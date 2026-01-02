// app/api/admin/family-glossary/route.ts
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { kvGetJson, kvSetJson } from "../../_lib/kv";

type GlossaryEntryRaw = { zh: string; vi?: string; en?: string; tags?: string[]; note?: string | null };
type GlossaryEntry = { zh: string; vi: string; tags?: string[]; note?: string | null };

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const LEGACY_KEY = process.env.FACTORY_GLOSSARY_KEY || "factory_glossary_v1";

const ADMIN_PIN = process.env.ADMIN_PASS || process.env.ADMIN_PIN || "";

function assertPin(req: Request) {
  const pin = req.headers.get("x-admin-pin") || "";
  if (!ADMIN_PIN) throw new Error("ADMIN_PIN not set");
  if (pin !== ADMIN_PIN) throw new Error("Unauthorized");
}

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

async function readCurrent() {
  let current = normalize((await kvGetJson<GlossaryEntryRaw[]>(KEY)) || []);
  // 自動搬 legacy（避免舊資料卡在另一個 key）
  if (current.length === 0 && LEGACY_KEY && LEGACY_KEY !== KEY) {
    const legacy = normalize((await kvGetJson<GlossaryEntryRaw[]>(LEGACY_KEY)) || []);
    if (legacy.length > 0) {
      await kvSetJson(KEY, legacy);
      current = legacy;
    }
  }
  if ((await kvGetJson(KEY)) === null) await kvSetJson(KEY, []);
  return current;
}

export async function POST(req: Request) {
  try {
    assertPin(req);

    const body = await req.json().catch(() => ({}));
    const action = String(body?.action || "");

    const current = await readCurrent();

    if (action === "reset") {
      await kvSetJson(KEY, []);
      return Response.json({ ok: true, action, count: 0 });
    }

    if (action === "upsert") {
      const e = body?.entry || {};
      const zh = String(e.zh || "").trim();
      const vi = String(e.vi ?? e.en ?? "").trim(); // 兼容舊欄位 en
      if (!zh) return Response.json({ ok: false, error: "zh required" }, { status: 400 });

      const entry: GlossaryEntry = {
        zh,
        vi,
        tags: (e.tags || []).map(String).map((t: string) => t.trim()).filter(Boolean),
        note: e.note ?? null,
      };

      const merged = normalize([...current, entry]);
      await kvSetJson(KEY, merged);
      return Response.json({ ok: true, action, count: merged.length, entry });
    }

    if (action === "import") {
      const mode = body?.mode === "replace" ? "replace" : "append";
      const items: GlossaryEntryRaw[] = Array.isArray(body?.items) ? body.items : [];
      const imported = normalize(items);
      const merged = mode === "replace" ? imported : normalize([...current, ...imported]);
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
