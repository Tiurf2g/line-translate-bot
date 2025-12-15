import os
import hmac
import hashlib
import base64
import traceback
import requests
from fastapi import FastAPI, Request
from openai import OpenAI

app = FastAPI()

# =========================
# Environment
# =========================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FAMILY_GROUP_IDS = os.getenv("FAMILY_GROUP_IDS", "")

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# Prompts
# =========================
TW_TO_VN_PROMPT = """你是一位住在台灣多年的越南人，熟悉夫妻與家庭日常對話。
請把台灣人口語中文改寫成越南人在家裡真的會這樣講的越南話。
避免書面官方語氣，要自然、有生活感。"""

VN_TO_TW_PROMPT = """你是一位很懂越南文化的台灣人。
請把越南話改寫成台灣人看了會覺得順、不刺耳的口語中文。"""

DIRECT_TRANSLATE_PROMPT = """請忠實、直接翻譯使用者輸入的內容。
不要改寫、不要修飾、不加任何說明、不加國別標示。
只輸出翻譯後的文字本身。"""

# =========================
# Language helpers
# =========================
VN_MARKS = set("ăâêôơưđĂÂÊÔƠƯĐ")


def is_vietnamese(text: str) -> bool:
    return any(ch in VN_MARKS for ch in text)


def is_non_family(event: dict) -> bool:
    """
    True  = 非家庭模式（直翻）
    False = 家庭模式（生活化）
    """
    src = (event or {}).get("source") or {}
    gid = src.get("groupId") or src.get("roomId")

    # curl / 私聊 / 無 groupId
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
# Translation core
# =========================
def translate_text(text: str, event: dict) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    # 避免 bot 翻自己
    if text.startswith("🇹🇼") or text.startswith("🇻🇳"):
        return ""

    # 非家庭 → 直翻
    if is_non_family(event):
        system = DIRECT_TRANSLATE_PROMPT
    else:
        # 家庭模式
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

    return (resp.choices[0].message.content or "").strip()


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
                return {
                    "ok": True,
                    "input": original,
                    "translated": translated,
                }

            if translated and reply_token:
                reply_line(reply_token, translated)

        return {"ok": True}

    except Exception as e:
        print("❌ WEBHOOK_FATAL:", repr(e))
        print(traceback.format_exc())
        return {"ok": False, "error": repr(e)}
