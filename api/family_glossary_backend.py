# family_glossary_backend.py
# A lightweight backend for storing/retrieving a shared "family glossary" (single source of truth)
# via Upstash KV REST API. Includes PIN-protected write endpoints + small in-memory cache.

import os
import time
import json
from typing import List, Optional, Literal, Dict, Any

import requests
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# =========================
# Env
# =========================
KV_REST_API_URL = os.getenv("KV_REST_API_URL", "").rstrip("/")
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN", "")

# Use ADMIN_PIN first; fallback to APP_PIN for convenience
ADMIN_PIN = os.getenv("ADMIN_PIN", os.getenv("APP_PIN", ""))

# Default key is family_glossary; customizable via env
GLOSSARY_KEY = os.getenv("FAMILY_GLOSSARY_KEY", "family_glossary")

# Cache (seconds) to reduce KV hits for frequent reads
CACHE_TTL_SECONDS = int(os.getenv("FAMILY_GLOSSARY_CACHE_TTL", "20"))
_cache: Dict[str, Any] = {"ts": 0.0, "data": []}


# =========================
# Models
# =========================
class GlossaryEntry(BaseModel):
    zh: str = Field(..., min_length=1)
    en: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class ImportPayload(BaseModel):
    items: List[GlossaryEntry] = Field(default_factory=list)


# =========================
# KV helpers (Upstash REST)
# =========================
def _kv_headers() -> dict:
    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Missing KV_REST_API_URL or KV_REST_API_TOKEN",
        )
    return {"Authorization": f"Bearer {KV_REST_API_TOKEN}"}


def kv_get_json(key: str) -> Any:
    url = f"{KV_REST_API_URL}/get/{key}"
    r = requests.get(url, headers=_kv_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    raw = data.get("result")
    if raw is None:
        return None

    # Upstash might store as JSON string; parse if possible
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def kv_set_json(key: str, value: Any) -> None:
    url = f"{KV_REST_API_URL}/set/{key}"
    payload = {"value": json.dumps(value, ensure_ascii=False)}
    r = requests.post(url, headers=_kv_headers(), json=payload, timeout=10)
    r.raise_for_status()


def kv_del(key: str) -> None:
    url = f"{KV_REST_API_URL}/del/{key}"
    r = requests.post(url, headers=_kv_headers(), timeout=10)
    r.raise_for_status()


def require_pin(x_admin_pin: Optional[str]) -> None:
    if not ADMIN_PIN:
        raise HTTPException(status_code=500, detail="ADMIN_PIN not set (or APP_PIN fallback missing)")
    if (not x_admin_pin) or (x_admin_pin != ADMIN_PIN):
        raise HTTPException(status_code=401, detail="Invalid PIN")


# =========================
# Glossary core
# =========================
def _normalize_items(items: List[dict]) -> List[dict]:
    """Normalize entries: trim strings, clean tags, de-duplicate by zh."""
    out: List[dict] = []
    seen = set()

    for it in items:
        zh = (it.get("zh") or "").strip()
        en = (it.get("en") or "").strip()
        if not zh or not en:
            continue

        tags = it.get("tags") or []
        if isinstance(tags, str):
            tags = [x.strip() for x in tags.split(",")]
        tags = [x.strip() for x in tags if x and x.strip()]
        tags = sorted(set(tags))

        note = it.get("note")
        key = zh  # use zh as primary key (simple & practical)

        if key in seen:
            continue
        seen.add(key)

        out.append({"zh": zh, "en": en, "tags": tags, "note": note})

    return out


def get_glossary(force: bool = False) -> List[dict]:
    now = time.time()
    if (not force) and (now - float(_cache["ts"]) < CACHE_TTL_SECONDS):
        return _cache["data"]

    data = kv_get_json(GLOSSARY_KEY)
    if not data:
        items: List[dict] = []
    else:
        # Support either list storage or {"items":[...]}
        if isinstance(data, dict) and "items" in data:
            items = data.get("items") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []

    items = _normalize_items(items)
    _cache["ts"] = now
    _cache["data"] = items
    return items


def save_glossary(items: List[dict]) -> None:
    items = _normalize_items(items)
    kv_set_json(GLOSSARY_KEY, {"items": items, "updated_at": int(time.time())})
    _cache["ts"] = 0.0
    _cache["data"] = []


def upsert_entry(entry: GlossaryEntry) -> dict:
    items = get_glossary(force=True)
    by_zh = {it["zh"]: it for it in items}

    zh = entry.zh.strip()
    by_zh[zh] = {
        "zh": zh,
        "en": entry.en.strip(),
        "tags": sorted(set([t.strip() for t in entry.tags if t and t.strip()])),
        "note": entry.note,
    }

    new_items = list(by_zh.values())
    new_items.sort(key=lambda x: x["zh"])
    save_glossary(new_items)
    return by_zh[zh]


def import_entries(payload: ImportPayload, mode: Literal["append", "replace"]) -> dict:
    incoming = _normalize_items([e.model_dump() for e in payload.items])

    if mode == "replace":
        save_glossary(incoming)
        return {"mode": mode, "count": len(incoming)}

    # append: upsert by zh
    current = get_glossary(force=True)
    by_zh = {it["zh"]: it for it in current}
    for it in incoming:
        by_zh[it["zh"]] = it

    merged = list(by_zh.values())
    merged.sort(key=lambda x: x["zh"])
    save_glossary(merged)
    return {"mode": mode, "count": len(merged), "added_or_updated": len(incoming)}


# =========================
# App
# =========================
app = FastAPI()

# If you're calling from a Vercel/Next.js admin page, CORS helps.
# You can tighten allow_origins later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    return {
        "ok": True,
        "service": "family-glossary-backend",
        "kv_configured": bool(KV_REST_API_URL and KV_REST_API_TOKEN),
        "pin_configured": bool(ADMIN_PIN),
        "key": GLOSSARY_KEY,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
    }


