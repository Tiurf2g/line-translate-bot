export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const FAMILY_GROUP_IDS = (process.env.FAMILY_GROUP_IDS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const payload = {
    ok: true,
    time: new Date().toISOString(),
    env: {
      OPENAI_API_KEY: Boolean(process.env.OPENAI_API_KEY),
      LINE_CHANNEL_ACCESS_TOKEN: Boolean(process.env.LINE_CHANNEL_ACCESS_TOKEN),
      LINE_CHANNEL_SECRET: Boolean(process.env.LINE_CHANNEL_SECRET),

      // ✅ Vercel KV（@vercel/kv）
      KV_REST_API_URL: Boolean(process.env.KV_REST_API_URL),
      KV_REST_API_TOKEN: Boolean(process.env.KV_REST_API_TOKEN),

      // （可留著：若未來又接 Upstash Redis REST）
      UPSTASH_REDIS_REST_URL: Boolean(process.env.UPSTASH_REDIS_REST_URL),
      UPSTASH_REDIS_REST_TOKEN: Boolean(process.env.UPSTASH_REDIS_REST_TOKEN),

      ADMIN_PIN: Boolean(process.env.ADMIN_PIN || process.env.ADMIN_PASS),
      FAMILY_GROUP_IDS_count: FAMILY_GROUP_IDS.length,
      FAMILY_GLOSSARY_KEY: Boolean(process.env.FAMILY_GLOSSARY_KEY),

      OPENAI_MODEL: process.env.OPENAI_MODEL || "gpt-4o-mini",
      VERCEL: Boolean(process.env.VERCEL),
      VERCEL_ENV: process.env.VERCEL_ENV || "",
    },
    links: {
      webhook: "/api/line/webhook",
      admin: "/admin/family-glossary",
    },
  };

  return Response.json(payload, {
    headers: {
      "Cache-Control": "no-store, max-age=0",
      Pragma: "no-cache",
    },
  });
}
