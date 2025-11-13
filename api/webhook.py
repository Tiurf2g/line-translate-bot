from fastapi import FastAPI, Request
import requests, os, json, re
from openai import OpenAI

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

SETTINGS_FILE = "/tmp/user_settings.json"
CACHE_FILE = "/tmp/translate_cache.json"   # ⭐ 翻譯快取
client = OpenAI(api_key=OPENAI_API_KEY)

# === 快取讀寫 ===
def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# === 設定讀寫 ===
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
        return cache[cache_key]  # ⭐ 使用快取（不花 Token）

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

    except Exception:
        return "英文"

# === 翻譯（含快取） ===
def translate_text(text: str, source_lang: str, target_lang: str, cache):
    cache_key = f"trans::{source_lang}->{target_lang}::{text}"

    # ⭐ 直接命中快取
    if cache_key in cache:
        return cache[cache_key]

    # 判斷目標語言樣式
    style = "自然流暢的繁體中文（台灣用語）" if "中" in target_lang else target_lang

    prompt = (
        f"請將以下內容翻譯成{style}："
        f"\n- 若為越南語，請根據語境判斷稱謂（如 con, anh, em 等）。"
        f"\n- 若原文已是目標語言，請直接回覆原文即可。"
        f"\n- 請只輸出翻譯結果，不要附註語言名稱或解釋。\n\n"
        f"原文：\n{text}"
    )

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"你是專業翻譯員，負責翻譯成 {style}。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3
    )

    result = res.choices[0].message.content.strip()

    # 繁體化
    if "中" in target_lang:
        replacements = {
            "这": "這", "着": "著", "么": "麼", "为": "為", "于": "於",
            "觉": "覺", "听": "聽", "关": "關", "头": "頭", "电": "電",
            "间": "間", "对": "對", "会": "會", "还": "還", "时": "時",
            "后": "後", "国": "國", "两": "兩"
        }
        for k, v in replacements.items():
            result = result.replace(k, v)

    # ⭐ 儲存快取
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

# === 主程式 ===
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
        source = ev.get("source", {})
        user_id = source.get("userId", "anonymous")

        # === 個人設定初始化 ===
        key = f"user:{user_id}"
        if key not in settings:
            settings[key] = {"enabled": True, "target": "中文"}

        # === 指令 ===
        if msg_lower.startswith("/set ") or user_msg.startswith("設定翻譯 "):
            parts = user_msg.split()
            lang = normalize_lang(parts[-1])
            settings[key] = {"enabled": True, "target": lang}
            save_settings(settings)
            line_reply(reply_token, f"✅ 已設定：翻譯成「{lang}」。")
            continue

        if msg_lower == "/status" or user_msg == "查翻譯":
            cfg = settings[key]
            line_reply(reply_token, f"🔧 個人設定：{'開啟' if cfg['enabled'] else '關閉'} → {cfg['target']}")
            continue

        if msg_lower == "/off" or user_msg == "停止翻譯":
            settings[key]["enabled"] = False
            save_settings(settings)
            line_reply(reply_token, "⏸️ 個人翻譯已關閉。")
            continue

        if msg_lower == "/on" or user_msg == "開啟翻譯":
            settings[key]["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, "▶️ 個人翻譯已開啟。")
            continue

        if msg_lower == "/reset" or user_msg == "重設翻譯":
            settings[key] = {"enabled": True, "target": "中文"}
            save_settings(settings)
            line_reply(reply_token, "♻️ 已重設為翻譯成：中文")
            continue

        # === 自動翻譯 ===
        cfg = settings[key]
        if cfg.get("enabled", True):
            detected = detect_language(user_msg, cache)
            target = cfg["target"]

            if detected != target:
                result = translate_text(user_msg, detected, target, cache)
                line_reply(reply_token, result)

    return {"status": "ok"}
