import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashValidation from "./CrashValidation";

vi.mock("../api/crash", () => ({
  fetchCrashValidation: vi.fn(() =>
    Promise.resolve({
      generated_at: "2026-10-04T01:00:00+00:00",
      setup: { template: "crash_box_shell", L_mm: 300, h_mm: 50, b_mm: 40, t_mm: 3, material: "S235",
               v0_m_s: 10, note: "Kabul kriteri yok — oranlar veri; eşik mühendisin." },
      cases: [
        { id: "V1", title: "Elastik", run_id: 51, energy_balance_rel: 0.001, hourglass_ratio: 0.002,
          rows: [{ quantity: "Plato kuvveti (kN)", sim: 200.0, ref: 204.6, ref_label: "ρ·c₀·v·A (çubuk)",
                   ratio: 0.9775, alt_ref: 214.5, alt_label: "ρ·c_p·v·A (levha)" }] },
        { id: "V3", title: "Kızak", references: { wierzbicki_abramowicz_1983_kn: 48.7,
          abramowicz_jones_1984_kn: 66.6, formula: "Pm = k·σ0·t^(5/3)·C^(1/3)" },
          mesh: [{ element_mm: 5, run_id: 53, wall_s: 40, crush_mm: 49.0, t_stop_ms: 9.5, ie_stop_j: 2450,
                   pm_energy_kn: 50.0, f_mean_kn: 51, f_peak_kn: 126, ratio_wa: 1.027, ratio_aj: 0.751,
                   energy_balance_rel: 0.001, hourglass_ratio: 0.05 }] },
        { id: "V5", title: "Recht–Ipson", references: { formula: "v_r = a·√(v0² − v_bl²)" },
          fit: { a: 0.988, v_bl_m_s: 28.75, r2: 0.9998, bracket_low_m_s: 25, bracket_high_m_s: 50, v_bl_in_bracket: true },
          rows: [{ quantity: "Son hız v0 = 100 m/s (#68)", sim: 95.3, ref: 94.62, ref_label: "Recht–Ipson uydurma", ratio: 1.0072 }] },
        { id: "V7", title: "Düşme", energy_balance_rel: 0.071, hourglass_ratio: 0.165,
          rows: [
            { quantity: "Zemin impulsu — yüzey (#121)", sim: 7.543, ref: 7.546, ref_label: "m·Δv + m·g·t", ratio: 0.9997 },
            { quantity: "Zemin impulsu — köşe (#122)", sim: 4.446, ref: 4.445, ref_label: "m·Δv + m·g·t", ratio: 1.0003 },
            { quantity: "Tepe kuvvet (kN)", sim: 471.6, ref: null, ref_label: "— (veri)", ratio: null },
          ],
          runs: [
            { run_id: 121, orientation: "yüzey", wall_s: 14, energy_balance_rel: 0.0713, hourglass_ratio: 0.1654, force_max_kn: 471.6 },
            { run_id: 123, orientation: "yüzey Ishell 24", element_mm: 10, control: true, wall_s: 15,
              energy_balance_rel: 0.0402, hourglass_ratio: 0.0, force_max_kn: 478.7 },
            { run_id: 124, orientation: "yüzey 5 mm", element_mm: 5, control: true, wall_s: 29,
              energy_balance_rel: 0.0872, hourglass_ratio: 0.161, force_max_kn: 468.3 },
          ] },
      ],
    }),
  ),
  fetchValidationThresholds: vi.fn(() =>
    Promise.resolve({
      default: { ratio_min: null, ratio_max: null, energy_balance_max: null, hourglass_max: null },
      cases: {},
      updated_at: null,
    }),
  ),
  putValidationThresholds: vi.fn((t: unknown) =>
    Promise.resolve({ ...(t as object), updated_at: "2026-10-05T01:00:00+00:00" }),
  ),
}));

import { fetchValidationThresholds, putValidationThresholds } from "../api/crash";

