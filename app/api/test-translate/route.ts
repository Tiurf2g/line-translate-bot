export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { kvGetJson } from "../_lib/kv";

type Entry = { zh: string; vi?: string; en?: string };

const GLOSSARY_KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const OPENAI_KEY = process.env.OPENAI_API_KEY || "";
const OPENAI_MODEL = process.env.OPENAI_MODEL || "gpt-4o-mini";

const ADMIN_PIN = process.env.ADMIN_PIN || process.env.ADMIN_PASS || "";

function pickDirection(text: string): "zh2vi" | "vi2zh" {
  // 粗略偵測：有中日韓字 → zh2vi；否則當 vi2zh
  const hasCJK = /[\u4E00-\u9FFF]/.test(text);
  return hasCJK ? "zh2vi" : "vi2zh";
}

function normalizeGlossary(raw: any): Array<{ zh: string; vi: string }> {
  const arr = Array.isArray(raw) ? raw : [];
  return arr
    .map((x: Entry) => ({
      zh: String(x?.zh || "").trim(),
      vi: String((x?.vi ?? x?.en) || "").trim(),
    }))
    .filter((x) => x.zh.length > 0);
}

async function callOpenAI(system: string, user: string) {
  if (!OPENAI_KEY) throw new Error("Missing OPENAI_API_KEY");

  const t0 = Date.now();
  const res = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENAI_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: OPENAI_MODEL,
      input: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    }),
  });

  const text = await res.text();
  let data: any = null;
  try {
    data = JSON.parse(text);
  } catch {}

  if (!res.ok) {
    throw new Error(data?.error?.message || text || `OpenAI HTTP ${res.status}`);
  }

  // responses API 通常會有 output_text
  const out = data?.output_text
    ?? data?.output?.[0]?.content?.[0]?.text
    ?? "";

  return { out: String(out || "").trim(), ms: Date.now() - t0 };
}

export async function POST(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));
    const text = String(body?.text || "").trim();
    const direction = (String(body?.direction || "auto") as any) as
      | "auto"
      | "zh2vi"
      | "vi2zh";

    const pin = String(body?.pin || req.headers.get("x-admin-pin") || "");

    if (ADMIN_PIN && pin !== ADMIN_PIN) {
      return Response.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }
    if (!text) {
      return Response.json({ ok: false, error: "text required" }, { status: 400 });
    }

    const finalDir = direction === "auto" ? pickDirection(text) : direction;

    const rawGlossary = await kvGetJson<any>(GLOSSARY_KEY);
    const glossary = normalizeGlossary(rawGlossary);

    // 為了避免 prompt 太長，只塞前 200 筆（通常夠用）
    const slice = glossary.slice(0, 200);
    const glossaryLines = slice
      .map((x) => `- ${x.zh} => ${x.vi}`)
      .join("\n");

    const system =
      finalDir === "zh2vi"
        ? `You are a STRICT translator. Translate Traditional Chinese to Vietnamese.
Rules:
- Translate exactly, do NOT paraphrase.
- Keep punctuation and numbers.
- If unclear/inaudible, output exactly: [UNSURE]
- Use glossary terms when they match.
Glossary:
${glossaryLines}`
        : `You are a STRICT translator. Translate Vietnamese to Traditional Chinese.
Rules:
- Translate exactly, do NOT paraphrase.
- Keep punctuation and numbers.
- If unclear/inaudible, output exactly: [UNSURE]
- Use glossary terms when they match.
Glossary:
${glossaryLines}`;

    const user = text;

    const r = await callOpenAI(system, user);

    return Response.json({
      ok: true,
      direction: finalDir,
      ms: r.ms,
      input: text,
      output: r.out,
      glossary_count: glossary.length,
    });
  } catch (e: any) {
    return Response.json(
      { ok: false, error: e?.message || String(e) },
      { status: 500 }
    );
  }
}
