import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import type { CrashJcSet } from "../api/materials";
import { jcStressCurve, jcToCard, type JcSource } from "../lib/crashJc";
import CrashMaterialCard, { defaultMatCard, matCardPayload, stressStrainSeries, type MatCardState } from "./CrashMaterialCard";

const JC_7075: CrashJcSet = {
  a_mpa: 546, b_mpa: 674, n: 0.72, c: 0.059, m: 1.56, eps_dot0_per_s: null, t_melt_k: null, t_ref_k: null, d: null,
  source: "Brar, Joshi, Harris 2009",
};
const JC_2024: CrashJcSet = {
  a_mpa: 369, b_mpa: 684, n: 0.73, c: 0.0083, m: 1.7, eps_dot0_per_s: 1, t_melt_k: 775, t_ref_k: 293,
  d: [0.13, 0.13, -1.5, 0.011, 0], source: "Lesuer 1999 Table 8",
};

function Harness({ sources, onState, init }: { sources: JcSource[]; onState: (s: MatCardState) => void; init?: Partial<MatCardState> }) {
  const [s, setS] = useState<MatCardState>(() => ({ ...defaultMatCard(), ...init }));
  onState(s);
  return <CrashMaterialCard value={s} onChange={setS} jcSources={sources} />;
}

describe("1.24g — kütüphane JC seti + σ–εₚ önizleme", () => {
  it("jcToCard: A MPa → σy Pa, B / n / C; kaynakta olmayan alan yazılmaz; D → /FAIL/JOHNSON", () => {
    const base = { ...defaultMatCard(), jcEps0: "5", jcTmelt: "900" };
    const p = jcToCard(JC_7075, base);
    expect(p).toMatchObject({ law: "plastic", sigmaY: "546000000", hardenB: "674", hardenN: "0.72", jcC: "0.059", jcM: "1.56" });
    expect(p).not.toHaveProperty("jcEps0"); // özette yok → kart değeri (5) kalır
    expect(p).not.toHaveProperty("jcTmelt");
    expect(p.failJohnson).toBeUndefined();
    const q = jcToCard(JC_2024, base);
    expect(q).toMatchObject({ jcEps0: "1", jcTmelt: "775", jcTr: "293" });
    expect(q.failJohnson).toMatchObject({ d1: "0.13", d2: "0.13", d3: "-1.5", d4: "0.011", d5: "0" });
  });

  it("jcStressCurve: σ(0) = A, σ(εₚ) = A + B·εₚⁿ", () => {
    const c = jcStressCurve(546, 674, 0.72, 0.5, 10);
    expect(c[0]).toEqual([0, 546]);
    expect(c[10][0]).toBeCloseTo(0.5);
    expect(c[10][1]).toBeCloseTo(546 + 674 * Math.pow(0.5, 0.72));
  });

  it("LAW2 kartında kaynaklı düğme alanları doldurur; payload deck birimleriyle", () => {
    let s = defaultMatCard();
    render(<Harness sources={[{ label: "7075-T6", jc: JC_7075 }]} onState={(x) => (s = x)} />);
    const box = screen.getByTestId("crash-jc-lib");
    expect(box).toHaveTextContent("A 546 MPa · B 674 MPa · n 0.72 · C 0.059 · m 1.56 · ε̇₀ kaynakta yok");
    expect(box).toHaveTextContent("Brar, Joshi, Harris 2009");
    fireEvent.click(within(box).getByRole("button", { name: "7075-T6 Johnson–Cook setini alanlara doldur" }));
    expect(matCardPayload(s)).toMatchObject({ law: "plastic", sigma_y_pa: 546e6, harden_b_mpa: 674, harden_n: 0.72, jc_c: 0.059, jc_m: 1.56 });
    // σ–εₚ önizlemesi çizildi
    expect(screen.getByRole("img", { name: "Gerilme–plastik şekil değiştirme grafiği" })).toBeInTheDocument();
  });

  it("kaynak yoksa ya da LAW1'de kütüphane kutusu yok", () => {
    render(<Harness sources={[]} onState={() => undefined} />);
    expect(screen.queryByTestId("crash-jc-lib")).toBeNull();
  });

  it("σ–εₚ: a boşsa not; LAW36'da girilen eğriler", () => {
    expect(stressStrainSeries(defaultMatCard()).series).toEqual([]);
    expect(stressStrainSeries(defaultMatCard()).note).toMatch(/a \(σy\) boş/);
    const tab = { ...defaultMatCard(), law: "tabulated" as const, tabCurves: [{ id: 1, rate: "0", points: "0 235\n0.1 320\n0.3 380" }] };
    const { series } = stressStrainSeries(tab);
    expect(series).toHaveLength(1);
    expect(series[0].values).toEqual([235, 320, 380]);
    expect(series[0].time).toEqual([0, 0.1, 0.3]);
  });
});
