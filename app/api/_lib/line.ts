// app/api/_lib/line.ts
import crypto from "crypto";

export function verifyLineSignature(bodyText: string, signature: string | null) {
  const secret = process.env.LINE_CHANNEL_SECRET || "";
  if (!secret) throw new Error("Missing LINE_CHANNEL_SECRET");
  if (!signature) return false;

  const hash = crypto.createHmac("sha256", secret).update(bodyText).digest("base64");
  return hash === signature;
}

export async function replyLineMessage(replyToken: string, text: string) {
  const accessToken = process.env.LINE_CHANNEL_ACCESS_TOKEN || "";
  if (!accessToken) throw new Error("Missing LINE_CHANNEL_ACCESS_TOKEN");

  const r = await fetch("https://api.line.me/v2/bot/message/reply", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text }],
    }),
  });

  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`LINE reply failed ${r.status}: ${t}`);
  }
}
