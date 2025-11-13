from fastapi import FastAPI, Request
import requests, os, json
from openai import OpenAI

app = FastAPI()

# LINE
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

# OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Upstash（只存少量暫存，避免重複花 API）
KV_URL = os.getenv("KV_REST_API_URL")
KV_TOKEN = os.getenv("KV_REST_API_TOKEN")
CACHE_KEY = "cache_translate_bot"


# -------------------------
#   Upstash Cache
# -------------------------
def load_cache():
    try:
        res = requests.get(
            f"{KV_URL}/get/{CACHE_KEY}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            timeout=5
        )
        raw = res.json().get("result")
        if isinstance(raw, str):
            return json.loads(raw)
        return raw if isinstance(raw, dict) else {}
    except:
        return {}


def save_cache(cache):
    try:
        requests.post(
            f"{KV_URL}/set/{CACHE_KEY}",
            headers={
                "Authorization": f"Bearer {KV_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"value": cache},
            timeout=5
        )
    except:
        pass


# -------------------------
#   Detect Language
# -------------------------
def detect_lang(text, cache):
    ck = f"detect::{text}"
    if ck in cache:
        return cache[ck]

    prompt = f"判斷以下文本是 中文 或 越南文，只回答「中文」或「越南文」：\n{text}"

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "判斷語言。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0
        )
        lang = res.choices[0].message.content.strip()
    except:
        lang = "中文"

    cache[ck] = lang
    save_cache(cache)
    return lang


# -------------------------
#   Translate
# -------------------------
def translate(text, target_lang, cache):
    ck = f"trans::{target_lang}::{text}"
    if ck in cache:
        return cache[ck]

    tone = {
        "中文": "使用自然、口語化的台灣中文，不要太正式。",
        "越南文": "使用自然、口語化的越南文，不要太正式。",
    }

    prompt = (
        f"請把以下內容翻譯成 {target_lang}。\n"
        f"語氣要求：{tone[target_lang]}\n"
        f"若內容本來就是 {target_lang}，請直接回原文。\n\n{text}"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是自然口語翻譯員。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3
        )
        out = res.choices[0].message.content.strip()
    except:
        out = text

    cache[ck] = out
    save_cache(cache)
    return out


# -------------------------
#   LINE Reply
# -------------------------
def reply(token, text):
    requests.post(
        LINE_REPLY_API,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        },
        json={"replyToken": token, "messages": [{"type": "text", "text": text}]}
    )


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
    cache = load_cache()

    for ev in events:
        if ev.get("type") != "message":
            continue

        msg = ev.get("message", {})
        if msg.get("type") != "text":
            continue

        text = msg.get("text").strip()
        reply_token = ev.get("replyToken")

        # Detect
        lang = detect_lang(text, cache)

        # Decide target
        target = "越南文" if lang == "中文" else "中文"

        # Translate
        result = translate(text, target, cache)

        # Reply
        reply(reply_token, result)

    return {"status": "ok"}
