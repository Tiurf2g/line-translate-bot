// app/api/kv-ping/route.ts
export const runtime = "edge";
export const dynamic = "force-dynamic";

import { getKvEnvStatus, kvGetRaw, kvSetRaw } from "../_lib/kv";

function errToJson(e: any) {
  const msg = e?.message || String(e);
  const cause = (e && typeof e === "object" && "cause" in e) ? (e as any).cause : undefined;

  const causeOut =
    cause && typeof cause === "object"
      ? {
          message: cause.message,
          code: cause.code,
          errno: cause.errno,
          syscall: cause.syscall,
          address: cause.address,
          port: cause.port,
        }
      : cause
      ? { message: String(cause) }
      : null;

  return { message: msg, cause: causeOut };
}

export async function GET() {
  const env = getKvEnvStatus();

  const missing_env = {
    KV_REST_API_URL: env.missing.KV_REST_API_URL,
    KV_REST_API_TOKEN: env.missing.KV_REST_API_TOKEN,
  };

  if (env.missing.KV_REST_API_URL || env.missing.KV_REST_API_TOKEN) {
    return Response.json(
      { ok: false, error: "Missing KV_REST_API_URL or KV_REST_API_TOKEN", missing_env, kv_host: env.parsed ?? null },
      { status: 500 }
    );
  }

  const t0 = Date.now();
  const key = "__kv_ping__";
  const value = `pong:${Date.now()}`;

  try {
    await kvSetRaw(key, value);
    const got = await kvGetRaw(key);
    return Response.json({
      ok: true,
      ms: Date.now() - t0,
      wrote: value,
      read: got,
      kv_host: env.parsed ?? null,
      missing_env,
    });
  } catch (e: any) {
    const info = errToJson(e);
    return Response.json(
      {
        ok: false,
        error: info.message || "fetch failed",
        error_detail: info,
        kv_host: env.parsed ?? null,
        missing_env,
      },
      { status: 500 }
    );
  }
}
