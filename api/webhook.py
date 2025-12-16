import os
import hmac
import hashlib
import base64
import traceback
import requests
import re
import json
from typing import Dict, Any
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI

app = FastAPI()

# =========================
# Environment
# =========================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FAMILY_GROUP_IDS = os.getenv("FAMILY_GROUP_IDS", "")

# Admin (Basic Auth)
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

# Upstash KV (Dictionary storage)
KV_REST_API_URL = os.getenv("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN", "")
DICT_KEY = os.getenv("DICT_KEY", "dict_translate_bot_v1")  # 可不設

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
client = OpenAI(api_key=OPENAI_API_KEY)

# ★ 重要：在 Vercel 你的對外入口是 /api/webhook
# 後台也要掛在這個底下，才不會 404
ADMIN_BASE = "/admin"


# =========================
# Prompts
# =========================
TW_TO_VN_PROMPT = """你是一位住在台灣多年的越南人，
平常在家中與配偶、小孩、長輩用越南話溝通。

任務：
- 把台灣人口語中文，翻成「越南家庭裡真的會講的話」
- 語氣要溫柔、自然、偏生活化
- 可以使用越南人常用的語助詞（如：ừ、ờ、uh、ha、nè、á）
- 適度使用年輕人或家庭常見說法
- 不要書面、不要正式、不要像新聞或課本
- 不要加解釋，只輸出翻譯內容
"""

VN_TO_TW_PROMPT = """你是一位很懂越南文化的台灣人，
長期接觸越南家庭、夫妻與親子對話。

任務：
- 把越南口語翻成「台灣人在家裡真的會講的中文」
- 可以出現「嗯、喔、啊、欸、啦、耶」等口語語氣
- 翻成自然、不刺耳、不生硬的生活中文
- 不要太完整句、不要像作文

重要規則（台灣在地用語）：
- "thẻ bảo hiểm y tế" 一律翻成「健保卡」
- 不可翻成「保險卡」
- 牽涉小孩/看醫生/證件/卡片時，優先使用台灣家庭常用說法

不要加解釋，只輸出翻譯內容
"""

DIRECT_TRANSLATE_PROMPT = """你是一個【中文 ↔ 越南文】專用翻譯器。

規則：
- 如果輸入是中文（繁體或簡體），請翻譯成「越南文」。
- 如果輸入是越南文，請翻譯成「繁體中文」。
- 絕對不要輸出英文。
- 不要加說明、不要加標註、不要加任何前後綴。
- 只輸出翻譯後的文字本身。"""


# =========================
# Language helpers
# =========================
VN_MARKS = set("ăâêôơưđĂÂÊÔƠƯĐ")

# 連結 / 網頁分享：不翻譯（避免群組被洗版）
URL_PATTERN = re.compile(r"(https?://|www\.|line\.me/|liff\.line\.me/)")

# --- Filler / 語助詞：硬規則（不走模型，穩、快、準） ---
FILLER_MAP_TW_TO_VN = {
    "嗯": "Uh",
    "嗯嗯": "Uh uh",
    "喔": "Ờ",
    "哦": "Ờ",
    "啊": "À",
}

VN_FILLERS = {"uh", "ừ", "ờ", "ha", "nè", "á", "a", "à", "ừm", "um", "ừm ừm"}

FILLER_MAP_VN_TO_TW = {
    "uh": "嗯",
    "ừ": "嗯",
    "ờ": "喔",
    "ha": "哈",
    "nè": "捏",
    "á": "啊",
    "à": "啊",
    "um": "嗯",
    "ừm": "嗯",
}


