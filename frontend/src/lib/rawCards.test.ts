import { describe, expect, it } from "vitest";
import {
  cursorInfo,
  formatIdLines,
  insertBlockAt,
  rawCardLineCount,
  rulerLines,
  spacesToNextField,
} from "./rawCards";

describe("rawCards yardımcıları", () => {
  it("ID'ler 10'luk alanlara, satır başına 10", () => {
    const ids = Array.from({ length: 12 }, (_, i) => i + 1);
    const lines = formatIdLines(ids).split("\n");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveLength(100);
    expect(lines[0].slice(0, 10)).toBe("         1");
    expect(lines[1]).toBe("        11        12");
    expect(formatIdLines([900001])).toBe("    900001");
  });

  it("imleç → satır, kolon, alan", () => {
    const t = "/BCS/900001\nabc\n0123456789X";
    expect(cursorInfo(t, 0)).toEqual({ line: 1, col: 1, field: 1 });
    expect(cursorInfo(t, t.length)).toEqual({ line: 3, col: 12, field: 2 });
    expect(cursorInfo(t, t.length - 1)).toEqual({ line: 3, col: 11, field: 2 });
  });

  it("Tab sonraki 10'luk alan başına", () => {
    expect(spacesToNextField(0)).toBe(10);
    expect(spacesToNextField(3)).toBe(7);
    expect(spacesToNextField(10)).toBe(10);
  });

  it("blok ekleme satır ortasında yeni satır açar", () => {
    expect(insertBlockAt("ab", 2, "X")).toEqual({ text: "ab\nX\n", cursor: 5 });
    expect(insertBlockAt("ab\n", 3, "X")).toEqual({ text: "ab\nX\n", cursor: 5 });
    expect(insertBlockAt("", 0, "X")).toEqual({ text: "X\n", cursor: 2 });
  });

  it("cetvel 10'luk sınırları gösterir", () => {
    const [nums, ticks] = rulerLines(30);
    expect(nums).toBe("        10        20        30");
    expect(ticks).toHaveLength(30);
    expect(ticks[9]).toBe("|");
    expect(ticks[4]).toBe("+");
  });

  it("satır sayısı sondaki boşlukları saymaz", () => {
    expect(rawCardLineCount("")).toBe(0);
    expect(rawCardLineCount("  \n\n")).toBe(0);
    expect(rawCardLineCount("a\nb\n\n")).toBe(2);
  });
});
