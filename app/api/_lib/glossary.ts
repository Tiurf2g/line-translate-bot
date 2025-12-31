// app/api/_lib/glossary.ts
import { kvGetJson, kvSetJson } from "./kv";

export type GlossaryEntry = {
  zh: string;        // 原文 key（你後台用 zh 當 key）
  en: string;        // 這裡沿用你既有欄位名：en（實際可放「翻譯目標詞」）
  tags?: string[];
  note?: string | null;
};

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const TTL = Number(process.env.FAMILY_GLOSSARY_CACHE_TTL || "20");

let cache: { at: number; items: GlossaryEntry[] } | null = null;

function normalize(items: GlossaryEntry[]) {
  const map = new Map<string, GlossaryEntry>();
  for (const it of items || []) {
    const zh = (it.zh || "").trim();
    const en = (it.en || "").trim();
    if (!zh) continue;
    map.set(zh, { zh, en, tags: it.tags || [], note: it.note ?? null });
  }
  return Array.from(map.values());
}

export async function getFamilyGlossary(): Promise<GlossaryEntry[]> {
  const now = Date.now();
  if (cache && now - cache.at < TTL * 1000) return cache.items;

  const raw = await kvGetJson<GlossaryEntry[]>(KEY);
  if (raw === null) {
    await kvSetJson(KEY, []);
    cache = { at: now, items: [] };
    return [];
  }

  const items = normalize(raw);
  cache = { at: now, items };
  return items;
}
