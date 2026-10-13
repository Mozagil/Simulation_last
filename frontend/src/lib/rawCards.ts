/**
 * 1.22d — ham kart editörü yardımcıları (OpenRadioss sabit genişlik: 10 karakterlik alanlar).
 * Yalnız metin işlemi; kart içeriğini yorumlamaz.
 */

export const RADIOSS_FIELD = 10;
/** 1.22 — kullanıcı ham kart ID aralığı (kullanıcı onayı 2026-10-13). */
export const USER_ID_MIN = 900_000;

/** Kimlikleri 10'luk alanlara sağa yaslı, satır başına `perLine` adet yazar. */
export function formatIdLines(ids: number[], perLine = 10): string {
  const lines: string[] = [];
  for (let i = 0; i < ids.length; i += perLine) {
    lines.push(ids.slice(i, i + perLine).map((n) => String(n).padStart(RADIOSS_FIELD)).join(""));
  }
  return lines.join("\n");
}

/** İmleç konumu → 1 tabanlı satır, kolon ve 10'luk alan numarası. */
export function cursorInfo(text: string, pos: number): { line: number; col: number; field: number } {
  const before = text.slice(0, pos);
  const line = before.split("\n").length;
  const col = pos - (before.lastIndexOf("\n") + 1) + 1;
  return { line, col, field: Math.floor((col - 1) / RADIOSS_FIELD) + 1 };
}

/** Tab: imleci bir sonraki alan başına götürecek boşluk sayısı (satır içi 0 tabanlı kolon). */
export function spacesToNextField(col0: number): number {
  return RADIOSS_FIELD - (col0 % RADIOSS_FIELD);
}

/**
 * Metnin `pos` noktasına `insert` ekler; imleç satır ortasındaysa önce yeni
 * satır açar, ekin sonuna yeni satır koyar. Döner: yeni metin + imleç.
 */
export function insertBlockAt(text: string, pos: number, insert: string): { text: string; cursor: number } {
  const atLineStart = pos === 0 || text[pos - 1] === "\n";
  const block = `${atLineStart ? "" : "\n"}${insert}\n`;
  return { text: text.slice(0, pos) + block + text.slice(pos), cursor: pos + block.length };
}

/** Kolon cetveli: üst satır 10'un katlarında numara, alt satır alan sınırları. */
export function rulerLines(width = 100): [string, string] {
  let nums = "";
  let ticks = "";
  for (let c = 1; c <= width; c += 1) {
    ticks += c % RADIOSS_FIELD === 0 ? "|" : c % 5 === 0 ? "+" : "·";
  }
  for (let c = RADIOSS_FIELD; c <= width; c += RADIOSS_FIELD) {
    nums += String(c).padStart(RADIOSS_FIELD);
  }
  return [nums, ticks];
}

/** "3 satır" özeti için: sondaki boş satırlar sayılmaz; boş metin → 0. */
export function rawCardLineCount(text: string): number {
  const trimmed = text.replace(/\s+$/, "");
  return trimmed ? trimmed.split("\n").length : 0;
}
