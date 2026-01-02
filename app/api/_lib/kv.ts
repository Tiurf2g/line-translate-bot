// app/api/_lib/kv.ts
// REST KV helper: 支援 Vercel KV (KV_REST_*) 與 Upstash (UPSTASH_REDIS_REST_*)

function cleanEnv(v?: string) {
  if (!v) return "";
  // 去掉前後空白、換行、以及不小心貼上的引號
  return v.trim().replace(/^["']|["']$/g, "");
}

function normalizeBaseUrl(raw: string) {
  let u = cleanEnv(raw);
  if (!u) return "";

  // 有些人會只貼 domain，補上 https://
  if (!/^https?:\/\//i.test(u)) u = `https://${u}`;

  // 去掉尾端 /
  u = u.replace(/\/+$/, "");

  // 驗證 URL 合法（不合法會直接 throw，避免 fetch failed）
  try {
    // eslint-disable-next-line no-new
    new URL(u);
  } catch {
    throw new Error(`Invalid KV REST URL: ${u}`);
  }
  return u;
}

const URL =
  normalizeBaseUrl(
    process.env.KV_REST_API_URL ||
      process.env.UPSTASH_REDIS_REST_URL ||
      ""
  );

const TOKEN = cleanEnv(
  process.env.KV_REST_API_TOKEN ||
    process.env.UPSTASH_REDIS_REST_TOKEN ||
    ""
);

function assertEnv() {
  if (!URL || !TOKEN) {
    throw new Error("Missing KV_REST_API_URL or KV_REST_API_TOKEN");
  }
}

async function kvFetch(path: string, init?: RequestInit) {
  assertEnv();

  const res = await fetch(`${URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
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