def is_vietnamese(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in VN_FILLERS:
        return True
    return any(ch in VN_MARKS for ch in (text or ""))


def is_non_family(event: dict) -> bool:
    src = (event or {}).get("source") or {}
    gid = src.get("groupId") or src.get("roomId")

    if not gid:
        return True

    fam_ids = {x.strip() for x in FAMILY_GROUP_IDS.split(",") if x.strip()}
    if not fam_ids:
        return True

    return gid not in fam_ids


# =========================
# LINE helpers
# =========================
def verify_line_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    mac = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def reply_line(reply_token: str, text: str):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ Missing LINE_CHANNEL_ACCESS_TOKEN")
        return

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    r = requests.post(LINE_REPLY_API, headers=headers, json=payload, timeout=10)
    if r.status_code != 200:
        print("❌ LINE reply failed:", r.status_code, r.text)


# =========================
# Upstash KV Dictionary
# =========================
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

        # shape guard
        for k in ("tw_to_vn", "vn_to_tw", "replace_out"):
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
        return d
    except Exception:
        return _dict_default()


def kv_set_dict(d: Dict[str, Any]) -> bool:
    if not kv_enabled():
        return False
    try:
        payload = json.dumps(d, ensure_ascii=False)
        r = requests.post(
            f"{KV_REST_API_URL}/set/{DICT_KEY}",
            headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"},
            json={"value": payload},
            timeout=5,
        )
        return r.status_code == 200
    except Exception:
        return False


def dict_lookup_exact(text: str) -> str:
    """
    回傳：若詞庫命中，直接回翻譯後文字；否則回空字串
    """
    d = kv_get_dict()
    t = (text or "").strip()
    if not t:
        return ""

    if not is_vietnamese(t):
        if t in d["tw_to_vn"]:
            return d["tw_to_vn"][t]
    else:
        # 越南詞庫允許大小寫不同
        tl = t.lower()
        for k, v in d["vn_to_tw"].items():
            if k.lower() == tl:
                return v

    return ""


def apply_replace_out(out: str, original_text: str) -> str:
    """
    輸出保底替換（例如：保險卡->健保卡）
    以及原本你做的健保卡保底
    """
    d = kv_get_dict()
    for a, b in d.get("replace_out", {}).items():
        if a:
            out = out.replace(a, b)

    src_low = (original_text or "").lower()
    if ("thẻ bảo hiểm y tế" in src_low or "bao hiem y te" in src_low or "bảo hiểm y tế" in src_low):
        out = out.replace("保險卡", "健保卡")

    return out


# =========================
# Admin (Basic Auth)
# =========================
def _basic_auth_ok(request: Request) -> bool:
    """
    簡易 Basic Auth：
    - 需要設定 ADMIN_USER / ADMIN_PASS
    - 瀏覽器會跳帳密視窗
    """
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


# =========================
# Admin pages (★搬到 /api/webhook/admin)
# =========================
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not _basic_auth_ok(request):
        return _basic_auth_challenge()

    d = kv_get_dict()
    tw_to_vn = d.get("tw_to_vn", {})
    vn_to_tw = d.get("vn_to_tw", {})
    replace_out = d.get("replace_out", {})

    def render_table(title, data):
        rows = "".join(
            [f"<tr><td style='padding:6px'>{k}</td><td style='padding:6px'>{v}</td></tr>" for k, v in data.items()]
        )
        if not rows:
            rows = "<tr><td colspan='2' style='padding:6px;color:#666'>(empty)</td></tr>"
        return f"""
        <h4 style="margin-top:18px">{title}</h4>
        <table border="1" cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%">
          <tr><th style='padding:6px'>Key</th><th style='padding:6px'>Value</th></tr>
          {rows}
        </table>
        """

    warn = ""
    if not kv_enabled():
        warn = "<p style='color:#b00'>⚠️ 你尚未設定 Upstash KV（KV_REST_API_URL / KV_REST_API_TOKEN）。後台新增不會永久保存。</p>"

    html = f"""
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Dictionary Admin</title>
    </head>
    <body style="font-family: Arial; padding:16px; max-width:820px; margin:auto">
      <h3>Dictionary Admin</h3>
      {warn}

      <div style="padding:12px; border:1px solid #ddd; border-radius:10px">
        <h4 style="margin-top:0">新增 / 更新詞條</h4>
        <form method="post" action="{ADMIN_BASE}/add">
          <div style="margin:8px 0">
            類型：
            <select name="bucket">
              <option value="tw_to_vn">TW → VN（例如：嗯 → Uh）</option>
              <option value="vn_to_tw">VN → TW（例如：uh → 嗯）</option>
              <option value="replace_out">輸出保底替換（例如：保險卡 → 健保卡）</option>
            </select>
          </div>
          <div style="margin:8px 0">Key：<input name="k" style="width:70%" /></div>
          <div style="margin:8px 0">Value：<input name="v" style="width:70%" /></div>
          <button type="submit" style="padding:8px 14px">Save</button>
        </form>
      </div>

      <div style="padding:12px; border:1px solid #ddd; border-radius:10px; margin-top:12px">
        <h4 style="margin-top:0">刪除詞條</h4>
        <form method="post" action="{ADMIN_BASE}/del">
          <div style="margin:8px 0">
            類型：
            <select name="bucket">
              <option value="tw_to_vn">TW → VN</option>
              <option value="vn_to_tw">VN → TW</option>
              <option value="replace_out">輸出保底替換</option>
            </select>
          </div>
          <div style="margin:8px 0">Key：<input name="k" style="width:70%" /></div>
          <button type="submit" style="padding:8px 14px">Delete</button>
        </form>
      </div>

      {render_table("TW → VN", tw_to_vn)}
      {render_table("VN → TW", vn_to_tw)}
      {render_table("Replace Output", replace_out)}

      <p style="margin-top:18px; color:#666">
        Tip：新增「嗯 → Uh」請選 TW→VN；新增「uh → 嗯」請選 VN→TW。
      </p>
    </body></html>
    """
    return HTMLResponse(html, status_code=200)


@app.post("/admin/add")
def admin_add(request: Request, bucket: str = Form(...), k: str = Form(...), v: str = Form(...)):
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


@app.post("/admin/del")
def admin_del(request: Request, bucket: str = Form(...), k: str = Form(...)):
    if not _basic_auth_ok(request):
        return _basic_auth_challenge()

    bucket = (bucket or "").strip()
    k = (k or "").strip()
    if bucket not in ("tw_to_vn", "vn_to_tw", "replace_out") or not k:
        return RedirectResponse(url=ADMIN_BASE, status_code=303)

    d = kv_get_dict()
    if bucket in d and k in d[bucket]:
        del d[bucket][k]
        kv_set_dict(d)
    return RedirectResponse(url=ADMIN_BASE, status_code=303)


# =========================
# Translation core
# =========================
def translate_text(text: str, event: dict) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    # 網頁 / 連結分享：不翻譯，保持單純網址即可
    if URL_PATTERN.search(text):
        return ""

    # 避免 bot 翻自己（你原本有判斷國旗前綴）
    if text.startswith("🇹🇼") or text.startswith("🇻🇳"):
        return ""

    # --- 0) 先查你「網頁後台自訂詞庫」（最優先） ---
    dict_hit = dict_lookup_exact(text)
    if dict_hit:
        return dict_hit

    # --- 1) 語助詞硬規則 ---
    if not is_vietnamese(text) and text in FILLER_MAP_TW_TO_VN:
        return FILLER_MAP_TW_TO_VN[text]

    t_low = text.lower()
    if is_vietnamese(text) and t_low in FILLER_MAP_VN_TO_TW:
        return FILLER_MAP_VN_TO_TW[t_low]

    # --- 2) 模式選擇 ---
    if is_non_family(event):
        system = DIRECT_TRANSLATE_PROMPT
    else:
        system = VN_TO_TW_PROMPT if is_vietnamese(text) else TW_TO_VN_PROMPT

    if not OPENAI_API_KEY:
        return "(OPENAI_API_KEY 沒設定)"

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
        max_tokens=180,
    )
    out = (resp.choices[0].message.content or "").strip()

    # --- 3) 輸出保底替換（含健保卡保底）---
    out = apply_replace_out(out, text)

    return out


