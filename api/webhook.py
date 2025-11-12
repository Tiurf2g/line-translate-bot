from fastapi import FastAPI, Request
import requests, os, json, re
from openai import OpenAI

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"

SETTINGS_FILE = "/tmp/user_settings.json"
client = OpenAI(api_key=OPENAI_API_KEY)

# === 基礎設定讀寫 ===
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

# === 語言偵測 ===
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

# === 翻譯（最終版：動態語言支援＋繁體優化） ===
def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    # 判斷目標語言樣式
    if "中" in target_lang:
        style = "自然流暢的繁體中文（台灣用語）"
    else:
        style = target_lang

    prompt = (
        f"請將以下內容翻譯成{style}："
        f"\n- 若為越南語，請根據語境判斷稱謂（如 con, anh, em 等）。\n"
        f"- 若原文已是目標語言，請直接回覆原文即可。\n"
        f"- 請只輸出翻譯結果，不要附註語言名稱或解釋。\n\n"
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

    # 若翻譯成中文則自動繁體化
    if "中" in target_lang:
        replacements = {
            "这": "這", "着": "著", "么": "麼", "为": "為", "于": "於",
            "觉": "覺", "听": "聽", "关": "關", "头": "頭", "电": "電",
            "间": "間", "对": "對", "会": "會", "还": "還", "时": "時",
            "后": "後", "国": "國", "两": "兩"
        }
        for k, v in replacements.items():
            result = result.replace(k, v)

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

# === 群組設定工具 ===
def get_group_settings(all_settings, group_id):
    gs = all_settings.get("group_settings", {})
    return gs.get(group_id, {"enabled": True, "targets": []})

def set_group_settings(all_settings, group_id, cfg):
    gs = all_settings.get("group_settings", {})
    gs[group_id] = cfg
    all_settings["group_settings"] = gs
    save_settings(all_settings)

# === FastAPI 主程式 ===
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
        msg_lower = user_msg.lower()
        reply_token = ev.get("replyToken")
        source = ev.get("source", {})
        group_id = source.get("groupId")
        user_id = source.get("userId")
        if not user_id:
            continue

        # === 指令區（保留原邏輯） ===
        if msg_lower in ["/help", "help", "幫助", "指令"]:
            help_text = (
                "📘 ChatGPT 翻譯機器人 指令說明\n\n"
                "🧍‍♂️【個人設定 / Personal Settings】\n"
                "・設定翻譯 ［語言］ | /set [lang]\n"
                "・查翻譯 | /status\n"
                "・停止翻譯 | /off\n"
                "・開啟翻譯 | /on\n"
                "・重設翻譯 | /reset\n\n"
                "👥【群組設定 / Group Settings】\n"
                "・/groupset 中文 英文 越南文 | /gset zh en vi\n"
                "・/groupadd 英文 | /gadd en\n"
                "・/groupdel 英文 | /gdel en\n"
                "・/groupstatus | /gstatus\n"
                "・/groupoff | /goff\n"
                "・/groupon | /gon\n\n"
                "🌐 支援語言 / Supported Languages：\n"
                "中文、英文、越南文、日文、韓文、印尼文、泰文、西班牙文、德文\n\n"
                "💡規則：個人設定優先於群組設定。"
            )
            line_reply(reply_token, help_text)
            continue

        # === 群組與個人設定 ===
        key = f"user:{user_id}"
        if key not in settings:
            settings[key] = {"enabled": True, "target": "中文"}
            save_settings(settings)

        if user_msg.startswith("設定翻譯 ") or msg_lower.startswith("/set "):
            parts = user_msg.split()
            lang = normalize_lang(parts[-1])
            settings[key] = {"enabled": True, "target": lang}
            save_settings(settings)
            line_reply(reply_token, f"✅ 已設定：所有訊息將翻譯成「{lang}」顯示。")
            continue

        if user_msg in ["查翻譯"] or msg_lower in ["/status"]:
            cfg = settings[key]
            line_reply(reply_token, f"🔧 個人設定：{'開啟' if cfg['enabled'] else '關閉'} → {cfg['target']}")
            continue

        if user_msg in ["停止翻譯"] or msg_lower in ["/off"]:
            settings[key]["enabled"] = False
            save_settings(settings)
            line_reply(reply_token, "⏸️ 個人翻譯已關閉。")
            continue

        if user_msg in ["開啟翻譯"] or msg_lower in ["/on"]:
            settings[key]["enabled"] = True
            save_settings(settings)
            line_reply(reply_token, "▶️ 個人翻譯已開啟。")
            continue

        if user_msg in ["重設翻譯"] or msg_lower in ["/reset"]:
            settings[key] = {"enabled": True, "target": "中文"}
            save_settings(settings)
            line_reply(reply_token, "♻️ 已重設為：翻譯成 中文。")
            continue

        # === 翻譯執行區 ===
        user_cfg = settings.get(key, {"enabled": True, "target": "中文"})
        gcfg = get_group_settings(settings, group_id) if group_id else {"enabled": False, "targets": []}
        detected = detect_language(user_msg)

        # 個人優先
        if user_cfg.get("enabled", True):
            tgt = user_cfg["target"]
            if tgt != detected:
                result = translate_text(user_msg, detected, tgt)
                line_reply(reply_token, result)
            continue

        # 群組翻譯
        if group_id and gcfg.get("enabled", True) and gcfg.get("targets"):
            for tgt in gcfg["targets"]:
                if tgt == detected:
                    continue
                result = translate_text(user_msg, detected, tgt)
                line_reply(reply_token, result)
            continue

    return {"status": "ok"}
