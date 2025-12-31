// app/api/_lib/lang.ts
export type Lang = "zh" | "vi";

export function containsUrl(text: string) {
  const s = text.trim();
  if (!s) return false;
  // 常見 URL
  const urlRe = /(https?:\/\/\S+|www\.\S+)/i;
  return urlRe.test(s);
}

export function isMostlyUrl(text: string) {
  const s = text.trim();
  if (!s) return false;
  // 如果整段幾乎就是網址/符號，就跳過
  const stripped = s.replace(/(https?:\/\/\S+|www\.\S+)/gi, "");
  const remain = stripped.replace(/[\s\W_]+/g, "");
  return remain.length <= 2 && containsUrl(s);
}

export function looksChinese(text: string) {
  // 中日韓統一表意文字
  return /[\u4E00-\u9FFF]/.test(text);
}

export function looksVietnamese(text: string) {
  // 越南文常見變音符 & đ/Đ
  return /[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵĂÂĐÊÔƠƯÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]/.test(
    text
  );
}

export function detectLang(text: string): Lang | null {
  const s = text.trim();
  if (!s) return null;

  // URL/廣告類先排除
  if (containsUrl(s) || isMostlyUrl(s)) return null;

  if (looksVietnamese(s) && !looksChinese(s)) return "vi";
  if (looksChinese(s)) return "zh";

  // 其他：純英文、純數字、代碼 → 不翻
  return null;
}
