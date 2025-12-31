import crypto from "crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// =========================
// Environment (same as webhook.py)
// =========================
const LINE_CHANNEL_ACCESS_TOKEN = process.env.LINE_CHANNEL_ACCESS_TOKEN || "";
const LINE_CHANNEL_SECRET = process.env.LINE_CHANNEL_SECRET || "";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const FAMILY_GROUP_IDS = process.env.FAMILY_GROUP_IDS || "";

const LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply";

// =========================
// Prompts (copy from webhook.py)
// =========================
const TW_TO_VN_PROMPT = `你是一位住在台灣多年的越南人，
平常在家中與配偶、小孩、長輩用越南話溝通。

任務：
- 把台灣人口語中文，翻成「越南家庭裡真的會講的話」
- 語氣要溫柔、自然、偏生活化
- 可以使用越南人常用的語助詞（如：ừ、ờ、uh、ha、nè、á）
- 適度使用年輕人或家庭常見說法
- 不要書面、不要正式、不要像新聞或課本
- 不要加解釋，只輸出翻譯內容
`;

const VN_TO_TW_PROMPT = `你是一位很懂越南文化的台灣人，
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
`;

const DIRECT_TRANSLATE_PROMPT = `你是一個【中文 ↔ 越南文】專用翻譯器。

規則：
- 如果輸入是中文（繁體或簡體），請翻譯成「越南文」。
- 如果輸入是越南文，請翻譯成「繁體中文」。
- 絕對不要輸出英文。
- 不要加說明、不要加標註、不要加任何前後綴。
- 只輸出翻譯後的文字本身。`;

// =========================
// Language helpers (same as webhook.py)
// =========================
const VN_MARKS = new Set(Array.from("ăâêôơưđĂÂÊÔƠƯĐ"));

const URL_PATTERN = /(https?:\/\/|www\.|line\.me\/|liff\.line\.me\/)/i; // :contentReference[oaicite:1]{index=1}

const FILLER_MAP_TW_TO_VN: Record<string, string> = {
  "嗯": "Uh",
  "嗯嗯": "Uh uh",
  "喔": "Ờ",
  "哦": "Ờ",
  "啊": "À",
};

const VN_FILLERS = new Set(["uh", "ừ", "ờ", "ha", "nè", "á", "a", "à", "ừm", "um", "ừm ừm"]); // :contentReference[oaicite:2]{index=2}

const FILLER_MAP_VN_TO_TW: Record<string, string> = {
  "uh": "嗯",
  "ừ": "嗯",
  "ờ": "喔",
  "ha": "哈",
  "nè": "捏",
  "á": "啊",
  "à": "啊",
  "um": "嗯",
  "ừm": "嗯",
};

function isVietnamese(text: string): boolean {
  const t = (text || "").trim().toLowerCase();
  // Uh 也算越南語助詞 :contentReference[oaicite:3]{index=3}
  if (VN_FILLERS.has(t)) return true;
  for (const ch of text || "") {
    if (VN_MARKS.has(ch)) return true;
  }
  return false;
}

function isNonFamily(event: any): boolean {
  const src = event?.source || {};
  const gid = src.groupId || src.roomId;

  // 私聊/無 groupId -> 非家庭 :contentReference[oaicite:4]{index=4}
  if (!gid) return true;

  const famIds = new Set(
    (FAMILY_GROUP_IDS || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
  );

  if (famIds.size === 0) return true; // :contentReference[oaicite:5]{index=5}
  return !famIds.has(gid); // :contentReference[oaicite:6]{index=6}
}

// =========================
// LINE helpers (same as webhook.py)
// =========================
function verifyLineSignature(rawBody: string, signature: string): boolean {
  if (!LINE_CHANNEL_SECRET || !signature) return false; // :contentReference[oaicite:7]{index=7}
  const mac = crypto.createHmac("sha256", LINE_CHANNEL_SECRET).update(rawBody, "utf8").digest("base64");
  // compare_digest :contentReference[oaicite:8]{index=8}
  return crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(signature));
}

async function replyLine(replyToken: string, text: string) {
  if (!LINE_CHANNEL_ACCESS_TOKEN) {
    console.log("❌ Missing LINE_CHANNEL_ACCESS_TOKEN");
    return;
  }

  const r = await fetch(LINE_REPLY_API, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text }],
    }),
  });

  if (!r.ok) {
    const t = await r.text().catch(() => "");
    console.log("❌ LINE reply failed:", r.status, t); // :contentReference[oaicite:9]{index=9}
  }
}

