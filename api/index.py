from fastapi import FastAPI, Request
import os, json, hashlib
import httpx
from openai import OpenAI

app = FastAPI()

# LINE
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

# OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

# Upstash Cache
KV_URL = os.getenv("KV_REST_API_URL", "")
KV_TOKEN = os.getenv("KV_REST_API_TOKEN", "")
CACHE_KEY = "cache_translate_bot_v2"

HTTP_TIMEOUT = httpx.Timeout(6.0, connect=3.0)

def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:32]

# -------------------------
#   Upstash Cache (async)
# -------------------------
async def load_cache() -> dict:
    if not KV_URL or not KV_TOKEN:
        return {}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            r = await c.get(
                f"{KV_URL}/get/{CACHE_KEY}",
                headers={"Authorization": f"Bearer {KV_TOKEN}"},
            )
        raw = r.json().get("result")
        if isinstance(raw, str):
            return json.loads(raw)
        return raw if isinstance(raw, dict) else {}
    except:
        return {}

async def save_cache(cache: dict):
    if not KV_URL or not KV_TOKEN:
        return
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            await c.post(
                f"{KV_URL}/set/{CACHE_KEY}",
                headers={
                    "Authorization": f"Bearer {KV_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"value": cache},
            )
    except:
        pass

# -------------------------
#   Translate (one-shot: detect + translate)
# -------------------------
SYSTEM_TRANSLATOR = (
    "你是台灣中文 ↔ 越南文的即時聊天翻譯員。"
    "目標：像家人/朋友聊天一樣自然、在地、精準。"
    "規則：只輸出翻譯結果，不要解釋、不加括號、不加原文、不加語言標籤、不加emoji。"
)

USER_PROMPT = """請先判斷這句話主要語言（中文或越南文），然後翻譯成另一種語言：
- 中文→翻成「台灣日常口語中文」：自然、好懂、像聊天（可用台灣常用詞），避免書面與生硬直翻。
- 越南文→翻成「越南日常口語」：自然、越南人平常會講的說法，避免正式公文風。
注意：保留人名/地名/數字/單位/時間格式；不確定縮寫就原樣保留；髒話/語氣詞照原語氣自然呈現。
要翻譯的內容：
{text}
"""

async def translate_one_shot(text: str, cache: dict) -> str:
    # normalize
    text = (text or "").strip()
    if not text:
        return text

    # avoid wasting tokens for very short junk
    if len(text) <= 1:
        return text

    ck = f"t::{_h(text)}"
    if ck in cache:
        return cache[ck]

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_TRANSLATOR},
                {"role": "user", "content": USER_PROMPT.format(text=text)},
            ],
            temperature=0.2,
        )
        out = (res.choices[0].message.content or "").strip()
        if not out:
            out = text
    except:
        out = text

    cache[ck] = out
    # fire-and-forget style (await to persist; you can remove await for even faster but less reliable cache)
    await save_cache(cache)
    return out

# -------------------------
#   LINE Reply (async)
# -------------------------
async def reply(reply_token: str, text: str):
    if not LINE_CHANNEL_ACCESS_TOKEN or not reply_token:
        return
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            await c.post(
                LINE_REPLY_API,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                },
                json=payload,
            )
    except:
        pass

# -------------------------
#   Health check (optional but recommended for LINE Developers verify)
# -------------------------
@app.get("/api/healthz")
async def healthz():
    return {"ok": True}

# -------------------------
#   Webhook
# -------------------------
@app.post("/api/webhook")
async def webhook(req: Request):
    try:
        body = await req.json()
    except:
        return {"status": "ok"}

    events = body.get("events", [])
    cache = await load_cache()

    for ev in events:
        if ev.get("type") != "message":
            continue

        msg = ev.get("message", {})
        if msg.get("type") != "text":
            continue

        text = (msg.get("text") or "").strip()
        if not text:
            continue

        # 避免自己回自己（如果你有把 bot 的 userId 存起來可更精準判斷；先用常見欄位保底）
        src = ev.get("source", {})
        if src.get("type") == "bot":
            continue

        reply_token = ev.get("replyToken")
        result = await translate_one_shot(text, cache)
        await reply(reply_token, result)

    return {"status": "ok"}
