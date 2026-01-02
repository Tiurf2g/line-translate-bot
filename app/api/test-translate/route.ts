// app/api/test-translate/route.ts
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { kvGetJson } from "../_lib/kv";

type Entry = { zh: string; vi?: string; en?: string; tags?: string[]; note?: string | null };

const KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const ADMIN_PIN = process.env.ADMIN_PIN || process.env.ADMIN_PASS || "";
const MODEL = process.env.OPENAI_MODEL || "gpt-4o-mini";

const VN_MARKS = new Set("ăâêôơưđĂÂÊÔƠƯĐ".split(""));

function isVietnamese(t: string) {
  const s = (t || "").trim();
  if (!s) return false;
  for (const ch of s) if (VN_MARKS.has(ch)) return true;
  return false;
}

function normalize(items: Entry[]) {
  const map = new Map<string, { zh: string; vi: string }>();
  for (const it of items || []) {
    const zh = (it.zh || "").trim();
    const vi = ((it.vi ?? it.en) || "").trim();
    if (!zh || !vi) continue;
    map.set(zh, { zh, vi });
  }
  return Array.from(map.values());
}

function requirePin(req: Request) {
  if (!ADMIN_PIN) throw new Error("ADMIN_PIN not set");
  const pin = req.headers.get("x-admin-pin") || "";
  if (pin !== ADMIN_PIN) throw new Error("Unauthorized");
}

export async function POST(req: Request) {
  try {
    requirePin(req);

    const { text, direction } = await req.json().catch(() => ({}));
    const input = String(text || "").trim();
    if (!input) return Response.json({ ok: false, error: "text required" }, { status: 400 });

    // direction: "auto" | "zh2vi" | "vi2zh"
    let from: "zh" | "vi" = "zh";
    let to: "zh" | "vi" = "vi";

    if (direction === "vi2zh") {
      from = "vi";
      to = "zh";
    } else if (direction === "zh2vi") {
      from = "zh";
      to = "vi";
    } else {
      // auto
      if (isVietnamese(input)) {
        from = "vi";
        to = "zh";
      } else {
        from = "zh";
        to = "vi";
      }
    }

    const raw = (await kvGetJson<Entry[]>(KEY)) || [];
    const glossary = normalize(raw);

    // 避免 prompt 太長：只塞前 200 條
    const pairs =
      from === "zh" ? glossary.map((g) => `- ${g.zh} => ${g.vi}`) : glossary.map((g) => `- ${g.vi} => ${g.zh}`);

    const glossaryText = pairs.slice(0, 200).join("\n") || "（無詞庫）";

    const system = [
      `你是「繁體中文 ↔ 越南文」的家庭生活翻譯器。`,
      `只做翻譯：方向 ${from}→${to}。`,
      `如果聽不清楚或語意不完整，請輸出空字串（不要亂翻）。`,
      `詞庫優先套用：\n${glossaryText}`,
      `只輸出翻譯結果，不要加解釋。`,
    ].join("\n");

    if (!process.env.OPENAI_API_KEY) throw new Error("Missing OPENAI_API_KEY");

    const r = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        input: [
          { role: "system", content: system },
          { role: "user", content: input },
        ],
        temperature: 0,
        max_output_tokens: 220,
      }),
    });

    if (!r.ok) {
      const t = await r.text().catch(() => "");
      throw new Error(`OpenAI ${r.status}: ${t}`);
    }

    const data: any = await r.json();
    const out = String(data?.output_text || "").trim();

    return Response.json({
      ok: true,
      from,
      to,
      model: MODEL,
      used_glossary: Math.min(pairs.length, 200),
      translated: out,
    });
  } catch (e: any) {
    const msg = e?.message || String(e);
    const status = msg === "Unauthorized" ? 401 : 500;
    return Response.json({ ok: false, error: msg }, { status });
  }
}
