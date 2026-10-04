import { render, screen, within } from "@testing-library/react";
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
      ],
    }),
  ),
}));

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
});