describe("CrashValidation", () => {
  it("vakaları oranlarla ve mesh tablosuyla gösterir; kabul kriteri koymaz", async () => {
    render(<CrashValidation />);
    expect(await screen.findByText(/Validasyon · 2026-10-04/)).toBeInTheDocument();
    const box = screen.getByTestId("crash-validation");
    expect(box).toHaveTextContent("Kabul kriteri yok");
    expect(box).toHaveTextContent("ρ·c_p·v·A (levha): 214.5");
    expect(box).toHaveTextContent("0.978"); // oran
    const mesh = within(screen.getByTestId("crash-validation-mesh"));
    expect(mesh.getByText("1.027")).toBeInTheDocument();
    expect(mesh.getByText("0.751")).toBeInTheDocument();
    // 1.18e — V5 uydurma satırı; koşusuz vakada "koşu #" yok
    expect(screen.getByTestId("crash-validation-fit-V5")).toHaveTextContent("v_bl 28.750 m/s · a 0.988 · R² 1.000");
    expect(screen.getByTestId("crash-validation-fit-V5")).toHaveTextContent("v_bl aralıkta");
    expect(box).not.toHaveTextContent("koşu #undefined");
    expect(box).not.toHaveTextContent(/geçti|kaldı|PASS|FAIL/i);
  });

  it("özet tablosu: vaka başına koşu sayısı, oran aralığı, en kötü denge / HG; koşu tablosu", async () => {
    render(<CrashValidation />);
    const sum = within(await screen.findByTestId("crash-validation-summary"));
    const v7 = sum.getByRole("link", { name: "V7" }).closest("tr")!;
    expect(v7).toHaveTextContent("3"); // koşu sayısı
    expect(v7).toHaveTextContent("1.000 – 1.000"); // 0.9997 / 1.0003, 3 hane
    expect(v7).toHaveTextContent("0.087"); // en kötü denge koşular içinden (#124)
    expect(v7).toHaveTextContent("0.165"); // en büyük HG
    // V3 mesh vakası: W&A / A&J oranlarından aralık
    expect(sum.getByRole("link", { name: "V3" }).closest("tr")!).toHaveTextContent("0.751 – 1.027");
    const runs = within(screen.getByTestId("crash-validation-runs-V7"));
    expect(runs.getByText("#123")).toBeInTheDocument();
    expect(runs.getByText("yüzey Ishell 24 · 10 mm · kontrol")).toBeInTheDocument();
    expect(runs.getByText("478.7")).toBeInTheDocument();
    expect(screen.getByTestId("crash-validation")).not.toHaveTextContent(/geçti|kaldı|PASS|FAIL/i);
  });

  it("eşik yoksa işaret yok (—); eşik girilip kaydedilince satırlar içinde / dışında işaretlenir", async () => {
    render(<CrashValidation />);
    const sum = within(await screen.findByTestId("crash-validation-summary"));
    await waitFor(() => expect(fetchValidationThresholds).toHaveBeenCalled());
    expect(screen.getByTestId("crash-validation-thr-V1")).toHaveTextContent("—");

    // varsayılan oran 0.98–1.02, denge ≤ 0.05; V7 için HG ≤ 0.1
    fireEvent.change(screen.getByLabelText("default oran min"), { target: { value: "0.98" } });
    fireEvent.change(screen.getByLabelText("default oran maks"), { target: { value: "1,02" } });
    fireEvent.change(screen.getByLabelText("default denge maks"), { target: { value: "0.05" } });
    fireEvent.change(screen.getByLabelText("V7 HG/IE maks"), { target: { value: "0.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Eşikleri kaydet" }));
    await waitFor(() => expect(putValidationThresholds).toHaveBeenCalledTimes(1));
    const body = vi.mocked(putValidationThresholds).mock.calls[0][0];
    expect(body.default).toEqual({ ratio_min: 0.98, ratio_max: 1.02, energy_balance_max: 0.05, hourglass_max: null });
    expect(body.cases.V7).toEqual({ ratio_min: null, ratio_max: null, energy_balance_max: null, hourglass_max: 0.1 });

    // V1: oran 0.978 < 0.98 → dışında; V7: oranlar içinde, denge 0.087 > 0.05, HG 0.165 > 0.1
    await waitFor(() => expect(screen.getByTestId("crash-validation-thr-V1")).toHaveTextContent("dışındaoran 1"));
    expect(screen.getByTestId("crash-validation-thr-V7")).toHaveTextContent("dışındadenge, HG");
    expect(sum.getByTestId("crash-validation-thr-V5")).toHaveTextContent("içinde");
    expect(screen.getByText("0.978 ↓")).toBeInTheDocument();
    expect(screen.getByText(/kaydedildi · 2026-10-05 01:00/)).toBeInTheDocument();
  });

  it("geçersiz eşik kaydedilmez", async () => {
    vi.mocked(putValidationThresholds).mockClear();
    render(<CrashValidation />);
    await screen.findByTestId("crash-validation-summary");
    fireEvent.change(screen.getByLabelText("default oran min"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Eşikleri kaydet" }));
    expect(await screen.findByText(/Geçersiz eşik/)).toBeInTheDocument();
    expect(putValidationThresholds).not.toHaveBeenCalled();
  });
});
