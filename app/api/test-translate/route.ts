export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { kvGetJson } from "../_lib/kv";

type Entry = { zh: string; vi?: string; en?: string };

const GLOSSARY_KEY = process.env.FAMILY_GLOSSARY_KEY || "family_glossary_v1";
const OPENAI_KEY = process.env.OPENAI_API_KEY || "";
const OPENAI_MODEL = process.env.OPENAI_MODEL || "gpt-4o-mini";

const ADMIN_PIN = process.env.ADMIN_PIN || process.env.ADMIN_PASS || "";

const PHRASE_MAP_VN_TO_TW: Record<string, string> = {
  "con uh": "寶寶喔？",
  "con u": "寶寶喔？",
  "con ư": "寶寶喔？",
  "con à": "寶寶喔？",
  "khong hieu": "不懂。",
  "không hiểu": "不懂。",
  "dang noi ve cai gi vay": "在說什麼？",
  "đang nói về cái gì vậy": "在說什麼？",
  "toi cho con ngu": "我先讓孩子睡。",
  "tôi cho con ngủ": "我先讓孩子睡。",
  "con ngu say da roi ra ngoai": "等孩子睡熟了再出去。",
  "con ngủ say đã rồi ra ngoài": "等孩子睡熟了再出去。",
};

const PHRASE_MAP_TW_TO_VN: Record<string, string> = {
  "去睡覺吧": "Đi ngủ đi.",
  "不懂": "Không hiểu.",
  "在說什麼": "Đang nói về cái gì vậy?",
  "在說什麼？": "Đang nói về cái gì vậy?",
  "可以": "Được.",
};

function normalizePhrase(text: string) {
  return text
    .trim()
    .toLowerCase()
    .replace(/[?!！？。,.，、]+$/g, "")
    .replace(/\s+/g, " ");
}

function stripVietnameseMarks(text: string) {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D");
}

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

    const phrase = normalizePhrase(text);
    const phraseNoMarks = stripVietnameseMarks(phrase);
    const hardCoded =
      finalDir === "zh2vi"
        ? PHRASE_MAP_TW_TO_VN[text] || PHRASE_MAP_TW_TO_VN[phrase]
        : PHRASE_MAP_VN_TO_TW[phrase] || PHRASE_MAP_VN_TO_TW[phraseNoMarks];

    if (hardCoded) {
      return Response.json({
        ok: true,
        direction: finalDir,
        ms: 0,
        input: text,
        output: hardCoded,
        glossary_count: 0,
        hard_rule: true,
      });
    }

    const rawGlossary = await kvGetJson<any>(GLOSSARY_KEY);
    const glossary = normalizeGlossary(rawGlossary);

    // 為了避免 prompt 太長，只塞前 200 筆（通常夠用）
    const slice = glossary.slice(0, 200);
    const glossaryLines = slice
      .map((x) => `- ${x.zh} => ${x.vi}`)
      .join("\n");

    const system =
      finalDir === "zh2vi"
        ? `You are a STRICT translator for family LINE messages. Translate Traditional Chinese to Vietnamese.
Rules:
- Translate exactly, do NOT paraphrase.
- Keep punctuation and numbers.
- If unclear/inaudible, output exactly: [UNSURE]
- Use glossary terms when they match.
- Use natural Vietnamese family wording, not textbook or news style.
- Do not invent people, reasons, or context for short messages.
Glossary:
${glossaryLines}`
        : `You are a STRICT translator for family LINE messages. Translate Vietnamese to Traditional Chinese.
Rules:
- Translate exactly, do NOT paraphrase.
- Keep punctuation and numbers.
- If unclear/inaudible, output exactly: [UNSURE]
- Use glossary terms when they match.
- Use natural Taiwanese family wording, not formal writing.
- Do not invent questions or context for short messages.
- Vietnamese "con" often means child/baby or a junior family member's self-reference; unless the source says "ai", do not translate it as "誰".
- "cho con ngủ" usually means "讓孩子睡／哄孩子睡".
- "đã rồi" often means "等...之後再...".
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
