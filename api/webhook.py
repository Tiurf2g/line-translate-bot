# api/webhook.py
from fastapi import FastAPI, Request
import requests, os, json, re
from typing import Dict, Any, List
from openai import OpenAI

app = FastAPI()

# --- Env & constants ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
SETTINGS_FILE = "/tmp/user_settings.json"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

client = OpenAI(api_key=OPENAI_API_KEY)


# --- Utilities: settings persistence ---
def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # why: Vercel /tmp 允許寫，但失敗時不要中斷 webhook
        pass


# --- Language aliases & normalization ---
LANG_ALIASES = {
    "中文": ["中文", "繁中", "zh", "chinese", "zh-tw", "tw", "cn", "zh-hant"],
    "英文": ["英文", "英", "en", "english"],
    "越南文": ["越南文", "越文", "vi", "vietnamese", "vi-vn"],
    "日文": ["日文", "jp", "ja", "japanese"],
    "韓文": ["韓文", "kr", "ko", "korean"],
    "印尼文": ["印尼文", "id", "indonesian", "bahasa"],
    "泰文": ["泰文", "th", "thai"],
    "西班牙文": ["西班牙文", "es", "spanish"],
    "德文": ["德文", "de", "german"],
}


def normalize_lang(name: str) -> str:
    n = (name or "").strip().lower()
    for std, alts in LANG_ALIASES.items():
        if n == std.lower() or n in [a.lower() for a in alts]:
            return std
    return name.strip() or "中文"


# --- Default user config ---
def default_user_conf() -> Dict[str, Any]:
    return {
        "source": "中文",
        "target": "越南文",
        "tone": "casual",
        "unit_locale": "vn",
        "glossary": {},
    }


# --- LINE reply helper ---
def line_reply(reply_token: str, text: str) -> None:
    if not reply_token or not LINE_CHANNEL_ACCESS_TOKEN:
        return
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": (text or "")[:4900]}],
    }
    try:
        requests.post(LINE_REPLY_API, headers=headers, json=payload, timeout=8)
    except Exception:
        # why: 避免 webhook 回 5xx 讓 LINE 重送
        pass


# --- One-shot decide & translate ---
DECIDE_TRANSLATE_SYS = (
    "你是台灣↔越南本地化翻譯專家。只輸出譯文，不要任何解釋、標註或語言名稱。"
    "對話場景以『日常生活、店家聊天、工作協作』優先自然口語。"
    "保留人名、品牌、代碼、網址與表情符號；數字與專有名詞儘量保留原狀。"
    "若涉及金額、日期、量詞：依 unit_locale 本地化（vn=越南格式、tw=台灣格式、none=不轉換）。"
    "語氣遵循 tone（casual|formal|business|street），避免直譯。"
    "若遇到 glossary 中的詞，嚴格使用指定譯法。"
)


def build_prompt(user_text: str, conf: Dict[str, Any]) -> List[Dict[str, str]]:
    cfg = {
        "source": conf.get("source", "中文"),
        "target": conf.get("target", "越南文"),
        "tone": conf.get("tone", "casual"),
        "unit_locale": conf.get("unit_locale", "vn"),
        "glossary": conf.get("glossary", {}),
        "rules": [
            "自動偵測輸入語言。",
            "若輸入語言==source ➜ 譯成 target；若==target ➜ 譯回 source；否則一律譯成 target。",
            "只輸出最終譯文，不要任何多餘內容。",
        ],
    }
    return [
        {"role": "system", "content": DECIDE_TRANSLATE_SYS},
        {
            "role": "user",
            "content": f"CONFIG:\n{json.dumps(cfg, ensure_ascii=False)}\n\nTEXT:\n{user_text}",
        },
    ]


def decide_and_translate(text: str, conf: Dict[str, Any]) -> str:
    try:
        msgs = build_prompt(text, conf)
        res = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=msgs,
            temperature=0,
        )
        return (res.choices[0].message.content or "").strip()
    except Exception:
        # why: OpenAI 失敗時不中斷，回原文避免阻塞
        return text


# --- Commands ---
SET_CMD = re.compile(r"^/set\s+(\S+)\s+(\S+)\s*$", re.IGNORECASE)
TONE_CMD = re.compile(r"^/tone\s+(casual|formal|business|street)\s*$", re.IGNORECASE)
UNIT_CMD = re.compile(r"^/unit\s+(vn|tw|none)\s*$", re.IGNORECASE)
GLOSS_ADD_CMD = re.compile(r"^/glossary\s+add\s+(.+?)=(.+)$", re.IGNORECASE)
GLOSS_LIST_CMD = re.compile(r"^/glossary\s+list\s*$", re.IGNORECASE)
GLOSS_CLEAR_CMD = re.compile(r"^/glossary\s+clear\s*$", re.IGNORECASE)


def handle_commands(user_id: str, text: str, conf: Dict[str, Any]) -> str:
    m = SET_CMD.match(text)
    if m:
        src = normalize_lang(m.group(1))
        tgt = normalize_lang(m.group(2))
        conf["source"], conf["target"] = src, tgt
        return f"✅ 已設定：{src} → {tgt}"

    m = TONE_CMD.match(text)
    if m:
        conf["tone"] = m.group(1).lower()
        return f"✅ 語氣 tone = {conf['tone']}"

    m = UNIT_CMD.match(text)
    if m:
        conf["unit_locale"] = m.group(1).lower()
        return f"✅ 本地化單位/日期/幣別 unit = {conf['unit_locale']}"

    m = GLOSS_ADD_CMD.match(text)
    if m:
        src_term = m.group(1).strip()
        dst_term = m.group(2).strip()
        if src_term and dst_term:
            conf.setdefault("glossary", {})[src_term] = dst_term
            return f"✅ 已加入詞彙：{src_term} => {dst_term}"

    if GLOSS_LIST_CMD.match(text):
        g = conf.get("glossary", {})
        if not g:
            return "（目前詞彙表為空）"
        pairs = [f"- {k} => {v}" for k, v in g.items()]
        return "📘 詞彙表：\n" + "\n".join(pairs)

    if GLOSS_CLEAR_CMD.match(text):
        conf["glossary"] = {}
        return "🗑️ 已清空詞彙表"

    if text in ("/lang", "/設定"):
        return (
            f"🔧 目前設定：{conf['source']} → {conf['target']} | "
            f"tone={conf['tone']} | unit={conf['unit_locale']} | "
            f"glossary={len(conf.get('glossary', {}))} 筆"
        )

    return ""


# --- Webhook endpoints ---
@app.get("/webhook")
def webhook_verify():
    # why: LINE Console 的 Verify 會發 GET，需要回 200 讓它過
    return {"ok": True}


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

        user_text = (msg.get("text") or "").strip()
        if not user_text:
            continue

        reply_token = ev.get("replyToken", "")
        user_id = ev.get("source", {}).get("userId", "")
        if not user_id or not reply_token:
            continue

        user_conf = settings.get(user_id) or default_user_conf()

        cmd_resp = handle_commands(user_id, user_text, user_conf)
        if cmd_resp:
            settings[user_id] = user_conf
            save_settings(settings)
            line_reply(reply_token, cmd_resp)
            continue

        translated = decide_and_translate(user_text, user_conf)
        line_reply(reply_token, translated)

        settings[user_id] = user_conf
        save_settings(settings)

    return {"status": "ok"}


@app.get("/healthz")
def health():
    return {"ok": True}
