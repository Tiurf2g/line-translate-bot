import os
import hmac
import hashlib
import base64
import traceback
import requests
import re
from fastapi import FastAPI, Request
from openai import OpenAI

app = FastAPI()

# =========================
# Environment
# =========================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FAMILY_GROUP_IDS = os.getenv("FAMILY_GROUP_IDS", "")

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# Prompts
# =========================
TW_TO_VN_PROMPT = """你是一位住在台灣多年的越南人，
平常在家中與配偶、小孩、長輩用越南話溝通。

任務：
- 把台灣人口語中文，翻成「越南家庭裡真的會講的話」
- 語氣要溫柔、自然、偏生活化
- 可以使用越南人常用的語助詞（如：ừ、ờ、uh、ha、nè、á）
- 適度使用年輕人或家庭常見說法
- 不要書面、不要正式、不要像新聞或課本
- 不要加解釋，只輸出翻譯內容
"""

VN_TO_TW_PROMPT = """你是一位很懂越南文化的台灣人，
長期接觸越南家庭、夫妻與親子對話。

任務：
- 把越南口語翻成「台灣人在家裡真的會講的中文」
- 可以出現「嗯、喔、啊、欸、啦、耶」等口語語氣
- 翻成自然、不刺耳、不生硬的生活中文
- 不要太完整句、不要像作文

重要規則（台灣在地用語）：
- "thẻ bảo hiểm y tế" 一律翻成「健保卡」
- 不可翻成「保險卡」
- 牽涉小孩/看醫生/證件/卡片時，優先使用台灣家庭常用說法

不要加解釋，只輸出翻譯內容
"""

DIRECT_TRANSLATE_PROMPT = """你是一個【中文 ↔ 越南文】專用翻譯器。

規則：
- 如果輸入是中文（繁體或簡體），請翻譯成「越南文」。
- 如果輸入是越南文，請翻譯成「繁體中文」。
- 絕對不要輸出英文。
- 不要加說明、不要加標註、不要加任何前後綴。
- 只輸出翻譯後的文字本身。"""

# =========================
# Language helpers
# =========================
VN_MARKS = set("ăâêôơưđĂÂÊÔƠƯĐ")

# 連結 / 網頁分享：不翻譯（避免群組被洗版）
URL_PATTERN = re.compile(r"(https?://|www\.|line\.me/|liff\.line\.me/)")

# --- Filler / 語助詞：硬規則（不走模型，穩、快、準） ---
FILLER_MAP_TW_TO_VN = {
    "嗯": "Uh",
    "嗯嗯": "Uh uh",
    "喔": "Ờ",
    "哦": "Ờ",
    "啊": "À",
}

# 越南常見語助詞（含你要的 Uh）
VN_FILLERS = {"uh", "ừ", "ờ", "ha", "nè", "á", "a", "à", "ừm", "um", "ừm ừm"}

FILLER_MAP_VN_TO_TW = {
    "uh": "嗯",
    "ừ": "嗯",
    "ờ": "喔",
    "ha": "哈",
    "nè": "捏",
    "á": "啊",
    "à": "啊",
    "um": "嗯",
    "ừm": "嗯",
}


def is_vietnamese(text: str) -> bool:
    t = (text or "").strip().lower()
    # 讓 Uh 這種沒有重音的越南語助詞，也能被判定為越南文
    if t in VN_FILLERS:
        return True
    return any(ch in VN_MARKS for ch in (text or ""))


def is_non_family(event: dict) -> bool:
    """
    True  = 非家庭模式（直翻）
    False = 家庭模式（生活化）
    """
    src = (event or {}).get("source") or {}
    gid = src.get("groupId") or src.get("roomId")

    # curl / 私聊 / 無 groupId
    if not gid:
        return True

    fam_ids = {x.strip() for x in FAMILY_GROUP_IDS.split(",") if x.strip()}
    if not fam_ids:
        return True

    return gid not in fam_ids


# =========================
# LINE helpers
# =========================
def verify_line_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    mac = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def reply_line(reply_token: str, text: str):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ Missing LINE_CHANNEL_ACCESS_TOKEN")
        return

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    r = requests.post(LINE_REPLY_API, headers=headers, json=payload, timeout=10)
    if r.status_code != 200:
        print("❌ LINE reply failed:", r.status_code, r.text)


# =========================
# Translation core
# =========================
def translate_text(text: str, event: dict) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    # 網頁 / 連結分享：不翻譯，保持單純網址即可
    if URL_PATTERN.search(text):
        return ""

    # 避免 bot 翻自己（你之前不想顯示國別前綴，所以保留這個保護就好）
    if text.startswith("🇹🇼") or text.startswith("🇻🇳"):
        return ""

    # --- 1) 語助詞硬規則：優先處理（穩、快、準） ---
    # 中文 fillers -> 越南
    if not is_vietnamese(text) and text in FILLER_MAP_TW_TO_VN:
        return FILLER_MAP_TW_TO_VN[text]

    # 越南 fillers -> 中文（含 Uh）
    t_low = text.lower()
    if is_vietnamese(text) and t_low in FILLER_MAP_VN_TO_TW:
        return FILLER_MAP_VN_TO_TW[t_low]

    # --- 2) 模式選擇 ---
    # 非家庭 → 直翻
    if is_non_family(event):
        system = DIRECT_TRANSLATE_PROMPT
    else:
        # 家庭模式：判語言決定 prompt
        system = VN_TO_TW_PROMPT if is_vietnamese(text) else TW_TO_VN_PROMPT

    if not OPENAI_API_KEY:
        return "(OPENAI_API_KEY 沒設定)"

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
        max_tokens=180,
    )

    out = (resp.choices[0].message.content or "").strip()

    # --- 3) 台灣在地名詞保底：避免「健保卡」被翻成「保險卡」 ---
    # 只要輸入明顯在講越南的「健保卡」概念，就強制修正一次
    # （即使 prompt 失手也救得回來）
    src_low = text.lower()
    if ("thẻ bảo hiểm y tế" in src_low or "bao hiem y te" in src_low or "bảo hiểm y tế" in src_low):
        out = out.replace("保險卡", "健保卡")

    return out


# =========================
# Health check
# =========================
@app.get("/")
@app.get("/api/webhook")
def alive():
    return {
        "ok": True,
        "msg": "webhook alive",
        "openai_key_loaded": bool(OPENAI_API_KEY),
        "line_token_loaded": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "secret_loaded": bool(LINE_CHANNEL_SECRET),
    }


# =========================
# Webhook
# =========================
@app.post("/")
@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        body = await request.body()
        signature = request.headers.get("x-line-signature", "")

        if not verify_line_signature(body, signature):
            print("⚠️ Invalid signature (ignored)")

        data = await request.json()
        events = data.get("events", [])

        if not events:
            return {"ok": True, "message": "No events"}

        for ev in events:
            if ev.get("type") != "message":
                continue
            msg = ev.get("message", {})
            if msg.get("type") != "text":
                continue

            reply_token = ev.get("replyToken")
            original = msg.get("text", "")

            translated = translate_text(original, ev)

            # curl 測試
            if reply_token == "TEST_TOKEN":
                return {
                    "ok": True,
                    "input": original,
                    "translated": translated,
                }

            if translated and reply_token:
                reply_line(reply_token, translated)

        return {"ok": True}

    except Exception as e:
        print("❌ WEBHOOK_FATAL:", repr(e))
        print(traceback.format_exc())
        return {"ok": False, "error": repr(e)}
