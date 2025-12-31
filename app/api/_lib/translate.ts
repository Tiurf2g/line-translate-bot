// app/api/_lib/translate.ts
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
      ? "（目前沒有詞庫規則）"
      : glossaryPairs.map(p => `- "${p.src}" => "${p.dst}"`).join("\n");

  // 你要的「家庭口語」與「不加戲」
  return `
你是一個只做「家庭日常口語」的精準翻譯器，方向：${dir}
規則：
1) 只翻譯使用者原句，不要加戲、不補充、不解釋。
2) 保留人名、數字、表情符號、標點、語氣詞。
3) 如果內容不是對話（像是網址、廣告、代碼、亂碼），輸出空字串。
4) 目標語言要貼近在地家庭口語：
   - zh：繁體中文、台灣家人聊天口吻
   - vi：越南家庭口語（自然，不要教材腔）
5) 必須優先套用詞庫（最重要）。遇到詞庫條目要照規則翻，不要改。
詞庫規則如下：
${glossaryText}

只輸出翻譯結果本身，不要輸出其他文字。
`.trim();
}

export async function translateFamily(text: string, from: Lang, to: Lang): Promise<string> {
  const { apiKey, model } = getOpenAIEnv();

  const glossary = await getFamilyGlossary();

  // glossary 的 zh/en 你後台既有欄位名：zh=原詞, en=對應詞
  // 這裡不管方向，都交給 prompt 來「優先套用」
  // 但你可以在後台用 tags 做分類（例如 tags: ["vi2zh"]），未來再強化
  const glossaryPairs = glossary
    .map(g => ({ src: g.zh.trim(), dst: g.en.trim() }))
    .filter(p => p.src && p.dst);

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
  // responses API：常見輸出在 output_text
  const out = (data?.output_text || "").toString().trim();
  return out;
}
