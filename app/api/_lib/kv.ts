// app/api/_lib/kv.ts
// REST KV helper: 支援 Vercel KV (KV_REST_*) 與 Upstash (UPSTASH_REDIS_REST_*)

function cleanEnv(v?: string) {
  if (!v) return "";
  // 重要：移除所有空白/換行/不可見字元 + 去掉兩側引號
  return v
    .replace(/\s+/g, "")
    .replace(/^["']|["']$/g, "");
}

function normalizeBaseUrl(raw: string) {
  let u = cleanEnv(raw);
  if (!u) return "";

  if (!/^https?:\/\//i.test(u)) u = `https://${u}`;
  u = u.replace(/\/+$/, "");

  try {
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

function hostOf(url: string) {
  try {
    return new globalThis.URL(url).host;
  } catch {
    return url;
  }
}

async function kvFetch(path: string, init?: RequestInit) {
  assertEnv();

  const fullUrl = `${KV_BASE_URL}${path}`;

  let res: Response;
  try {
    res = await fetch(fullUrl, {
      ...init,
      headers: {
        Authorization: `Bearer ${KV_TOKEN}`,
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (err: any) {
    // 把真正的底層原因吐出來（ENOTFOUND / ECONNRESET / ETIMEDOUT…）
    const cause = err?.cause;
    const code = cause?.code || err?.code || "";
    const msg = cause?.message || err?.message || String(err);
    throw new Error(
      `KV fetch failed (${code}): ${msg} | host=${hostOf(KV_BASE_URL)}`
    );
  }

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
