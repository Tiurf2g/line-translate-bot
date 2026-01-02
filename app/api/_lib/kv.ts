// app/api/_lib/kv.ts
import { kv } from "@vercel/kv";

export async function kvGetRaw(key: string): Promise<string | null> {
  const v = await kv.get<string>(key);
  if (v === null || v === undefined) return null;
  return typeof v === "string" ? v : String(v);
}

export async function kvSetRaw(key: string, value: string): Promise<boolean> {
  await kv.set(key, value);
  return true;
}

export async function kvGetJson<T>(key: string): Promise<T | null> {
  const v = await kv.get<T>(key);
  if (v === null || v === undefined) return null;
  return v;
}

export async function kvSetJson(key: string, value: any): Promise<boolean> {
  await kv.set(key, value);
  return true;
}
