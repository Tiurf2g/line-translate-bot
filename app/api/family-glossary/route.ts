import { kvGetJson, kvSetJson } from "../_lib/kv";

type GlossaryEntryRaw = { zh: string; vi?: string; en?: string; tags?: string[]; note?: string | null };
type GlossaryEntry = { zh: string; vi: string; tags?: string[]; note?: string | null };

// ✅ 統一用 FAMILY_GLOSSARY_KEY
const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";

// ✅ 向下相容：如果你之前錯存到 FACTORY_GLOSSARY_KEY，就幫你把舊資料搬過來
const LEGACY_KEY = process.env.FACTORY_GLOSSARY_KEY || "factory_glossary_v1";

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

export async function GET(req: Request) {
  const url = new URL(req.url);
  const force = url.searchParams.get("force") === "true";

  let glossary = normalize((await kvGetJson<GlossaryEntryRaw[]>(KEY)) || []);

  // 如果家庭 key 是空的，但 legacy 有資料 → 自動搬過來（避免你之前存錯 key 造成「明明有存但吃不到」）
  if (glossary.length === 0 && LEGACY_KEY && LEGACY_KEY !== KEY) {
    const legacy = normalize((await kvGetJson<GlossaryEntryRaw[]>(LEGACY_KEY)) || []);
    if (legacy.length > 0) {
      await kvSetJson(KEY, legacy);
      glossary = legacy;
    }
  }

  // 若 KV 是 null，初始化
  const rawNow = await kvGetJson<GlossaryEntryRaw[]>(KEY);
  if (rawNow === null) {
    await kvSetJson(KEY, []);
  }

  return Response.json({ ok: true, key: KEY, count: glossary.length, glossary, force });
}
