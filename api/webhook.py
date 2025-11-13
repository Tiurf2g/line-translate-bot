from fastapi import FastAPI, Request
import requests, os, json
from openai import OpenAI

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

KV_URL = os.getenv("KV_REST_API_URL")
KV_TOKEN = os.getenv("KV_REST_API_TOKEN")

SETTINGS_KEY = "translator_settings"
CACHE_KEY = "translator_cache"

client = OpenAI(api_key=OPENAI_API_KEY)


# ================================
# Upstash REST API（正確格式）
# ================================
def kv_get(key: str, default=None):
    try:
        res = requests.get(
            f"{KV_URL}/get/{key}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            timeout=5
        )

        raw = res.json().get("result")

        if not raw:
            return default

        # Upstash 有兩種格式：字串 or dict
        # 1) {"result": "...."}  ← 舊格式
        # 2) {"result": {"data": "...", "error": null}} ← 新格式
        if isinstance(raw, dict):
            raw = raw.get("data")

        if not raw:
            return default

        return json.loads(raw)

    except Exception:
        return default


def kv_set(key: str, value):
    try:
        requests.post(
            f"{KV_URL}/set/{key}",
            headers={
                "Authorization": f"Bearer {KV_TOKEN}",
                "Content-Type": "application/json"
            },
            json={"value": json.dumps(value)},
            timeout=5
        )
    except:
        pass


# =============== Settings/Cache ===============
def load_settings():
    return kv_get(SETTINGS_KEY, {})


def save_settings(data):
    kv_set(SETTINGS_KEY, data)


def load_cache():
    return kv_get(CACHE_KEY, {})


def save_cache(cache):
    kv_set(CACHE_KEY, cache)


# =============== 語言正規化 ===============
LANG_ALIASES = {
    "中文": ["中文", "繁中", "繁體中文", "zh", "chinese", "cn"],
    "英文": ["英文", "英", "en", "english"],
    "越南文": ["越南文", "越文", "vi", "vietnamese"],
    "日文": ["日文", "jp", "ja", "japanese"],
    "韓文": ["韓文", "kr", "ko", "korean"],
    "印尼文": ["印尼文", "id", "indonesian", "bahasa"],
    "泰文": ["泰文", "th", "thai"],
    "西班牙文": ["西班牙文", "西文", "es", "spanish"],
    "德文": ["德文", "de", "german"],
}


def normalize_lang(name: str) -> str:
    n = name.strip().lower()
    for std, alts in LANG_ALIASES.items():
        if n == std.lower() or n in [a.lower() for a in alts]:
            return std
    return name.strip()


# =============== 語言偵測 ===============
def detect_language(text: str, cache):
    cache_key = f"detect::{text}"

    if cache_key in cache:
        return cache[cache_key]

    prompt = (
        "請判斷以下句子的語言種類，僅回答：中文 / 英文 / 越南文 / 日文 / 韓文 / 印尼文 / 泰文 / 西班牙文 / 德文。\n"
        "若無法判斷，回英文。\n\n"
        f"句子：{text}"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是語言識別專家。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0
        )

        lang = normalize_lang(res.choices[0].message.content.strip())
        cache[cache_key] = lang
        save_cache(cache)
        return lang

    except:
        return "英文"


# =============== 翻譯功能 ===============
def translate_text(text, source_lang, target_lang, cache, tone="normal"):
    cache_key = f"trans::{source_lang}->{target_lang}::{tone}::{text}"

    if cache_key in cache:
        return cache[cache_key]

    tone_map = {
        "normal": "自然流暢、口語化但保持禮貌。",
        "formal": "正式、書面化、精準。",
        "casual": "輕鬆口語、朋友聊天語氣。",
    }

    style = "自然流暢的繁體中文（台灣用語）" if "中" in target_lang else target_lang

    prompt = (
        f"請將以下內容翻譯成 {style}，語氣：{tone_map[tone]}\n"
        f"若已是目標語言，請直接輸出原文。\n\n"
        f"內容：\n{text}"
    )

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是專業翻譯員。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3
    )

    result = res.choices[0].message.content.strip()

    # 繁體化修正
    if "中" in target_lang:
        trad = {
            "这": "這", "着": "著", "么": "麼", "为": "為", "于": "於",
            "觉": "覺", "听": "聽", "关": "關", "头": "頭", "电": "電",
        }
        for k, v in trad.items():
            result = result.replace(k, v)

    cache[cache_key] = result
    save_cache(cache)

    return result


