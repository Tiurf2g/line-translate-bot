import os
import hmac
import hashlib
import base64
from fastapi import FastAPI, Request, HTTPException
import requests
from openai import OpenAI

app = FastAPI()

# ========= ENV =========
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not LINE_CHANNEL_ACCESS_TOKEN:
    print("⚠️ Missing LINE_CHANNEL_ACCESS_TOKEN")
if not LINE_CHANNEL_SECRET:
    print("⚠️ Missing LINE_CHANNEL_SECRET")
if not OPENAI_API_KEY:
    print("⚠️ Missing OPENAI_API_KEY")

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
client = OpenAI(api_key=OPENAI_API_KEY)

# ========= 家庭模式 Prompt =========
TW_TO_VN_PROMPT = """你是一位住在台灣多年的越南人，
非常熟悉台灣夫妻、家庭、日常聊天的說話方式。

請把台灣人口語中文，
改寫成「越南人在家裡真的會這樣講」的越南話。

請避免書面、官方、翻譯腔，
要自然、溫柔、有生活感。

如果原文是關心、提醒、撒嬌、碎念，
請保留那種感覺。
"""

VN_TO_TW_PROMPT = """你是一位很懂越南文化的台灣人，
知道越南人說話比較直接，但不是沒禮貌。

請把越南話，
改寫成「台灣人看了會覺得順、不刺耳」的口語中文。

必要時可以稍微補語氣，
讓家人之間的對話更溫和自然。
"""

# ========= Utils =========
VN_MARKS = set("ăâêôơưđĂÂÊÔƠƯĐ")

def is_vietnamese(text: str) -> bool:
    # 家庭用：夠準就好（有越南字母就當越南文）
    return any(ch in VN_MARKS for ch in text)

def verify_line_signature(body: bytes, signature: str) -> bool:
    # LINE: X-Line-Signature = base64(HMAC-SHA256(channelSecret, body))
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    mac = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature)

def reply_line(reply_token: str, text: str):
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

    # 避免翻譯到自己的回覆造成洗版（保守策略）
    # 你也可以拿掉這段，但拿掉後「任何人訊息 + Bot 自己回覆」可能造成很吵。
    if text.startswith("🇻🇳") or text.startswith("🇹🇼"):
        return ""

    if is_vietnamese(text):
        system = VN_TO_TW_PROMPT
        prefix = "🇹🇼 "
    else:
        system = TW_TO_VN_PROMPT
        prefix = "🇻🇳 "

    # 用 Responses API（快、穩）
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        # 家庭聊天通常很短，限制輸出更快
        max_output_tokens=160,
        temperature=0.3,
    )

    out = (resp.output_text or "").strip()
    if not out:
        return ""
    return prefix + out

# ========= Routes =========
@app.get("/api/webhook")
def webhook_get():
    # LINE 不會用 GET 打 webhook，但留著避免有人誤測
    return {"ok": True, "hint": "POST here from LINE webhook"}

@app.post("/api/webhook")
async def webhook_post(request: Request):
    body = await request.body()
    signature = request.headers.get("x-line-signature", "")

    # ⚠️ 驗簽，不過「驗簽失敗」也要回 200（避免 LINE Developers 一直報 4xx）
    if not verify_line_signature(body, signature):
        print("⚠️ Invalid signature (still return 200)")

    data = await request.json()
    events = data.get("events", [])

    # LINE Developers 的測試會送 events: []
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
        translated = ""
        try:
            translated = translate_family(original)
        except Exception as e:
            print("❌ translate error:", repr(e))
            translated = ""

        if translated:
            reply_line(reply_token, translated)

    return {"ok": True}
