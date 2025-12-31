// app/api/line/webhook/route.ts
import { verifyLineSignature, replyLineMessage } from "../../_lib/line";
import { containsUrl, detectLang } from "../../_lib/lang";
import { translateFamily } from "../../_lib/translate";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type LineEvent = {
  type: string;
  replyToken?: string;
  message?: { type: string; text?: string };
};

export async function POST(req: Request) {
  const bodyText = await req.text();
  const signature = req.headers.get("x-line-signature");

  if (!verifyLineSignature(bodyText, signature)) {
    return new Response("Bad signature", { status: 401 });
  }

  const payload = JSON.parse(bodyText || "{}");
  const events: LineEvent[] = Array.isArray(payload?.events) ? payload.events : [];

  // 逐筆處理：只處理文字訊息
  for (const ev of events) {
    if (ev.type !== "message") continue;
    if (!ev.replyToken) continue;

    const msg = ev.message;
    if (!msg || msg.type !== "text") continue;

    const text = (msg.text || "").trim();
    if (!text) continue;

    // 只要有網址就完全不翻不回（你要的：只看誰貼網址）
    if (containsUrl(text)) continue;

    const lang = detectLang(text);
    if (!lang) continue;

    // 越南文 → 繁中；繁中 → 越南文
    const from = lang;
    const to = lang === "vi" ? "zh" : "vi";

    try {
      const out = (await translateFamily(text, from, to)).trim();
      if (!out) continue;
      // 如果翻出來跟原文一樣，就不回（避免垃圾回覆）
      if (out === text) continue;

      await replyLineMessage(ev.replyToken, out);
    } catch (e) {
      // 翻譯失敗就安靜，不要吵群
      continue;
    }
  }

  return Response.json({ ok: true });
}

// LINE 可能會用 GET 打一下（可選）
export async function GET() {
  return Response.json({ ok: true, hint: "POST here from LINE webhook" });
}