# =========================
# Health check
# =========================
@app.get("/")
@app.get("/api/webhook")
def alive():
    return {
        "ok": True,
        "msg": "webhook alive",
        "openai_key_loaded": bool(OPENAI_API_KEY),
        "line_token_loaded": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "secret_loaded": bool(LINE_CHANNEL_SECRET),
        "kv_enabled": kv_enabled(),
        "admin_enabled": bool(ADMIN_USER and ADMIN_PASS),
        "admin_url": ADMIN_BASE,
    }


# =========================
# Webhook
# =========================
@app.post("/")
@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        body = await request.body()
        signature = request.headers.get("x-line-signature", "")

        # 你原本是 invalid 也不擋（保留你的設計）
        if not verify_line_signature(body, signature):
            print("⚠️ Invalid signature (ignored)")

        data = await request.json()
        events = data.get("events", [])

        if not events:
            return {"ok": True, "message": "No events"}

        for ev in events:
            if ev.get("type") != "message":
                continue
            msg = ev.get("message", {})
            if msg.get("type") != "text":
                continue

            reply_token = ev.get("replyToken")
            original = msg.get("text", "")

            translated = translate_text(original, ev)

            # curl 測試
            if reply_token == "TEST_TOKEN":
                return {"ok": True, "input": original, "translated": translated}

            if translated and reply_token:
                reply_line(reply_token, translated)

        return {"ok": True}

    except Exception as e:
        print("❌ WEBHOOK_FATAL:", repr(e))
        print(traceback.format_exc())
        return {"ok": False, "error": repr(e)}
