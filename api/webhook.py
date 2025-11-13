from fastapi import FastAPI, Request
import requests, os, json, re
from openai import OpenAI

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

# === Upstash KV (Redis) ===
KV_URL = os.getenv("KV_REST_API_URL")
KV_TOKEN = os.getenv("KV_REST_API_TOKEN")

SETTINGS_KEY = "translator_settings"
CACHE_KEY = "translator_cache"

client = OpenAI(api_key=OPENAI_API_KEY)

# === Upstash KV 基礎函式 ===
def kv_get(key: str, default=None):
    try:
        res = requests.get(
            f"{KV_URL}/get/{key}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            timeout=5
        )
        if res.status_code == 200:
            data = res.json().get("result")
            if data:
                return json.loads(data)
        return default
    except:
        return default

def kv_set(key: str, value):
    try:
        requests.post(
            f"{KV_URL}/set/{key}",
            headers={"Authorization": f"Bearer {KV_TOKEN}"},
            json=json.dumps(value),
            timeout=5
        )
    except:
        pass

# === 改寫：設定與快取全部存在 Redis ===
def load_settings():
    return kv_get(SETTINGS_KEY, {})

def save_settings(data):
    kv_set(SETTINGS_KEY, data)

def load_cache():
    return kv_get(CACHE_KEY, {})

def save_cache(cache):
    kv_set(CACHE_KEY, cache)

# === 語言正規化 ===
LANG_ALIASES = {
    "中文": ["中文", "繁中", "繁體中文", "zh", "chinese", "cn"],
    "英文": ["英文", "英", "en", "english"],
    "越南文": ["越南文", "越文", "vi", "vietnamese"],
    "日文": ["日文", "jp", "ja", "japanese"],
    "韓文": ["韓文", "kr", "ko", "korean"],
    "印尼文": ["印尼文", "id", "indonesian", "bahasa"],
    "泰文": ["泰文", "th", "thai"],
    "西班牙文": ["西班牙文", "西文", "es", "spanish"],
    "德文": ["德文", "de", "german"]
}

def normalize_lang(name: str) -> str:
    n = name.strip().lower()
    for std, alts in LANG_ALIASES.items():
        if n == std.lower() or n in [a.lower() for a in alts]:
            return std
    return name.strip()

# === 語言偵測（含快取） ===
def detect_language(text: str, cache):
    cache_key = f"detect::{text}"
    if cache_key in cache:
        return cache[cache_key]

    prompt = (
        "請判斷以下句子的語言種類，僅回「中文、英文、越南文、日文、韓文、印尼文、泰文、西班牙文、德文」之一；"
        "若不屬於以上，請回「英文」。\n\n句子：\n" + text
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是語言識別專家"},
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

# === 翻譯（含 Tone + Smart + Cache） ===
def translate_text(text: str, source_lang: str, target_lang: str, cache, tone="normal"):
    cache_key = f"trans::{source_lang}->{target_lang}::{tone}::{text}"
    if cache_key in cache:
        return cache[cache_key]

    style = "自然流暢的繁體中文（台灣用語）" if "中" in target_lang else target_lang

    tone_prompt = {
        "normal": "自然流暢、口語化但保持禮貌。",
        "formal": "正式、書面化、精準。",
        "casual": "輕鬆口語、朋友聊天語氣。"
    }.get(tone, "自然流暢、口語化但保持禮貌。")

    prompt = (
        f"請將以下內容翻譯成 {style}，語氣風格：{tone_prompt}\n"
        f"- 若為越南語，請根據語境判斷稱謂（如 con, anh, em）。\n"
        f"- 若原文已是目標語言，請直接回覆原文。\n"
        f"- 只輸出翻譯結果，不要附註說明。\n\n"
        f"原文：\n{text}"
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
            "间": "間", "对": "對", "会": "會", "还": "還", "时": "時",
            "后": "後", "国": "國", "两": "兩"
        }
        for k, v in trad.items():
            result = result.replace(k, v)

    cache[cache_key] = result
    save_cache(cache)

    return result

# === LINE 回覆 ===
def line_reply(reply_token: str, text: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}]
    }
    requests.post(LINE_REPLY_API, headers=headers, json=payload)

