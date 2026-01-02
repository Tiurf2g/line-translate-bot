export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function bool(v?: string) {
  return Boolean((v || "").trim());
}

export async function GET() {
  const env = {
    OPENAI_API_KEY: bool(process.env.OPENAI_API_KEY),
    LINE_CHANNEL_SECRET: bool(process.env.LINE_CHANNEL_SECRET),
    LINE_CHANNEL_ACCESS_TOKEN: bool(process.env.LINE_CHANNEL_ACCESS_TOKEN),
    UPSTASH_REDIS_REST_URL: bool(process.env.UPSTASH_REDIS_REST_URL),
    UPSTASH_REDIS_REST_TOKEN: bool(process.env.UPSTASH_REDIS_REST_TOKEN),
    ADMIN_PIN: bool(process.env.ADMIN_PIN || process.env.ADMIN_PASS),
    FAMILY_GROUP_IDS_count: (process.env.FAMILY_GROUP_IDS || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean).length,
  };

  return Response.json({
    ok: true,
    time: new Date().toISOString(),
    env,
    links: {
      webhook: "/api/line/webhook",
      admin: "/admin/family-glossary",
    },
  });
}
