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
# Upstash REST API
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

        if isinstance(raw, dict):
            raw = raw.get("data")

        if not raw:
            return default

        data = json.loads(raw)
        return data if isinstance(data, dict) else default
    except:
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
    data = kv_get(SETTINGS_KEY, {})
    return data if isinstance(data, dict) else {}


def save_settings(data):
    kv_set(SETTINGS_KEY, data)


def load_cache():
    data = kv_get(CACHE_KEY, {})
    return data if isinstance(data, dict) else {}


def save_cache(data):
    kv_set(CACHE_KEY, data)


# =============== 語言正規化（強化版） ===============
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
    if not name:
        return "中文"

    n = name.strip().lower().replace(" ", "")

    for std, alts in LANG_ALIASES.items():
        # 標準語本身
        if n == std.lower():
            return std

        # 同義詞
        for a in alts:
            if n == a.lower().replace(" ", ""):
                return std

    return name.strip()


# =============== 語言偵測（使用 gpt-4o） ===============
def detect_language(text: str, cache):
    cache_key = f"detect::{text}"
    if cache_key in cache:
        return cache[cache_key]

    prompt = (
        "偵測這句話的語言，只回答：中文、英文、越南文、日文、韓文、印尼文、泰文、西班牙文、德文\n\n"
        f"{text}"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "你是語言識別專家。回答要非常精準。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0
        )
        lang = normalize_lang(res.choices[0].message.content.strip())
    except:
        lang = "英文"

    cache[cache_key] = lang
    save_cache(cache)
    return lang


# =============== 翻譯功能（gpt-4o 全強化） ===============
def translate_text(text, source_lang, target_lang, cache, tone="normal"):
    cache_key = f"trans::{source_lang}->{target_lang}::{tone}::{text}"
    if cache_key in cache:
        return cache[cache_key]

    tone_map = {
        "normal": "自然、順口、禮貌。",
        "formal": "正式、嚴謹、精準。",
        "casual": "日常聊天語氣。",
    }

    style = "繁體中文（台灣用語）" if target_lang == "中文" else target_lang

    prompt = (
        f"請將以下內容翻譯成 {style}，語氣使用：{tone_map[tone]}\n"
        f"若內容本身已是目標語言請直接回傳原文。\n\n{text}"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "你是專業翻譯員，翻譯自然不死板。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3
        )
        result = res.choices[0].message.content.strip()
    except:
        result = text

    # 補強簡體 → 繁體
    if target_lang == "中文":
        trad = {
            "这": "這","着": "著","么": "麼","为": "為","于": "於",
            "觉": "覺","听": "聽","关": "關","头": "頭","电": "電",
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


# =============== key 來源 ===============
def get_source_key(ev):
    src = ev.get("source", {})
    stype = src.get("type")

    if stype == "user":
        return f"user:{src.get('userId')}"
    if stype == "group":
        return f"group:{src.get('groupId')}"
    if stype == "room":
        return f"room:{src.get('roomId')}"
    return "unknown"


# =============== Smart 模式邏輯 ===============
def smart_target(detected_lang, cfg):
    if not cfg.get("smart"):
        return cfg["target"]

    # 主人需求：中 ↔ 越 自動互翻
    if detected_lang == "中文":
        return "越南文"
    if detected_lang == "越南文":
        return "中文"

    # 其他語言 → 中文
    return "中文"


# =============== webhook 主程式（最終版） ===============
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

        user_msg = msg.get("text").strip()
        msg_lower = user_msg.lower()
        reply_token = ev.get("replyToken")
        key = get_source_key(ev)

        # 初始化設定
        if key not in settings:
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False,
            }

        cfg = settings[key]

        # ===== 指令處理 =====
        if msg_lower == "/status":
            line_reply(
                reply_token,
                f"🔧 狀態：{'ON' if cfg['enabled'] else 'OFF'}\n"
                f"🌐 目標語言：{cfg['target']}\n"
                f"🎙️ 語氣：{cfg['tone']}\n"
                f"🤖 Smart：{'ON' if cfg['smart'] else 'OFF'}"
            )
            continue

        if msg_lower.startswith("/set "):
            lang_raw = msg_lower.replace("/set", "").strip()
            lang = normalize_lang(lang_raw)
            cfg["target"] = lang
            cfg["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, f"✅ 已設定，之後翻譯將轉成：{lang}")
            continue

        if msg_lower == "/smart on":
            cfg["smart"] = True
            save_settings(settings)
            line_reply(reply_token, "🤖 Smart 模式：ON（中越互翻）")
            continue

        if msg_lower == "/smart off":
            cfg["smart"] = False
            save_settings(settings)
            line_reply(reply_token, "🧩 Smart 模式：OFF")
            continue

        if msg_lower == "/on":
            cfg["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, "▶️ 自動翻譯：ON")
            continue

        if msg_lower == "/off":
            cfg["enabled"] = False
            save_settings(settings)
            line_reply(reply_token, "⏸️ 自動翻譯：OFF")
            continue

        # ============================
        # 自動翻譯（完整升級版）
        # ============================
        if cfg["enabled"]:
            detected = detect_language(user_msg, cache)
            target = smart_target(detected, cfg)

            if detected != target:
                translated = translate_text(
                    user_msg, detected, target, cache, tone=cfg["tone"]
                )
                line_reply(reply_token, translated)

    return {"status": "ok"}
