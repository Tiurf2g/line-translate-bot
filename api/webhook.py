from fastapi import FastAPI, Request
import requests, os, json
from openai import OpenAI

app = FastAPI()

# LINE
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

# OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Upstash Cache
KV_URL = os.getenv("KV_REST_API_URL")
KV_TOKEN = os.getenv("KV_REST_API_TOKEN")
CACHE_KEY = "cache_translate_bot"


# -------------------------
#   Upstash Cache
# -------------------------
def load_cache():
    try:
        r = requests.get(
            f"{KV_URL}/get/{CACHE_KEY}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            timeout=5
        )
        raw = r.json().get("result")
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

    prompt = f"""
只回答「中文」或「越南文」其中一個。

判斷這句話是哪一種語言：

{text}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一個語言識別器，只回答語言名稱。"},
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
#   Translate（自然台式中文 & 自然越式越南文）
# -------------------------
def translate(text, target_lang, cache):
    ck = f"trans::{target_lang}::{text}"
    if ck in cache:
        return cache[ck]

    tone_rule = {
        "中文": (
            "請翻譯成自然、口語、像台灣人在聊天的中文。"
            "不要教學、不要字典解釋、不要說『在越南文中』、不要正式、不要僵硬。"
            "就像情侶、家人、朋友聊天那種自然感。"
        ),
        "越南文": (
            "請翻譯成自然的越南文（越南日常口語）。"
            "不要正式、不要僵硬、不要書面語、不要字典式定義。"
        )
    }

    prompt = f"""
{tone_rule[target_lang]}
如果原文已經是 {target_lang}，請直接輸出原文。

要翻譯的內容：

{text}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是自然口語翻譯員，翻譯要像真人在講話。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4
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

        # Language detection
        lang = detect_lang(text, cache)

        # Decide target language
        target = "越南文" if lang == "中文" else "中文"

        # Natural translation
        result = translate(text, target, cache)

        # Reply output
        reply(reply_token, result)

    return {"status": "ok"}
