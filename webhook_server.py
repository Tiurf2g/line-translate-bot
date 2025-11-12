from fastapi import FastAPI, Request
import requests, os, json, re
from openai import OpenAI

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

# Vercel 可寫 /tmp（部署或重啟會重置；若要持久化可改用雲端 DB/Redis）
SETTINGS_FILE = "/tmp/user_settings.json"

client = OpenAI(api_key=OPENAI_API_KEY)

# --- 小工具：讀寫設定 ---
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

# --- 語言正規化（別名都收斂成同一寫法） ---
LANG_ALIASES = {
    "中文": ["中文","繁中","繁體中文","zh","chinese","cn","traditional chinese"],
    "英文": ["英文","英","en","english"],
    "越南文": ["越南文","越文","vi","vietnamese"],
    "日文": ["日文","jp","ja","japanese"],
    "韓文": ["韓文","kr","ko","korean"],
    "印尼文": ["印尼文","id","indonesian","bahasa"],
    "泰文": ["泰文","th","thai"],
    "西班牙文": ["西班牙文","西文","es","spanish"],
    "德文": ["德文","de","german"]
}

def normalize_lang(name: str) -> str:
    n = name.strip().lower()
    for std, alts in LANG_ALIASES.items():
        if n == std.lower() or n in [a.lower() for a in alts]:
            return std
    # 若不在別名表，嘗試首字去空白直接回傳原字（讓模型自己處理）
    return name.strip()

# --- 呼叫 OpenAI：語言偵測 + 翻譯 ---
def detect_language(text: str) -> str:
    prompt = (
        "請判斷以下句子的語言種類，僅回「中文、英文、越南文、日文、韓文、印尼文、泰文、西班牙文、德文」之一；"
        "若不屬於以上，請回「英文」作為預設。\n\n句子：\n" + text
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

def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    prompt = (
        f"請將以下文字從「{source_lang}」翻譯成「{target_lang}」。"
        "保留原意、自然口語，專業名詞請保留原文或加註括號。\n\n"
        f"文字：\n{text}"
    )
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是專業多語翻譯員"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2
    )
    return res.choices[0].message.content.strip()

# --- 回覆到 LINE ---
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

# --- 指令解析 ---
SET_CMD = re.compile(r"^設定翻譯成\s+(.+)$")
HELP_TEXT = (
    "⚙️ 翻譯設定指令：\n"
    "・設定翻譯成 中文｜英文｜越南文｜日文｜韓文｜印尼文｜泰文｜西班牙文｜德文\n"
    "・查詢翻譯設定\n"
    "・停止翻譯 / 開啟翻譯\n"
    "・重設翻譯"
)

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

        source = ev.get("source", {})
        user_id = source.get("userId")
        # 個人偏好（群組內也能抓到 userId）
        key = f"user:{user_id}" if user_id else "fallback"

        # 初始預設
        if key not in settings:
            settings[key] = {"enabled": True, "target": "中文"}
            save_settings(settings)

        # --- 指令：設定翻譯成 X ---
        m = SET_CMD.match(user_msg)
        if m:
            target_raw = m.group(1)
            target_std = normalize_lang(target_raw)
            settings[key]["target"] = target_std
            settings[key]["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, f"✅ 已設定翻譯目標：{target_std}\n\n{HELP_TEXT}")
            continue

        # --- 其它指令 ---
        if user_msg in ["查詢翻譯設定", "查詢翻譯", "查設定"]:
            state = settings[key]
            line_reply(reply_token, f"🔧 目前設定：\n・狀態：{'開啟' if state['enabled'] else '停止'}\n・目標語言：{state['target']}")
            continue

        if user_msg in ["停止翻譯", "暫停翻譯"]:
            settings[key]["enabled"] = False
            save_settings(settings)
            line_reply(reply_token, "⏸️ 已停止翻譯。如需恢復請輸入：開啟翻譯")
            continue

        if user_msg in ["開啟翻譯", "啟用翻譯"]:
            settings[key]["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, "▶️ 已開啟翻譯。")
            continue

        if user_msg in ["重設翻譯", "重置翻譯"]:
            settings[key] = {"enabled": True, "target": "中文"}
            save_settings(settings)
            line_reply(reply_token, f"♻️ 已重設為預設：翻譯成 中文\n\n{HELP_TEXT}")
            continue

        # --- 非指令：做翻譯 ---
        if not settings[key]["enabled"]:
            # 關閉狀態就不回
            continue

        target_lang = settings[key]["target"]
        source_lang = detect_language(user_msg)

        # 避免源=目標直接平行輸出，仍可選擇翻一次（視你偏好）
        if source_lang == target_lang:
            line_reply(reply_token, f"🔍 語言判定：{source_lang}\n（目標語言相同，已略過翻譯）")
            continue

        try:
            result = translate_text(user_msg, source_lang, target_lang)
            line_reply(
                reply_token,
                f"🔍 語言判定：{source_lang}\n🌐 翻譯成 {target_lang}：\n{result}"
            )
        except Exception as e:
            line_reply(reply_token, f"⚠️ 翻譯失敗：{e}\n你可輸入：{HELP_TEXT}")

    return {"status": "ok"}
