export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const URL = process.env.UPSTASH_REDIS_REST_URL || "";
const TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN || "";

function assertEnv() {
  if (!URL || !TOKEN) {
    throw new Error("Missing UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN");
  }
}

async function upstashFetch(path: string, init?: RequestInit) {
  assertEnv();
  const r = await fetch(`${URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  const text = await r.text().catch(() => "");
  if (!r.ok) {
    throw new Error(`Upstash ${r.status}: ${text}`);
  }
  // Upstash 會回 JSON
  try {
    return JSON.parse(text);
  } catch {
    // 防守：萬一不是 JSON 也不要直接炸在這裡
    return { result: null, raw: text };
  }
}

export async function kvGetRaw(key: string): Promise<string | null> {
  const data = await upstashFetch(`/get/${encodeURIComponent(key)}`);
  return data?.result ?? null;
}

export async function kvGetJson<T>(key: string): Promise<T | null> {
  const raw = await kvGetRaw(key);
  if (raw == null) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function kvSetRaw(key: string, value: string) {
  // Upstash REST: /set/<key>/<value>
  await upstashFetch(`/set/${encodeURIComponent(key)}/${encodeURIComponent(value)}`, { method: "POST" });
  return true;
}

export async function kvSetJson(key: string, value: any) {
  return kvSetRaw(key, JSON.stringify(value));
}
