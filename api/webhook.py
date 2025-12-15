import os
import hmac
import hashlib
import base64
import traceback
import time
import requests
from fastapi import FastAPI, Request
from openai import OpenAI

app = FastAPI()

# -------------------------
# ENV
# -------------------------
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------------
# 家庭口語翻譯風格（最終版）
# -------------------------
SYSTEM_TW_TO_VN = """你是一位住在台灣多年的越南人，熟悉夫妻/家庭日常聊天。
請把「台灣人講的口語中文/台語語感」翻成越南人在家裡真的會講的越南話。
要求：
- 用生活口語，不要教科書或新聞腔
- 簡短、自然、像在聊天
- 保留語氣（撒嬌、抱怨、關心、催促）
- 若原文有台語語氣(如啦、咧、喔、欸、吼)，用越南人常用語氣去對應
只輸出翻譯結果，不要加任何前綴或解釋。"""

SYSTEM_VN_TO_TW = """你是一位很懂越南文化的台灣人，常接觸越南家庭口語。
請把越南話翻成台灣人家裡會講的口語中文。
要求：
- 口語、自然、像夫妻聊天
- 不要書面、不用敬語
- 簡短、順口、貼近台灣日常說法
只輸出翻譯結果，不要加任何前綴或解釋。"""

# -------------------------
# 簡易防洗版：記住最近 bot 回過的內容
# (避免同一句再翻、或 LINE 重送事件造成重覆回覆)
# -------------------------
_recent_cache = {}  # key: text, value: expire_ts
CACHE_TTL_SEC = 120  # 2 分鐘

VN_MARKS = set("ăâêôơưđĂÂÊÔƠƯĐ")


def is_vietnamese(text: str) -> bool:
    # 有越南文特有字母就判定越南文
    return any(ch in VN_MARKS for ch in text)


def is_empty_or_noise(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    # 只有符號/表情也跳過（避免亂翻）
    if all(not c.isalnum(