# === webhook 主程式 ===
@app.post("/webhook")
async def webhook(req: Request):
    body = await req.json()
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

        # 初始設定
        if key not in settings:
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False
            }

        cfg = settings[key]

        # 指令：/help
        if msg_lower == "/help":
            help_text = (
                "📘 ChatGPT 翻譯機器人 – 指令說明\n\n"
                "🧍‍♂️【個人翻譯設定】\n"
                "/set 語言     – 設定翻譯語言\n"
                "/status       – 查看目前設定\n"
                "/on /off      – 開啟或關閉翻譯\n"
                "/reset        – 重設為中文\n\n"
                "🎭【語氣 Tone】\n"
                "/tone normal / formal / casual\n\n"
                "🤖【Smart 智慧翻譯】\n"
                "/smart on     – 中↔越自動判斷\n"
                "/smart off    – 使用固定語言\n\n"
                "🧹【快取管理】\n"
                "/clearcache   – 清除翻譯快取\n\n"
                "🌐【語言列表】\n"
                "/langlist     – 顯示支援語言\n"
            )
            line_reply(reply_token, help_text)
            continue

        # /clearcache
        if msg_lower == "/clearcache":
            save_cache({})
            line_reply(reply_token, "🔄 快取已清除")
            continue

        # /langlist
        if msg_lower == "/langlist":
            lang_list = "🌐 支援語言：中文、英文、越南文、日文、韓文、印尼文、泰文、西班牙文、德文"
            line_reply(reply_token, lang_list)
            continue

        # /tone
        if msg_lower.startswith("/tone "):
            t = msg_lower.split(" ", 1)[1]
            if t in ["normal", "formal", "casual"]:
                cfg["tone"] = t
                save_settings(settings)
                line_reply(reply_token, f"🎙️ 已設定語氣：{t}")
            else:
                line_reply(reply_token, "可選：normal / formal / casual")
            continue

        # smart 模式
        if msg_lower == "/smart on":
            cfg["smart"] = True
            save_settings(settings)
            line_reply(reply_token, "🤖 Smart 模式已啟用")
            continue

        if msg_lower == "/smart off":
            cfg["smart"] = False
            save_settings(settings)
            line_reply(reply_token, "🧩 Smart 模式已關閉")
            continue

        # /set 目標語言
        if msg_lower.startswith("/set "):
            lang = normalize_lang(msg_lower.replace("/set", "").strip())
            cfg["target"] = lang
            cfg["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, f"✅ 已設定：翻譯成 {lang}")
            continue

        # /status
        if msg_lower == "/status":
            st = (
                f"🔧 個人設定\n"
                f"狀態：{'開啟' if cfg['enabled'] else '關閉'}\n"
                f"目標語言：{cfg['target']}\n"
                f"語氣：{cfg['tone']}\n"
                f"Smart：{'ON' if cfg['smart'] else 'OFF'}"
            )
            line_reply(reply_token, st)
            continue

        # on/off/reset
        if msg_lower == "/off":
            cfg["enabled"] = False
            save_settings(settings)
            line_reply(reply_token, "⏸️ 翻譯已關閉")
            continue

        if msg_lower == "/on":
            cfg["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, "▶️ 翻譯已開啟")
            continue

        if msg_lower == "/reset":
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False
            }
            save_settings(settings)
            line_reply(reply_token, "♻️ 已重設為中文")
            continue

        # 自動翻譯
        if cfg.get("enabled", True):
            detected = detect_language(user_msg, cache)

            if cfg["smart"]:
                if detected == "中文":
                    target = "越南文"
                elif detected == "越南文":
                    target = "中文"
                else:
                    target = cfg["target"]
            else:
                target = cfg["target"]

            if detected != target:
                result = translate_text(user_msg, detected, target, cache, tone=cfg["tone"])
                line_reply(reply_token, result)

    return {"status": "ok"}
