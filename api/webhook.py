from fastapi import FastAPI, Request
import requests, os, json, re
from openai import OpenAI

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

SETTINGS_FILE = "/tmp/user_settings.json"
CACHE_FILE = "/tmp/translate_cache.json"
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

    except Exception:
        return "英文"

# === 翻譯（含 Tone + SMART + Cache） ===
def translate_text(text: str, source_lang: str, target_lang: str, cache, tone="normal"):
    cache_key = f"trans::{source_lang}->{target_lang}::{tone}::{text}"
    if cache_key in cache:
        return cache[cache_key]

    style = "自然流暢的繁體中文（台灣用語）" if "中" in target_lang else target_lang

    tone_prompt = {
        "normal": "自然流暢、口語化但保持禮貌。",
        "formal": "正式、書面化、精準。",
        "casual": "輕鬆口語、朋友聊天語氣。"
    }.get(tone, "自然流暢")

    prompt = (
        f"請將以下內容翻譯成 {style}，語氣風格：{tone_prompt}。\n"
        f"- 若為越南語，請根據語境判斷稱謂（如 con, anh, em）。\n"
        f"- 若原文已是目標語言，請直接回覆原文。\n\n"
        f"原文：\n{text}"
    )

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"你是專業翻譯員。"},
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

# === 主 webhook ===
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
        user_id = ev.get("source", {}).get("userId", "anonymous")

        # === 初始化使用者設定 ===
        key = f"user:{user_id}"
        if key not in settings:
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False
            }

        cfg = settings[key]

        # ========== 指令區 ==========

        # /help（智能版）
        clean = re.sub(r"[^\w\u4e00-\u9fff]", "", msg_lower).strip()
        if clean in ["help", "幫助", "指令"]:
            help_text = (
                "📘 ChatGPT 翻譯機器人 – 指令說明\n\n"
                "🧍‍♂️【個人翻譯設定】\n"
                "/set 語言     – 設定翻譯語言\n"
                "/status       – 查看目前設定\n"
                "/on           – 開啟翻譯\n"
                "/off          – 關閉翻譯\n"
                "/reset        – 重設為中文翻譯\n\n"
                "🎭【語氣 Tone】\n"
                "/tone normal  – 一般自然語氣\n"
                "/tone formal  – 正式書面語\n"
                "/tone casual  – 朋友聊天語氣\n\n"
                "🤖【Smart 智慧翻譯】\n"
                "/smart on     – 自動判斷語言方向\n"
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
            line_reply(reply_token, "🔄 翻譯快取已清除。")
            continue

        # /langlist
        if msg_lower == "/langlist":
            lang_list = (
                "🌐 支援語言列表：\n"
                "中文（zh）\n英文（en）\n越南文（vi）\n日文（ja）\n"
                "韓文（ko）\n印尼文（id）\n泰文（th）\n西班牙文（es）\n德文（de）"
            )
            line_reply(reply_token, lang_list)
            continue

        # /tone
        if msg_lower.startswith("/tone "):
            tone = msg_lower.replace("/tone", "").strip()
            if tone not in ["normal", "formal", "casual"]:
                line_reply(reply_token, "🎭 語氣請選：normal / formal / casual")
                continue
            cfg["tone"] = tone
            save_settings(settings)
            line_reply(reply_token, f"🎙️ 已設定語氣為：{tone}")
            continue

        # Smart 開關
        if msg_lower == "/smart on":
            cfg["smart"] = True
            save_settings(settings)
            line_reply(reply_token, "🤖 Smart 智慧模式已啟用。")
            continue
        if msg_lower == "/smart off":
            cfg["smart"] = False
            save_settings(settings)
            line_reply(reply_token, "🧩 Smart 模式已關閉。")
            continue

        # 基本指令
        if msg_lower.startswith("/set ") or user_msg.startswith("設定翻譯 "):
            parts = user_msg.split()
            lang = normalize_lang(parts[-1])
            cfg["enabled"] = True
            cfg["target"] = lang
            save_settings(settings)
            line_reply(reply_token, f"✅ 已設定：翻譯成「{lang}」。")
            continue

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

        if msg_lower == "/off":
            cfg["enabled"] = False
            save_settings(settings)
            line_reply(reply_token, "⏸️ 翻譯已關閉。")
            continue

        if msg_lower == "/on":
            cfg["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, "▶️ 翻譯已開啟。")
            continue

        if msg_lower == "/reset":
            settings[key] = {
                "enabled": True,
                "target": "中文",
                "tone": "normal",
                "smart": False
            }
            save_settings(settings)
            line_reply(reply_token, "♻️ 已重設為翻譯成中文。")
            continue

        # ========== 自動翻譯邏輯 ==========
        if cfg.get("enabled", True):

            detected = detect_language(user_msg, cache)

            # SMART 模式：自動方向
            if cfg.get("smart", False):

                if detected == "中文":
                    target = "越南文"
                elif detected == "越南文":
                    target = "中文"
                else:
                    target = cfg["target"]   # 其他語言維持原本 target

            else:
                target = cfg["target"]

            if detected != target:
                result = translate_text(
                    user_msg, detected, target, cache, tone=cfg.get("tone", "normal")
                )
                line_reply(reply_token, result)

    return {"status": "ok"}
