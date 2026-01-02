// app/api/family-glossary/route.ts
export const runtime = "edge";
export const dynamic = "force-dynamic";

import { getKvEnvStatus, kvGetJson, kvSetJson } from "../_lib/kv";

type Entry = {
  zh: string;
  vi?: string;
  en?: string; // legacy
  tags?: string[];
  note?: string | null;
};

type NormEntry = { zh: string; vi: string; tags: string[]; note: string | null };

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";

function normalize(items: Entry[] | null | undefined): NormEntry[] {
  const map = new Map<string, NormEntry>();
  for (const it of items || []) {
    const zh = (it.zh || "").trim();
    const vi = ((it.vi ?? it.en) || "").trim();
    if (!zh || !vi) continue;

    const tags = Array.isArray(it.tags) ? it.tags.map((t) => String(t).trim()).filter(Boolean) : [];
    const note = it.note == null ? null : String(it.note);

    // merge by zh
    map.set(zh, { zh, vi, tags, note });
  }
  return Array.from(map.values()).sort((a, b) => a.zh.localeCompare(b.zh, "zh-Hant"));
}

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

export async function GET(req: Request) {
  const env = getKvEnvStatus();

  // FAMILY_GLOSSARY_KEY is optional (we default), so不列入 missing_env
  const missing_env = {
    KV_REST_API_URL: env.missing.KV_REST_API_URL,
    KV_REST_API_TOKEN: env.missing.KV_REST_API_TOKEN,
    FAMILY_GLOSSARY_KEY: false,
  };

  if (env.missing.KV_REST_API_URL || env.missing.KV_REST_API_TOKEN) {
    return Response.json(
      { ok: false, error: "Missing KV_REST_API_URL or KV_REST_API_TOKEN", missing_env, kv_host: env.parsed ?? null },
      { status: 500 }
    );
  }

  const u = new URL(req.url);
  const force = u.searchParams.get("force") === "true";

  try {
    let raw = await kvGetJson<Entry[]>(KEY);
    let items = normalize(raw);

    if (force && items.length === 0) {
      // 初始化空詞庫（避免前端第一次讀不到）
      await kvSetJson(KEY, []);
      raw = [];
      items = [];
    }

    return Response.json({
      ok: true,
      key: KEY,
      count: items.length,
      glossary: items,
      missing_env,
      kv_host: env.parsed ?? null,
    });
  } catch (e: any) {
    const info = errToJson(e);
    return Response.json(
      {
        ok: false,
        error: info.message || "fetch failed",
        error_detail: info,
        missing_env,
        kv_host: env.parsed ?? null,
      },
      { status: 500 }
    );
  }
}
