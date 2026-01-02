// app/api/_lib/kv.ts
// KV helper for Vercel KV (Upstash Redis REST).
// Uses KV_REST_API_URL + KV_REST_API_TOKEN (preferred), with fallback to UPSTASH_REDIS_REST_URL/TOKEN.
// Works in both Node.js and Edge runtimes.

import { createClient } from "@vercel/kv";

export type KvEnvStatus = {
  url: string;
  token: string;
  missing: {
    KV_REST_API_URL: boolean;
    KV_REST_API_TOKEN: boolean;
  };
  // For debugging (safe): hostname/protocol only, no token.
  parsed?: { protocol: string; host: string };
};

export function getKvEnvStatus(): KvEnvStatus {
  const url = (process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || "").trim();
  const token = (process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || "").trim();

  const status: KvEnvStatus = {
    url,
    token,
    missing: {
      KV_REST_API_URL: !url,
      KV_REST_API_TOKEN: !token,
    },
  };

  if (url) {
    try {
      const u = new globalThis.URL(url);
      status.parsed = { protocol: u.protocol, host: u.host };
    } catch {
      // leave parsed undefined; route handlers can show a friendlier error
    }
  }

  return status;
}

function getClient() {
  const { url, token, missing } = getKvEnvStatus();
  if (missing.KV_REST_API_URL || missing.KV_REST_API_TOKEN) {
    throw new Error("Missing KV_REST_API_URL or KV_REST_API_TOKEN");
  }

  // Disable auto-deserialization so we control JSON parsing ourselves.
  // (Some setups have reported surprising nulls when relying on
  // generic deserialization.)
  return createClient({
    url,
    token,
    automaticDeserialization: false,
  });
}

export async function kvGetRaw(key: string): Promise<string | null> {
  const kv = getClient();
  const v = (await kv.get(key)) as unknown;
  if (v === null || v === undefined) return null;
  return String(v);
}

export async function kvSetRaw(key: string, value: string): Promise<void> {
  const kv = getClient();
  await kv.set(key, value);
}

export async function kvGetJson<T = any>(key: string): Promise<T | null> {
  const raw = await kvGetRaw(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    // If it wasn't JSON, return as-is (typed as any).
    return raw as any;
  }
}

export async function kvSetJson(key: string, value: unknown): Promise<void> {
  await kvSetRaw(key, JSON.stringify(value));
}

// Safe KV host info for debugging (no secrets)
export function kvHostInfo() {
  return getKvEnvStatus().parsed || null;
}
