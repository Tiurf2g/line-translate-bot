import { getFamilyGlossary } from "./glossary";
import type { Lang } from "./lang";

function getOpenAIEnv() {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("Missing OPENAI_API_KEY");
  const model = process.env.OPENAI_MODEL || "gpt-4o-mini";
  return { apiKey, model };
}

function buildSystemPrompt(from: Lang, to: Lang, glossaryPairs: { src: string; dst: string }[]) {
  const dir = `${from}→${to}`;

  const glossaryText =
    glossaryPairs.length === 0
      ? "（無詞庫）"
      : glossaryPairs.map((p) => `- ${p.src} => ${p.dst}`).join("\n");

  return [
    `你是「繁體中文 ↔ 越南文」的精準翻譯器（家庭生活用）。`,
    `只做翻譯：方向 ${dir}。`,
    `如果聽不清楚或語意不完整，請輸出空字串（不要亂翻）。`,
    `以下詞庫請優先套用：\n${glossaryText}`,
    `只輸出翻譯結果，不要加解釋。`,
  ].join("\n");
}

export async function translateFamily(text: string, from: Lang, to: Lang) {
  const { apiKey, model } = getOpenAIEnv();
  const glossary = await getFamilyGlossary();

  // ✅ 依方向決定 src/dst
  const glossaryPairs =
    from === "zh" && to === "vi"
      ? glossary
          .map((g) => ({ src: g.zh.trim(), dst: g.vi.trim() }))
          .filter((p) => p.src && p.dst)
      : from === "vi" && to === "zh"
      ? glossary
          .map((g) => ({ src: g.vi.trim(), dst: g.zh.trim() }))
          .filter((p) => p.src && p.dst)
      : [];

  const system = buildSystemPrompt(from, to, glossaryPairs);

  const r = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      input: [
        { role: "system", content: system },
        { role: "user", content: text },
      ],
      temperature: 0,
      max_output_tokens: 300,
    }),
  });

  if (!r.ok) {
    const errText = await r.text().catch(() => "");
    throw new Error(`OpenAI error ${r.status}: ${errText}`);
  }

  const data: any = await r.json();
  const out = (data?.output_text || "").toString().trim();
  return out;
}
