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
    const vi = ((it?.vi || it?.en || "") as string).trim();
    if (!zh || !vi) continue;
    const tags = Array.isArray(it.tags) ? it.tags.map((t) => String(t).trim()).filter(Boolean) : [];
    const note = it.note == null ? null : String(it.note);
    map.set(zh, { zh, vi, tags, note });
  }
  return Array.from(map.values());
}

function requireAdmin(req: Request) {
  if (!ADMIN_PIN) return { ok: false, status: 500, error: "Missing ADMIN_PIN/ADMIN_PASS in env" };
  const pin = (req.headers.get("x-admin-pin") || "").trim();
  if (!pin || pin !== ADMIN_PIN) return { ok: false, status: 401, error: "Unauthorized (bad x-admin-pin)" };
  return null;
}

async function loadList(): Promise<NormEntry[]> {
  const cur = await kvGetJson<NormEntry[]>(KEY);
  return normalize(cur as any);
}

async function saveList(list: NormEntry[]) {
  await kvSetJson(KEY, normalize(list as any));
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
    const body = (await req.json().catch(() => ({}))) as any;
    const action = String(body?.action || "list");

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
      const it = body?.entry as Entry;
      const zh = (it?.zh || "").trim();
      const vi = ((it?.vi || it?.en || "") as string).trim();
      if (!zh || !vi) return NextResponse.json({ ok: false, error: "Missing zh/vi" }, { status: 400 });

      const list = await loadList();
      const map = new Map(list.map((x) => [x.zh, x] as const));
      const tags = Array.isArray(it.tags) ? it.tags.map((t: any) => String(t).trim()).filter(Boolean) : [];
      const note = it.note == null ? null : String(it.note);
      map.set(zh, { zh, vi, tags, note });
      const next = Array.from(map.values());
      await saveList(next);

      return NextResponse.json({ ok: true, key: KEY, count: next.length, glossary: next, kv_host: kvHostInfo() }, { status: 200 });
    }

    if (action === "delete") {
      const zh = String(body?.zh || "").trim();
      if (!zh) return NextResponse.json({ ok: false, error: "Missing zh" }, { status: 400 });

      const list = await loadList();
      const next = list.filter((x) => x.zh !== zh);
      await saveList(next);
      return NextResponse.json({ ok: true, key: KEY, count: next.length, glossary: next, kv_host: kvHostInfo() }, { status: 200 });
    }

    if (action === "import") {
      const mode = String(body?.mode || "append"); // append | replace
      const items = normalize(body?.items as Entry[]);
      if (!Array.isArray(items)) return NextResponse.json({ ok: false, error: "items must be array" }, { status: 400 });

      if (mode === "replace") {
        await saveList(items);
        return NextResponse.json({ ok: true, key: KEY, count: items.length, glossary: items, kv_host: kvHostInfo() }, { status: 200 });
      }

      // append (merge by zh)
      const cur = await loadList();
      const map = new Map(cur.map((x) => [x.zh, x] as const));
      for (const it of items) map.set(it.zh, it);
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
