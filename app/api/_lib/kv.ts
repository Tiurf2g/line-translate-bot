// app/api/_lib/kv.ts
// REST KV helper: 支援 Vercel KV (KV_REST_*) 與 Upstash (UPSTASH_REDIS_REST_*)

function cleanEnv(v?: string) {
  if (!v) return "";
  return v.trim().replace(/^["']|["']$/g, "");
}

function normalizeBaseUrl(raw: string) {
  let u = cleanEnv(raw);
  if (!u) return "";

  if (!/^https?:\/\//i.test(u)) u = `https://${u}`;
  u = u.replace(/\/+$/, "");

  try {
    // 這裡不要用 URL 變數名，避免遮蔽全域 URL 類別
    // eslint-disable-next-line no-new
    new globalThis.URL(u);
  } catch {
    throw new Error(`Invalid KV REST URL: ${u}`);
  }
  return u;
}

const KV_BASE_URL = normalizeBaseUrl(
  process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || ""
);

const KV_TOKEN = cleanEnv(
  process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || ""
);

function assertEnv() {
  if (!KV_BASE_URL || !KV_TOKEN) {
    throw new Error("Missing KV_REST_API_URL or KV_REST_API_TOKEN");
  }
}

async function kvFetch(path: string, init?: RequestInit) {
  assertEnv();

  const res = await fetch(`${KV_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${KV_TOKEN}`,
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  const text = await res.text().catch(() => "");
  if (!res.ok) throw new Error(`KV ${res.status}: ${text}`);

  try {
    return JSON.parse(text);
  } catch {
    return { result: null, raw: text };
  }
}

export async function kvGetRaw(key: string): Promise<string | null> {
  const data = await kvFetch(`/get/${encodeURIComponent(key)}`);
  return data?.result ?? null;
}

export async function kvSetRaw(
  key: string,
  value: string,
  opts?: { ex?: number }
): Promise<boolean> {
  const qs =
    opts?.ex && Number.isFinite(opts.ex)
      ? `?EX=${encodeURIComponent(String(opts.ex))}`
      : "";

  await kvFetch(
    `/set/${encodeURIComponent(key)}/${encodeURIComponent(value)}${qs}`,
    { method: "POST" }
  );
  return true;
}

export async function kvGetJson<T>(key: string): Promise<T | null> {
  const raw = await kvGetRaw(key);
  if (raw == null) return null;

  if (typeof raw !== "string") return raw as unknown as T;

  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function kvSetJson(
  key: string,
  value: any,
  opts?: { ex?: number }
): Promise<boolean> {
  return kvSetRaw(key, JSON.stringify(value), opts);
}
