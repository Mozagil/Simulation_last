import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import CrashMaterialCard, {
  defaultMatCard,
  matCardPayload,
  parseCurvePoints,
  type MatCardState,
} from "./CrashMaterialCard";

function Harness({ onState }: { onState: (s: MatCardState) => void }) {
  const [s, setS] = useState<MatCardState>(defaultMatCard);
  return (
    <CrashMaterialCard
      value={s}
      onChange={(n) => {
        setS(n);
        onState(n);
      }}
    />
  );
}

describe("CrashMaterialCard", () => {
  it("eğri noktaları: boşluk, sekme + ondalık virgül, tek virgül ayırıcı", () => {
    expect(parseCurvePoints("0 235\n0,2\t320,5\n\n0.5,400", "e")).toEqual([
      [0, 235],
      [0.2, 320.5],
      [0.5, 400],
    ]);
    expect(() => parseCurvePoints("0 235 1", "e")).toThrow(/iki sütun/);
    expect(() => parseCurvePoints("a 235", "e")).toThrow(/sayı geçersiz/);
  });

  it("LAW1 yalnız temel alanları, /FAIL kapalıyken fail göndermez", () => {
    const p = matCardPayload(defaultMatCard());
    expect(p).toEqual({ law: "elastic", sigma_y_pa: null, harden_b_mpa: 0, harden_n: 1 });
  });

  it("LAW36 eğrileri + TENSSTRAIN arayüzden payload'a", () => {
    let last: MatCardState = defaultMatCard();
    render(<Harness onState={(s) => (last = s)} />);
    fireEvent.click(screen.getByRole("button", { name: "LAW36 tablo" }));
    fireEvent.change(screen.getByLabelText("Eğri 1 noktaları"), { target: { value: "0 235\n0.2 320" } });
    fireEvent.click(screen.getByRole("button", { name: "+ Eğri ekle" }));
    fireEvent.change(screen.getByLabelText("Eğri 2 ε̇"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Eğri 2 noktaları"), { target: { value: "0 260\n0.2 350" } });
    fireEvent.change(screen.getByLabelText("Eps_f"), { target: { value: "0.4" } });
    fireEvent.click(screen.getByLabelText("/FAIL/TENSSTRAIN"));
    fireEvent.change(screen.getByLabelText("ε_t1"), { target: { value: "0.2" } });
    fireEvent.change(screen.getByLabelText("ε_t2"), { target: { value: "0.3" } });
    const p = matCardPayload(last);
    expect(p.law).toBe("tabulated");
    expect(p.tab_curves).toEqual([
      { eps_dot_per_s: 0, points: [[0, 235], [0.2, 320]] },
      { eps_dot_per_s: 100, points: [[0, 260], [0.2, 350]] },
    ]);
    expect(p.tab_eps_f).toBe(0.4);
    expect(p.fail).toEqual({ tensstrain: { eps_t1: 0.2, eps_t2: 0.3, eps_f1: 0, eps_f2: 0, s_flag: 0 } });
    expect(p.jc_c).toBeUndefined(); // LAW2 alanı LAW36'da gitmez
  });

  it("LAW2 JC terimleri ve /FAIL/JOHNSON", () => {
    let last: MatCardState = defaultMatCard();
    render(<Harness onState={(s) => (last = s)} />);
    fireEvent.click(screen.getByRole("button", { name: "LAW2 plastik" }));
    fireEvent.change(screen.getByLabelText("c"), { target: { value: "0.014" } });
    fireEvent.change(screen.getByLabelText("ε̇₀ (1/s)"), { target: { value: "1" } });
    fireEvent.click(screen.getByLabelText("/FAIL/JOHNSON"));
    fireEvent.change(screen.getByLabelText("D1"), { target: { value: "0.05" } });
    fireEvent.change(screen.getByLabelText("Ifail_sh"), { target: { value: "1" } });
    const p = matCardPayload(last);
    expect(p).toMatchObject({ law: "plastic", jc_c: 0.014, jc_eps_dot0_per_s: 1 });
    expect(p.fail?.johnson).toMatchObject({ d1: 0.05, ifail_sh: 1, ifail_so: 0 });
    expect(p.tab_curves).toBeUndefined();
  });

  it("geçersiz sayıda alan adını içeren hata", () => {
    const s = { ...defaultMatCard(), law: "plastic" as const, jcC: "x" };
    expect(() => matCardPayload(s, "Parça #1")).toThrow(/Parça #1 c/);
  });
});
