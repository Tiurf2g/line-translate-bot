import { kvGetJson, kvSetJson } from "../_lib/kv";

type GlossaryEntry = { zh: string; en: string; tags?: string[]; note?: string | null };
const KEY = process.env.FACTORY_GLOSSARY_KEY || "factory_glossary_v1";

function normalize(items: GlossaryEntry[]) {
  const map = new Map<string, GlossaryEntry>();
  for (const it of items || []) {
    const zh = (it.zh || "").trim();
    const en = (it.en || "").trim();
    if (!zh) continue;
    map.set(zh, { zh, en, tags: (it.tags || []).map(String).map(t => t.trim()).filter(Boolean), note: it.note ?? null });
  }
  return Array.from(map.values());
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const force = url.searchParams.get("force") === "true";

  let glossary = await kvGetJson<GlossaryEntry[]>(KEY);
  glossary = normalize(glossary || []);

  // 若 KV 是空的，初始化
  if ((glossary?.length ?? 0) === 0) {
    await kvSetJson(KEY, []);
  }

  return Response.json({ ok: true, key: KEY, count: glossary.length, glossary, force });
}
