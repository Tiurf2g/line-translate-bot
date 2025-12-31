// app/api/admin/family-glossary/route.ts
import { kvGetJson, kvSetJson } from "../../_lib/kv";

type GlossaryEntry = {
  zh: string;
  en: string;
  tags?: string[];
  note?: string | null;
};

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const ADMIN_PIN = process.env.ADMIN_PASS || process.env.ADMIN_PIN || "";

function assertPin(req: Request) {
  const pin = req.headers.get("x-admin-pin") || "";
  if (!ADMIN_PIN) throw new Error("ADMIN_PIN not set");
  if (pin !== ADMIN_PIN) throw new Error("Unauthorized");
}

function normalize(items: GlossaryEntry[]) {
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

export async function POST(req: Request) {
  try {
    assertPin(req);

    const body = await req.json().catch(() => ({}));
    const action = String(body?.action || "");

    const current = normalize((await kvGetJson<GlossaryEntry[]>(KEY)) || []);

    if (action === "reset") {
      await kvSetJson(KEY, []);
      return Response.json({ ok: true, action, count: 0 });
    }

    if (action === "upsert") {
      const entry: GlossaryEntry = body?.entry;
      const zh = (entry?.zh || "").trim();
      if (!zh) return Response.json({ ok: false, error: "zh is required" }, { status: 400 });

      const map = new Map(current.map(it => [it.zh, it]));
      map.set(zh, {
        zh,
        en: (entry.en || "").trim(),
        tags: (entry.tags || []).map(t => String(t).trim()).filter(Boolean),
        note: entry.note ?? null,
      });

      const next = Array.from(map.values());
      await kvSetJson(KEY, next);
      return Response.json({ ok: true, action, count: next.length });
    }

    if (action === "import") {
      const mode = (body?.mode === "replace" ? "replace" : "append") as "append" | "replace";
      const items: GlossaryEntry[] = Array.isArray(body?.items) ? body.items : [];

      const imported = normalize(items);
      const merged = mode === "replace"
        ? imported
        : normalize([...current, ...imported]); // append 但會去重

      await kvSetJson(KEY, merged);
      return Response.json({ ok: true, action, mode, count: merged.length, imported: imported.length });
    }

    return Response.json({ ok: false, error: "Unknown action" }, { status: 400 });
  } catch (e: any) {
    const msg = e?.message || String(e);
    const status = msg === "Unauthorized" ? 401 : 500;
    return Response.json({ ok: false, error: msg }, { status });
  }
}
