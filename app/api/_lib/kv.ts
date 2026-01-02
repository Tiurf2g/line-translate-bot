// app/api/_lib/kv.ts
// REST KV helper: 支援 Vercel KV (KV_REST_*) 與 Upstash (UPSTASH_REDIS_REST_*)

const URL =
  process.env.KV_REST_API_URL ||
  process.env.UPSTASH_REDIS_REST_URL ||
  "";

const TOKEN =
  process.env.KV_REST_API_TOKEN ||
  process.env.UPSTASH_REDIS_REST_TOKEN ||
  "";

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
  // Upstash REST: /set/<key>/<value>
  // TTL: /set/<key>/<value>?EX=seconds (或 ex=)
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

  // 有些情況可能已經是物件，保守處理
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
