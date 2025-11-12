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
    "中文": ["中文","繁中","繁體中文","zh","chinese","cn"],
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

# === 翻譯 ===
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

        # === /help ===
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

        # === 群組設定指令 ===
        if group_id:
            gcfg = get_group_settings(settings, group_id)

            if msg_lower.startswith("/groupset ") or msg_lower.startswith("/gset "):
                langs = [normalize_lang(x) for x in user_msg.split()[1:]]
                gcfg["targets"] = langs
                gcfg["enabled"] = True
                set_group_settings(settings, group_id, gcfg)
                line_reply(reply_token, f"✅ 群組語言設定：{', '.join(langs)}")
                continue

            if msg_lower.startswith("/groupadd ") or msg_lower.startswith("/gadd "):
                tgt = normalize_lang(user_msg.split()[1])
                if tgt not in gcfg["targets"]:
                    gcfg["targets"].append(tgt)
                    set_group_settings(settings, group_id, gcfg)
                line_reply(reply_token, f"✅ 已加入語言：{tgt}\n目前清單：{', '.join(gcfg['targets'])}")
                continue

            if msg_lower.startswith("/groupdel ") or msg_lower.startswith("/gdel "):
                tgt = normalize_lang(user_msg.split()[1])
                if tgt in gcfg["targets"]:
                    gcfg["targets"].remove(tgt)
                    set_group_settings(settings, group_id, gcfg)
                line_reply(reply_token, f"🗑️ 已移除語言：{tgt}\n目前清單：{', '.join(gcfg['targets'])}")
                continue

            if msg_lower in ["/groupstatus", "/gstatus"]:
                onoff = "開啟" if gcfg.get("enabled", True) else "關閉"
                targets = ", ".join(gcfg.get("targets", [])) or "（無）"
                line_reply(reply_token, f"🔧 群組翻譯：{onoff}\n🎯 目標語言：{targets}")
                continue

            if msg_lower in ["/groupoff", "/goff"]:
                gcfg["enabled"] = False
                set_group_settings(settings, group_id, gcfg)
                line_reply(reply_token, "⏸️ 群組翻譯已關閉。")
                continue

            if msg_lower in ["/groupon", "/gon"]:
                gcfg["enabled"] = True
                set_group_settings(settings, group_id, gcfg)
                line_reply(reply_token, "▶️ 群組翻譯已開啟。")
                continue

        # === 個人設定指令 ===
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

        # === 翻譯執行 ===
        user_cfg = settings.get(key, {"enabled": True, "target": "中文"})
        gcfg = get_group_settings(settings, group_id) if group_id else {"enabled": False, "targets": []}

        detected = detect_language(user_msg)

        # 個人設定優先
        if user_cfg.get("enabled", True):
            tgt = user_cfg["target"]
            if tgt != detected:
                result = translate_text(user_msg, detected, tgt)
                line_reply(reply_token, result)
            continue

        # 群組翻譯（若個人關閉）
        if group_id and gcfg.get("enabled", True) and gcfg.get("targets"):
            for tgt in gcfg["targets"]:
                if tgt == detected:
                    continue
                result = translate_text(user_msg, detected, tgt)
                line_reply(reply_token, result)
            continue

    return {"status": "ok"}
