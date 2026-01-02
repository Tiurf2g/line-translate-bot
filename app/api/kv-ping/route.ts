export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { kv } from "@vercel/kv";

export async function GET(req: Request) {
  try {
    // 小寫 key 避免奇怪字元
    const key = "kv_ping";
    const value = `ok_${Date.now()}`;

    await kv.set(key, value);
    const got = await kv.get(key);

    return Response.json({
      ok: true,
      wrote: value,
      read: got,
      env: {
        // 只回傳是否存在，不洩漏內容
        KV_REST_API_URL: !!process.env.KV_REST_API_URL,
        KV_REST_API_TOKEN: !!process.env.KV_REST_API_TOKEN,
        VERCEL: !!process.env.VERCEL,
        VERCEL_ENV: process.env.VERCEL_ENV || null,
      },
    });
  } catch (e: any) {
    return Response.json(
      {
        ok: false,
        error: e?.message || String(e),
        name: e?.name || null,
        stack: e?.stack ? String(e.stack).split("\n").slice(0, 8) : null,
        env: {
          KV_REST_API_URL: !!process.env.KV_REST_API_URL,
          KV_REST_API_TOKEN: !!process.env.KV_REST_API_TOKEN,
          VERCEL: !!process.env.VERCEL,
          VERCEL_ENV: process.env.VERCEL_ENV || null,
        },
      },
      { status: 500 }
    );
  }
}
