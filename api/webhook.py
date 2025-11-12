from fastapi import FastAPI, Request
import requests, os, json, re
from openai import OpenAI

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

SETTINGS_FILE = "/tmp/user_settings.json"
client = OpenAI(api_key=OPENAI_API_KEY)

# --- 讀寫設定 ---
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

# --- 語言正規化 ---
LANG_ALIASES = {
    "中文": ["中文", "繁中", "zh", "chinese"],
    "英文": ["英文", "英", "en", "english"],
    "越南文": ["越南文", "越文", "vi", "vietnamese"],
    "日文": ["日文", "jp", "ja", "japanese"],
    "韓文": ["韓文", "kr", "ko", "korean"],
    "印尼文": ["印尼文", "id", "indonesian", "bahasa"],
    "泰文": ["泰文", "th", "thai"],
    "西班牙文": ["西班牙文", "es", "spanish"],
    "德文": ["德文", "de", "german"]
}

def normalize_lang(name: str) -> str:
    n = name.strip().lower()
    for std, alts in LANG_ALIASES.items():
        if n == std.lower() or n in [a.lower() for a in alts]:
            return std
    return name.strip()

# --- 語言偵測 ---
def detect_language(text: str) -> str:
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
        lang = res.choices[0].message.content.strip()
        return normalize_lang(lang)
    except Exception:
        return "英文"

# --- 翻譯 ---
def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    prompt = f"直接將以下內容翻譯成{target_lang}，只輸出翻譯結果：\n{text}"
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是翻譯機器，只輸出翻譯結果，不要任何解釋或標註語言。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0
    )
    return res.choices[0].message.content.strip()

# --- LINE 回覆 ---
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

# --- FastAPI 主程式 ---
@app.post("/webhook")
async def webhook(req: Request):
    body = await req.json()
    events = body.get("events", [])
    settings = load_settings()

    for ev in events:
        if ev.get("type") != "message":
            continue
        msg = ev.get("message", {})
        if msg.get("type") != "text":
            continue

        user_msg = msg.get("text", "").strip()
        reply_token = ev.get("replyToken")
        user_id = ev.get("source", {}).get("userId")
        if not user_id:
            continue

        # 預設：中文→越南文
        if user_id not in settings:
            settings[user_id] = {"source": "中文", "target": "越南文"}
            save_settings(settings)

        # --- 指令設定 ---
        if user_msg.startswith("/set "):
            parts = user_msg.split()
            if len(parts) == 3:
                settings[user_id] = {"source": normalize_lang(parts[1]), "target": normalize_lang(parts[2])}
                save_settings(settings)
                line_reply(reply_token, f"✅ 已設定：{parts[1]} → {parts[2]}")
            else:
                line_reply(reply_token, "❌ 格式錯誤，請輸入：/set zh vi")
            continue

        if user_msg in ["/lang", "/設定"]:
            cfg = settings[user_id]
            line_reply(reply_token, f"🔧 目前設定：{cfg['source']} → {cfg['target']}")
            continue

        # --- 翻譯執行 ---
        user_conf = settings[user_id]
        source_lang, target_lang = user_conf["source"], user_conf["target"]
        detected = detect_language(user_msg)

        # 若來源語言等於設定來源則翻譯；反向也支援（對話雙向翻譯）
        if detected == source_lang:
            trans = translate_text(user_msg, source_lang, target_lang)
            line_reply(reply_token, trans)
        elif detected == target_lang:
            trans = translate_text(user_msg, target_lang, source_lang)
            line_reply(reply_token, trans)
        else:
            # 若偵測不到匹配語言就翻譯成使用者的 target
            trans = translate_text(user_msg, detected, target_lang)
            line_reply(reply_token, trans)

    return {"status": "ok"}