# =========================
# Family routes (recommended)
# =========================
@app.get("/api/family-glossary")
def api_get_family_glossary(force: bool = Query(False)):
    items = get_glossary(force=force)
    return {"ok": True, "count": len(items), "glossary": items}


@app.post("/api/family-glossary/upsert")
def api_family_upsert(entry: GlossaryEntry, x_admin_pin: Optional[str] = Header(None)):
    require_pin(x_admin_pin)
    saved = upsert_entry(entry)
    return {"ok": True, "saved": saved}


@app.post("/api/family-glossary/import")
def api_family_import(
    payload: ImportPayload,
    mode: Literal["append", "replace"] = Query("append"),
    x_admin_pin: Optional[str] = Header(None),
):
    require_pin(x_admin_pin)
    res = import_entries(payload, mode=mode)
    return {"ok": True, **res}


@app.post("/api/family-glossary/reset")
def api_family_reset(x_admin_pin: Optional[str] = Header(None)):
    require_pin(x_admin_pin)
    kv_del(GLOSSARY_KEY)
    _cache["ts"] = 0.0
    _cache["data"] = []
    return {"ok": True, "message": "Family glossary cleared"}


# =========================
# Optional: Backward-compatible aliases (so old frontends still work)
# If you don't want these, just delete this section.
# =========================
@app.get("/api/factory-glossary")
def api_get_factory_glossary_alias(force: bool = Query(False)):
    return api_get_family_glossary(force=force)


@app.post("/api/factory-glossary/upsert")
def api_factory_upsert_alias(entry: GlossaryEntry, x_admin_pin: Optional[str] = Header(None)):
    return api_family_upsert(entry=entry, x_admin_pin=x_admin_pin)


@app.post("/api/factory-glossary/import")
def api_factory_import_alias(
    payload: ImportPayload,
    mode: Literal["append", "replace"] = Query("append"),
    x_admin_pin: Optional[str] = Header(None),
):
    return api_family_import(payload=payload, mode=mode, x_admin_pin=x_admin_pin)


@app.post("/api/factory-glossary/reset")
def api_factory_reset_alias(x_admin_pin: Optional[str] = Header(None)):
    return api_family_reset(x_admin_pin=x_admin_pin)
