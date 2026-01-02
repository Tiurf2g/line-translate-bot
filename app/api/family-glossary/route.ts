// app/api/family-glossary/route.ts
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { kvGetJson, kvSetJson } from "../_lib/kv";

type Entry = {
  zh: string;
  vi?: string;
  en?: string; // 向下相容舊欄位
  tags?: string[];
  note?: string | null;
};

type NormEntry = { zh: string; vi: string; tags: string[]; note: string | null };

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const ADMIN_PIN = process.env.ADMIN_PIN || process.env.ADMIN_PASS || "";

function normalize(items: Entry[] | null | undefined): NormEntry[] {
  const map = new Map<string, NormEntry>();
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

function requirePin(req: Request) {
  if (!ADMIN_PIN) throw new Error("ADMIN_PIN not set");
  const pin = req.headers.get("x-admin-pin") || "";
  if (pin !== ADMIN_PIN) throw new Error("Unauthorized");
}

async function ensureInit(): Promise<NormEntry[]> {
  const raw = await kvGetJson<Entry[]>(KEY);
  if (raw == null) {
    await kvSetJson(KEY, []);
    return [];
  }
  return normalize(raw);
}

export async function GET(req: Request) {
  try {
    const url = new URL(req.url);
    const force = url.searchParams.get("force") === "true";

    const glossary = force
      ? await ensureInit()
      : normalize((await kvGetJson<Entry[]>(KEY)) || []);

    return Response.json({ ok: true, key: KEY, count: glossary.length, glossary });
  } catch (e: any) {
    return Response.json(
      {
        ok: false,
        error: e?.message || String(e),
        missing_env: {
          KV_REST_API_URL: !process.env.KV_REST_API_URL,
          KV_REST_API_TOKEN: !process.env.KV_REST_API_TOKEN,
          FAMILY_GLOSSARY_KEY: !process.env.FAMILY_GLOSSARY_KEY,
        },
      },
      { status: 500 }
    );
  }
}

/**
 * POST 支援：
 * - action: "upsert"  entry: {zh, vi, tags?, note?}
 * - action: "import"  entries: Entry[]  mode: "append" | "replace"
 * - action: "reset"
 */
export async function POST(req: Request) {
  try {
    requirePin(req);

    const body = await req.json().catch(() => ({}));
    const action = String(body?.action || "").toLowerCase();

    if (!action) return Response.json({ ok: false, error: "action required" }, { status: 400 });

    if (action === "reset") {
      await kvSetJson(KEY, []);
      return Response.json({ ok: true, key: KEY, count: 0, glossary: [] });
    }

    if (action === "upsert") {
      const entry: Entry = body?.entry || {};
      const zh = (entry.zh || "").trim();
      const vi = ((entry.vi ?? entry.en) || "").trim();

      if (!zh) return Response.json({ ok: false, error: "entry.zh required" }, { status: 400 });

      const current = await ensureInit();
      const map = new Map(current.map((x) => [x.zh, x]));
      map.set(zh, {
        zh,
        vi,
        tags: (entry.tags || []).map(String).map((t) => t.trim()).filter(Boolean),
        note: entry.note ?? null,
      });

      const glossary = Array.from(map.values());
      await kvSetJson(KEY, glossary);
      return Response.json({ ok: true, key: KEY, count: glossary.length, glossary });
    }

    if (action === "import") {
      const mode = String(body?.mode || "append").toLowerCase();
      const entries: Entry[] = Array.isArray(body?.entries) ? body.entries : [];

      const incoming = normalize(entries);

      if (mode === "replace") {
        await kvSetJson(KEY, incoming);
        return Response.json({ ok: true, key: KEY, count: incoming.length, glossary: incoming });
      }

      const current = await ensureInit();
      const map = new Map(current.map((x) => [x.zh, x]));
      for (const it of incoming) map.set(it.zh, it);

      const glossary = Array.from(map.values());
      await kvSetJson(KEY, glossary);
      return Response.json({ ok: true, key: KEY, count: glossary.length, glossary });
    }

    return Response.json({ ok: false, error: `unknown action: ${action}` }, { status: 400 });
  } catch (e: any) {
    const msg = e?.message || String(e);
    const status = msg === "Unauthorized" ? 401 : 500;
    return Response.json({ ok: false, error: msg }, { status });
  }
}
