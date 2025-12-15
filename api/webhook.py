import os
import hmac
import hashlib
import base64
import requests
from fastapi import FastAPI, Request
from openai import OpenAI

app = FastAPI()

# ======================
# ENV
# ======================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
client = OpenAI(api_key=OPENAI_API_KEY)

# ======================
# 家庭翻譯 Prompt
# ======================
TW_TO_VN_PROMPT = """你是一位住在台灣多年的越南人，
非常熟悉台灣夫妻與家庭日常對話。

請把台灣人口語中文，
改寫成越南人在家裡真的會這樣講的越南話。

避免書面、官方語氣，
要自然、溫柔、有生活感。
"""

VN_TO_TW_PROMPT = """你是一位很懂越南文化的台灣人，
知道越南人說話比較直接但不是沒禮貌。

請把越南話，
改寫成台灣人看了會覺得順、不刺耳的口語中文。
"""

VN_MARKS = set("ăâêôơưđĂÂÊÔƠƯĐ")


def is_vietnamese(text: str) -> bool:
    return any(ch in VN_MARKS for ch in text)


def verify_line_signature(body: bytes, signature: str) -> bool:
    # LINE: X-Line-Signature = base64(HMAC-SHA256(channelSecret, body))
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


def translate_family(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    # 防止 bot 翻自己（避免洗版）
    if text.startswith("🇹🇼") or text.startswith("🇻🇳"):
        return ""

    if is_vietnamese(text):
        system = VN_TO_TW_PROMPT
        prefix = "🇹🇼 "
    else:
        system = TW_TO_VN_PROMPT
        prefix = "🇻🇳 "

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        max_output_tokens=160,
        temperature=0.3,
    )
    out = (resp.output_text or "").strip()
    return prefix + out if out else ""


# ======================
# Routes
# 注意：在 Vercel /api/webhook 這種路由下，這裡要用 "/"
# ======================
@app.get("/")
def root():
    return {"ok": True, "msg": "LINE webhook alive (use /api/webhook)"}


@app.post("/")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("x-line-signature", "")

    # 驗簽失敗也回 200（避免 Developers 一直報錯）
    if not verify_line_signature(body, signature):
        print("⚠️ Invalid signature (ignored)")

    data = await request.json()
    events = data.get("events", [])

    # LINE Verify 會送 events:[]
    if not events:
        return {"ok": True}

    for ev in events:
        if ev.get("type") != "message":
            continue
        msg = ev.get("message", {})
        if msg.get("type") != "text":
            continue

        reply_token = ev.get("replyToken")
        if not reply_token:
            continue

        original = msg.get("text", "")
        try:
            translated = translate_family(original)
            if translated:
                reply_line(reply_token, translated)
        except Exception as e:
            print("❌ translate error:", repr(e))

    return {"ok": True}