// =========================
// Translation core (same as webhook.py)
// =========================
async function openAITranslate(system: string, userText: string): Promise<string> {
  // webhook.py：沒 key 回固定字串 :contentReference[oaicite:10]{index=10}
  if (!OPENAI_API_KEY) return "(OPENAI_API_KEY 沒設定)";

  // webhook.py 用 gpt-4o-mini + temperature 0.2 + max_tokens 180 :contentReference[oaicite:11]{index=11}
  const resp = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      temperature: 0.2,
      max_tokens: 180,
      messages: [
        { role: "system", content: system },
        { role: "user", content: userText },
      ],
    }),
  });

  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    throw new Error(`OpenAI error ${resp.status}: ${t}`);
  }

  const data: any = await resp.json();
  return (data?.choices?.[0]?.message?.content || "").trim();
}

async function translateText(text: string, event: any): Promise<string> {
  const t = (text || "").trim();
  if (!t) return "";

  // URL 不翻 :contentReference[oaicite:12]{index=12}
  if (URL_PATTERN.test(t)) return "";

  // 避免 bot 翻自己（🇹🇼/🇻🇳 開頭就跳過）:contentReference[oaicite:13]{index=13}
  if (t.startsWith("🇹🇼") || t.startsWith("🇻🇳")) return "";

  // 1) 語助詞硬規則：優先處理 :contentReference[oaicite:14]{index=14}
  if (!isVietnamese(t) && FILLER_MAP_TW_TO_VN[t]) return FILLER_MAP_TW_TO_VN[t];
  const low = t.toLowerCase();
  if (isVietnamese(t) && FILLER_MAP_VN_TO_TW[low]) return FILLER_MAP_VN_TO_TW[low];

  // 2) 模式選擇：家庭/非家庭 :contentReference[oaicite:15]{index=15}
  let system: string;
  if (isNonFamily(event)) {
    system = DIRECT_TRANSLATE_PROMPT;
  } else {
    system = isVietnamese(t) ? VN_TO_TW_PROMPT : TW_TO_VN_PROMPT;
  }

  let out = await openAITranslate(system, t);

  // 3) 「健保卡」保底修正 :contentReference[oaicite:16]{index=16}
  const srcLow = t.toLowerCase();
  if (
    srcLow.includes("thẻ bảo hiểm y tế") ||
    srcLow.includes("bao hiem y te") ||
    srcLow.includes("bảo hiểm y tế")
  ) {
    out = out.replaceAll("保險卡", "健保卡");
  }

  return out.trim();
}

// =========================
// Health check (optional)
// =========================
export async function GET() {
  return Response.json({
    ok: true,
    msg: "webhook alive",
    openai_key_loaded: Boolean(OPENAI_API_KEY),
    line_token_loaded: Boolean(LINE_CHANNEL_ACCESS_TOKEN),
    secret_loaded: Boolean(LINE_CHANNEL_SECRET),
  });
}

// =========================
// Webhook (same structure as webhook.py)
// =========================
export async function POST(req: Request) {
  try {
    const raw = await req.text();
    const signature = req.headers.get("x-line-signature") || "";

    // webhook.py：Invalid signature 只警告、不中斷 :contentReference[oaicite:17]{index=17}
    if (!verifyLineSignature(raw, signature)) {
      console.log("⚠️ Invalid signature (ignored)");
    }

    const data = JSON.parse(raw || "{}");
    const events = Array.isArray(data?.events) ? data.events : [];

    if (!events.length) return Response.json({ ok: true, message: "No events" }); // :contentReference[oaicite:18]{index=18}

    for (const ev of events) {
      try {
        if (ev?.type !== "message") continue;
        const msg = ev?.message || {};
        if (msg?.type !== "text") continue;

        const replyToken = ev?.replyToken;
        const original = msg?.text || "";

        const translated = await translateText(original, ev);

        // webhook.py：TEST_TOKEN 直接回 JSON :contentReference[oaicite:19]{index=19}
        if (replyToken === "TEST_TOKEN") {
          return Response.json({ ok: true, input: original, translated });
        }

        // 有翻譯才回覆 :contentReference[oaicite:20]{index=20}
        if (translated && replyToken) {
          await replyLine(replyToken, translated);
        }
      } catch {
        // 跟 webhook.py 一樣：單筆錯就跳過
        continue;
      }
    }

    return Response.json({ ok: true }); // :contentReference[oaicite:21]{index=21}
  } catch (e: any) {
    console.log("❌ WEBHOOK_FATAL:", String(e?.message || e));
    return Response.json({ ok: false, error: String(e?.message || e) });
  }
}
