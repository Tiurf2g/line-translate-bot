export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { kv } from "@vercel/kv";

export async function GET() {
  await kv.set("kv_ping", "ok");
  const v = await kv.get("kv_ping");
  return Response.json({ ok: true, kv_ping: v });
}
