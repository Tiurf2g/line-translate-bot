export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { kvGetJson, kvSetJson, kvHostInfo } from "../../_lib/kv";

type Entry = { zh: string; vi?: string; en?: string; tags?: string[]; note?: string | null };
type NormEntry = { zh: string; vi: string; tags: string[]; note: string | null };

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const ADMIN_PIN = process.env.ADMIN_PIN || process.env.ADMIN_PASS || "";

function normalize(items: Entry[] | null | undefined): NormEntry[] {
  const map = new Map<string, NormEntry>();
  for (const it of items || []) {
    const zh = (it?.zh || "").trim();
    if (!zh) continue;
    const vi = (it?.vi || it?.en || "").trim(); // fallback
    const tags = Array.isArray(it?.tags) ? it.tags.map((t) => String(t).trim()).filter(Boolean) : [];
    const note = it.note == null ? null : String(it.note);
    map.set(zh, { zh, vi, tags, note });
  }
  return Array.from(map.values());
}

async function loadList(): Promise<NormEntry[]> {
  const v = await kvGetJson<any>(KEY);
  if (!v) return [];
  if (Array.isArray(v)) return normalize(v as Entry[]);
  if (typeof v === "object" && Array.isArray((v as any).glossary)) return normalize((v as any).glossary);
  return [];
}

async function saveList(list: NormEntry[]) {
  await kvSetJson(KEY, list);
}

function requireAdmin(req: Request) {
  const pin = (req.headers.get("x-admin-pin") || "").trim();
  if (!ADMIN_PIN) return { ok: false, error: "Server missing ADMIN_PIN", status: 500 };
  if (!pin || pin !== ADMIN_PIN) return { ok: false, error: "Invalid ADMIN PIN", status: 401 };
  return null;
}

export async function GET(req: Request) {
  // ✅ 修掉你看到的 HTTP 405：以前只有 POST，前端用 GET 會被 Next 回 405
  const auth = requireAdmin(req);
  if (auth) return NextResponse.json(auth, { status: auth.status });

  try {
    const glossary = await loadList();
    return NextResponse.json(
      { ok: true, key: KEY, count: glossary.length, glossary, kv_host: kvHostInfo() },
      { status: 200 }
    );
  } catch (e: any) {
    const status = e?.status || 500;
    const msg = e?.message || String(e);
    return NextResponse.json({ ok: false, error: msg, kv_host: kvHostInfo() }, { status });
  }
}

export async function POST(req: Request) {
  const auth = requireAdmin(req);
  if (auth) return NextResponse.json(auth, { status: auth.status });

  try {
    const body = await req.json().catch(() => ({}));
    const action = String(body?.action || "").trim();

    if (action === "list") {
      const glossary = await loadList();
      return NextResponse.json(
        { ok: true, key: KEY, count: glossary.length, glossary, kv_host: kvHostInfo() },
        { status: 200 }
      );
    }

    if (action === "reset") {
      await saveList([]);
      return NextResponse.json({ ok: true, key: KEY, count: 0, glossary: [], kv_host: kvHostInfo() }, { status: 200 });
    }

    if (action === "upsert") {
      const it = body?.item as Entry;
      const zh = String(it?.zh || "").trim();
      if (!zh) return NextResponse.json({ ok: false, error: "Missing zh" }, { status: 400 });

      const cur = await loadList();
      const norm = normalize([it])[0];
      const next = [norm, ...cur.filter((x) => x.zh !== zh)];
      await saveList(next);
      return NextResponse.json({ ok: true, key: KEY, count: next.length, glossary: next, kv_host: kvHostInfo() }, { status: 200 });
    }

    if (action === "delete") {
      const zh = String(body?.zh || "").trim();
      if (!zh) return NextResponse.json({ ok: false, error: "Missing zh" }, { status: 400 });

      const cur = await loadList();
      const next = cur.filter((x) => x.zh !== zh);
      await saveList(next);
      return NextResponse.json({ ok: true, key: KEY, count: next.length, glossary: next, kv_host: kvHostInfo() }, { status: 200 });
    }

    if (action === "import") {
      const mode = String(body?.mode || "append").trim(); // append | replace
      const incoming = normalize(Array.isArray(body?.items) ? body.items : []);

      if (mode === "replace") {
        await saveList(incoming);
        return NextResponse.json({ ok: true, key: KEY, count: incoming.length, glossary: incoming, kv_host: kvHostInfo() }, { status: 200 });
      }

      // append: incoming 覆蓋既有同 zh
      const cur = await loadList();
      const map = new Map(cur.map((x) => [x.zh, x] as const));
      for (const it of incoming) map.set(it.zh, it);
      const next = Array.from(map.values());
      await saveList(next);
      return NextResponse.json({ ok: true, key: KEY, count: next.length, glossary: next, kv_host: kvHostInfo() }, { status: 200 });
    }

    return NextResponse.json({ ok: false, error: `Unknown action: ${action}` }, { status: 400 });
  } catch (e: any) {
    const status = e?.status || 500;
    const msg = e?.message || String(e);
    return NextResponse.json({ ok: false, error: msg, kv_host: kvHostInfo() }, { status });
  }
}
