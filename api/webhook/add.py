import os, base64, json, requests
from typing import Dict, Any
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

KV_REST_API_URL = os.getenv("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN", "")
DICT_KEY = os.getenv("DICT_KEY", "dict_translate_bot_v1")

ADMIN_BASE = "/api/webhook/admin"

def _dict_default() -> Dict[str, Dict[str, str]]:
    return {"tw_to_vn": {}, "vn_to_tw": {}, "replace_out": {}}

def kv_enabled() -> bool:
    return bool(KV_REST_API_URL and KV_REST_API_TOKEN)

def kv_get_dict() -> Dict[str, Dict[str, str]]:
    if not kv_enabled():
        return _dict_default()
    try:
        r = requests.get(
            f"{KV_REST_API_URL}/get/{DICT_KEY}",
            headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"},
            timeout=5,
        )
        raw = r.json().get("result")
        if isinstance(raw, str) and raw:
            d = json.loads(raw)
        elif isinstance(raw, dict):
            d = raw
        else:
            d = _dict_default()
        for k in ("tw_to_vn", "vn_to_tw", "replace_out"):
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
        return d
    except Exception:
        return _dict_default()

def kv_set_dict(d: Dict[str, Any]) -> bool:
    if not kv_enabled():
        return False
    payload = json.dumps(d, ensure_ascii=False)
    r = requests.post(
        f"{KV_REST_API_URL}/set/{DICT_KEY}",
        headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"},
        json={"value": payload},
        timeout=5,
    )
    return r.status_code == 200

def _basic_auth_ok(request: Request) -> bool:
    if not (ADMIN_USER and ADMIN_PASS):
        return False
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        return False
    try:
        b64 = auth.split(" ", 1)[1].strip()
        raw = base64.b64decode(b64).decode("utf-8", errors="ignore")
        user, pw = raw.split(":", 1)
        return user == ADMIN_USER and pw == ADMIN_PASS
    except Exception:
        return False

def _basic_auth_challenge() -> HTMLResponse:
    return HTMLResponse(
        "Unauthorized",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Dictionary Admin"'},
    )

@app.post("/")
def add(request: Request, bucket: str = Form(...), k: str = Form(...), v: str = Form(...)):
    if not _basic_auth_ok(request):
        return _basic_auth_challenge()

    bucket = (bucket or "").strip()
    k = (k or "").strip()
    v = (v or "").strip()

    if bucket not in ("tw_to_vn", "vn_to_tw", "replace_out") or not k:
        return RedirectResponse(url=ADMIN_BASE, status_code=303)

    d = kv_get_dict()
    d.setdefault(bucket, {})
    d[bucket][k] = v
    kv_set_dict(d)
    return RedirectResponse(url=ADMIN_BASE, status_code=303)
