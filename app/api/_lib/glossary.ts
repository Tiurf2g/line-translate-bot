import { kvGetJson, kvSetJson } from "./kv";

export type GlossaryEntryRaw = {
  zh: string;
  vi?: string;
  en?: string; // 舊欄位：自動當 vi
  tags?: string[];
  note?: string | null;
};

export type GlossaryEntry = {
  zh: string;
  vi: string;
  tags?: string[];
  note?: string | null;
};

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const TTL = Number(process.env.FAMILY_GLOSSARY_CACHE_TTL || "20");

let cache: { at: number; items: GlossaryEntry[] } | null = null;

function normalize(items: GlossaryEntryRaw[]) {
  const map = new Map<string, GlossaryEntry>();
  for (const it of items || []) {
    const zh = (it.zh || "").trim();
    const vi = ((it.vi ?? it.en) || "").trim();
    if (!zh) continue;
    map.set(zh, {
      zh,
      vi,
      tags: (it.tags || []).map(String).map((t) => t.trim()).filter(Boolean),
      note: it.note ?? null,
    });
  }
  return Array.from(map.values());
}

export async function getFamilyGlossary() {
  const now = Date.now();
  if (cache && now - cache.at < TTL * 1000) return cache.items;

  const raw = await kvGetJson<GlossaryEntryRaw[]>(KEY);
  if (raw === null) {
    await kvSetJson(KEY, []);
    cache = { at: now, items: [] };
    return [];
  }

  const items = normalize(raw || []);
  cache = { at: now, items };
  return items;
}
