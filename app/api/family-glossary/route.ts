// app/api/family-glossary/route.ts
import { kvGetJson, kvSetJson } from "../_lib/kv";

type GlossaryEntry = {
  zh: string;
  en: string;
  tags?: string[];
  note?: string | null;
};

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";

function normalize(items: GlossaryEntry[]) {
  // 以 zh 當唯一 key 去重（最後寫入者覆蓋）
  const map = new Map<string, GlossaryEntry>();
  for (const it of items || []) {
    const zh = (it.zh || "").trim();
    const en = (it.en || "").trim();
    if (!zh) continue;
    map.set(zh, {
      zh,
      en,
      tags: (it.tags || []).map(t => String(t).trim()).filter(Boolean),
      note: it.note ?? null,
    });
  }
  return Array.from(map.values());
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const force = url.searchParams.get("force") === "true";

  // 可選：快取 TTL（秒）
  const ttl = Number(process.env.FAMILY_GLOSSARY_CACHE_TTL || "20");

  // 你如果想做「短暫快取」可擴充，這裡先保持簡單穩定
  let glossary = await kvGetJson<GlossaryEntry[]>(KEY);
  glossary = normalize(glossary || []);

  // 若 KV 是空的，初始化成空陣列
  if (!glossary) {
    await kvSetJson(KEY, []);
    glossary = [];
  }

  return Response.json({
    ok: true,
    key: KEY,
    count: glossary.length,
    glossary,
    force,
    ttl,
  });
}
