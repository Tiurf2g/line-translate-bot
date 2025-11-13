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

# ============================================================
# 🚀 Upstash v2：完全修復「雙層 JSON 導致設定沒寫入」問題
# ============================================================
def kv_get(key: str, default=None):
    try:
        r = requests.get(
            f"{KV_URL}/get/{key}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            timeout=5
        )
        raw = r.json().get("result")

        if raw is None:
            return default

        # 🟢 修正：可能是字串，要再解一次 JSON
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except:
                return default

        return raw if isinstance(raw, dict) else default

    except:
        return default


def kv_set(key: str, value):
    try:
        # 🟢 修正：不得再 json.dumps(value)，會變成雙層 JSON
        requests.post(
            f"{KV_URL}/set/{key}",
            headers={
                "Authorization": f"Bearer {KV_TOKEN}",
                "Content-Type": "application/json"
            },
            json={"value": value},
            timeout=5
        )
    except:
        pass


# ================= Settings/Cache
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


# ============================================================
# 語言正規化
# ============================================================
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


def normalize_lang(name: str):
    if not name:
        return "中文"

    n = name.strip().lower().replace(" ", "")
    for std, alts in LANG_ALIASES.items():
        if n == std.lower():
            return std
        for a in alts:
            if n == a.lower().replace(" ", ""):
                return std

    return name.strip()


# ============================================================
# 語言偵測（gpt-4o）
# ============================================================
def detect_language(text, cache):
    ck = f"detect::{text}"
    if ck in cache:
        return cache[ck]

    prompt = f"請判斷以下句子的語言，只回答：中文、英文、越南文、日文、韓文、印尼文、泰文、西班牙文、德文。\n\n{text}"

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "你是語言識別專家。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0
        )
        lang = normalize_lang(res.choices[0].message.content.strip())
    except:
        lang = "英文"

    cache[ck] = lang
    save_cache(cache)
    return lang


# ============================================================
# 翻譯（gpt-4o + 自動繁體補強）
# ============================================================
def translate_text(text, source_lang, target_lang, cache, tone="normal"):
    ck = f"trans::{source_lang}->{target_lang}::{tone}::{text}"
    if ck in cache:
        return cache[ck]

    tone_map = {
        "normal": "自然口語、清楚、流暢。",
        "formal": "正式、精準、工整。",
        "casual": "朋友聊天語氣，更輕鬆。",
    }

    style = "繁體中文（台灣用語）" if target_lang == "中文" else target_lang

    prompt = (
        f"請翻譯成 {style}，語氣使用：{tone_map[tone]}\n"
        f"若本來就是該語言，請直接回原文。\n\n{text}"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "你是專業翻譯。翻譯自然不死板。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3
        )
        out = res.choices[0].message.content.strip()
    except:
        out = text

    # 自動繁體化
    if target_lang == "中文":
        trad = {
            "这": "這","着": "著","么": "麼","为": "為","于": "於",
            "觉": "覺","听": "聽","关": "關","头": "頭","电": "電",
        }
        for k, v in trad.items():
            out = out.replace(k, v)

    cache[ck] = out
    save_cache(cache)
    return out


# ============================================================
# LINE 回覆
# ============================================================
def line_reply(reply_token, text):
    requests.post(
        LINE_REPLY_API,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text[:4900]}],
        }
    )


# ============================================================
# key 決定來源（user / group / room）
# ============================================================
def get_source_key(ev):
    src = ev.get("source", {})
    t = src.get("type")

    if t == "user":
        return f"user:{src.get('userId')}"
    if t == "group":
        return f"group:{src.get('groupId')}"
    if t == "room":
        return f"room:{src.get('roomId')}"
    return "unknown"


# ============================================================
# Smart：中↔越互翻
# ============================================================
def smart_target(detected, cfg):
    if not cfg.get("smart"):
        return cfg["target"]

    if detected == "中文":
        return "越南文"
    if detected == "越南文":
        return "中文"
    return "中文"


# ============================================================
# Webhook（最終完整版）
# ============================================================
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

        # 初始化
        if key not in settings:
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False,
            }

        cfg = settings[key]

        # ----------------------
        # 指令們
        # ----------------------
        if msg_lower == "/status":
            line_reply(
                reply_token,
                f"🔧 狀態：{'ON' if cfg['enabled'] else 'OFF'}\n"
                f"🌐 語言：{cfg['target']}\n"
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
            line_reply(reply_token, f"✅ 已設定翻譯語言：{lang}")
            continue

        if msg_lower == "/smart on":
            cfg["smart"] = True
            save_settings(settings)
            line_reply(reply_token, "🤖 Smart：ON（中文↔越南文）")
            continue

        if msg_lower == "/smart off":
            cfg["smart"] = False
            save_settings(settings)
            line_reply(reply_token, "🧩 Smart：OFF")
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

        # ============================================================
        # 自動翻譯
        # ============================================================
        if cfg["enabled"]:
            detected = detect_language(user_msg, cache)
            target = smart_target(detected, cfg)

            if detected != target:
                translated = translate_text(
                    user_msg, detected, target, cache, cfg["tone"]
                )
                line_reply(reply_token, translated)

    return {"status": "ok"}
