import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Çözülmemiş git çakışma işareti CSS'te sonraki kuralı sessizce düşürür
// (index.css'te af86b67'den kalan işaret tam ekran deforme şekli bozuyordu).
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? files(p) : /\.(css|tsx?)$/.test(n) ? [p] : [];
  });
}

describe("kaynakta git çakışma işareti yok", () => {
  it("src altındaki .css / .ts / .tsx", () => {
    const bad = files(join(__dirname))
      .filter((p) => /^(<{7}|={7}|>{7})( |$)/m.test(readFileSync(p, "utf8")))
      .map((p) => p.slice(__dirname.length + 1));
    expect(bad).toEqual([]);
  });
});