# =============== LINE 回覆 ===============
def line_reply(reply_token, text):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    }
    requests.post(LINE_REPLY_API, headers=headers, json=body)


# =============== webhook 主程式 ===============
@app.post("/api/webhook")
async def webhook(req: Request):
    try:
        body = await req.json()
    except:
        return {"status": "ok"}

    events = body.get("events", [])

    settings = load_settings()
    cache = load_cache()

    for ev in events:
        if ev.get("type") != "message":
            continue

        msg = ev.get("message", {})
        if msg.get("type") != "text":
            continue

        user_msg = msg.get("text", "").strip()
        msg_lower = user_msg.lower()
        reply_token = ev.get("replyToken")
        user_id = ev.get("source", {}).get("userId")
        key = f"user:{user_id}"

        if key not in settings:
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False,
            }

        cfg = settings[key]

        # ===== 指令區 =====
        if msg_lower == "/help":
            line_reply(reply_token,
                       "📘 指令清單：\n/set\n/status\n/on\n/off\n/reset\n/tone\n/smart\n/langlist\n/clearcache")
            continue

        if msg_lower == "/clearcache":
            save_cache({})
            line_reply(reply_token, "🔄 快取已清除")
            continue

        if msg_lower == "/langlist":
            line_reply(reply_token, "🌐 支援：中文、英文、越南文、日文、韓文、印尼文、泰文、西班牙文、德文")
            continue

        if msg_lower.startswith("/tone "):
            t = msg_lower.split(" ", 1)[1]
            if t in ["normal", "formal", "casual"]:
                cfg["tone"] = t
                save_settings(settings)
                line_reply(reply_token, f"🎙️ 已設定語氣：{t}")
            continue

        if msg_lower == "/smart on":
            cfg["smart"] = True
            save_settings(settings)
            line_reply(reply_token, "🤖 Smart 模式 ON")
            continue

        if msg_lower == "/smart off":
            cfg["smart"] = False
            save_settings(settings)
            line_reply(reply_token, "🧩 Smart 模式 OFF")
            continue

        if msg_lower.startswith("/set "):
            lang = normalize_lang(msg_lower.replace("/set", "").strip())
            cfg["target"] = lang
            cfg["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, f"✅ 已設定：翻譯成 {lang}")
            continue

        if msg_lower == "/status":
            line_reply(
                reply_token,
                f"🔧 設定：\n狀態：{'ON' if cfg['enabled'] else 'OFF'}\n語言：{cfg['target']}\n語氣：{cfg['tone']}\nSmart：{'ON' if cfg['smart'] else 'OFF'}"
            )
            continue

        if msg_lower == "/off":
            cfg["enabled"] = False
            save_settings(settings)
            line_reply(reply_token, "⏸️ 翻譯 OFF")
            continue

        if msg_lower == "/on":
            cfg["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, "▶️ 翻譯 ON")
            continue

        if msg_lower == "/reset":
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False,
            }
            save_settings(settings)
            line_reply(reply_token, "♻️ 已重設為中文")
            continue

        # =============== 自動翻譯 ===============
        if cfg["enabled"]:
            detected = detect_language(user_msg, cache)

            target = (
                "越南文" if cfg["smart"] and detected == "中文"
                else "中文" if cfg["smart"] and detected == "越南文"
                else cfg["target"]
            )

            if detected != target:
                result = translate_text(user_msg, detected, target, cache, tone=cfg["tone"])
                line_reply(reply_token, result)

    return {"status": "ok"}

