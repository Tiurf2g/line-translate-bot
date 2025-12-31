// app/api/_lib/kv.ts
export function getKvEnv() {
  // 兼容你之前可能用過的不同命名
  const url =
    process.env.KV_REST_API_URL ||
    process.env.UPSTASH_REDIS_REST_URL ||
    process.env.UPSTASH_REDIS_REST_ENDPOINT;

  const token =
    process.env.KV_REST_API_TOKEN ||
    process.env.UPSTASH_REDIS_REST_TOKEN;

  if (!url || !token) {
    throw new Error("Missing KV env: KV_REST_API_URL/KV_REST_API_TOKEN (or UPSTASH_REDIS_REST_URL/TOKEN)");
  }
  return { url, token };
}

export async function kvGetJson<T>(key: string): Promise<T | null> {
  const { url, token } = getKvEnv();
  const r = await fetch(`${url}/get/${encodeURIComponent(key)}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  const data = await r.json();
  // Upstash REST: { result: "..." } or { result: null }
  if (!data?.result) return null;
  try {
    return JSON.parse(data.result) as T;
  } catch {
    return null;
  }
}

export async function kvSetJson(key: string, value: unknown) {
  const { url, token } = getKvEnv();
  const payload = JSON.stringify(value);
  const r = await fetch(`${url}/set/${encodeURIComponent(key)}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`KV set failed: ${r.status}`);
}
