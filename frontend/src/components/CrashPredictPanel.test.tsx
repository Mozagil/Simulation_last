import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashPredictPanel, { midInputs } from "./CrashPredictPanel";

vi.mock("../api/crashMl", () => ({
  fetchCrashModels: vi.fn(),
  predictCrash: vi.fn(),
}));
vi.mock("../api/crash", () => ({ fetchCrashCatalog: vi.fn() }));

import { fetchCrashModels, predictCrash } from "../api/crashMl";

const MODEL = {
  template_id: "crash_box_shell",
  scenario: "rigid_wall",
  study_id: 2,
  n_runs: 12,
  feature_keys: ["req.barrier.speed_m_s", "geom.wall"],
  dropped_features: [],
  constant_features: {},
  bounds: { "req.barrier.speed_m_s": [5, 15] as [number, number], "geom.wall": [1.5, 3] as [number, number] },
  seed: 2026,
  targets: [
    { key: "peak_force_kn", label: "Tepe duvar kuvveti", unit: "kN", definition: "", trained: true,
      cv: { n: 12, r2: 0.911, mae: 3.653, mape: 0.043, folds: 5 } },
    { key: "crush_mm", label: "Ezilme mesafesi", unit: "mm", definition: "", trained: false,
      cv: { n: 5, skipped: "en az 8 dolu satır gerekir" } },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchCrashModels).mockResolvedValue([MODEL]);
});

describe("CrashPredictPanel", () => {
  it("girdi formu aralık ortasıyla başlar", () => {
    expect(midInputs(MODEL)).toEqual({ "req.barrier.speed_m_s": "10", "geom.wall": "2.25" });
  });

  it("tahmin eder, CV MAE ve aralık dışı girdiyi gösterir", async () => {
    vi.mocked(predictCrash).mockResolvedValue({
      prediction: { peak_force_kn: 101.234, crush_mm: null },
      out_of_domain: ["req.barrier.speed_m_s"],
      out_of_domain_detail: [{ feature: "req.barrier.speed_m_s", value: 20, min: 5, max: 15, side: "above", factor: 1.333 }],
      chosen: { peak_force_kn: "hybrid", crush_mm: null },
    });
    render(<CrashPredictPanel />);
    const speed = await screen.findByLabelText("req.barrier.speed_m_s");
    fireEvent.change(speed, { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Tahmin et" }));
    await waitFor(() =>
      expect(predictCrash).toHaveBeenCalledWith({
        template_id: "crash_box_shell",
        scenario: "rigid_wall",
        inputs: { "req.barrier.speed_m_s": 20, "geom.wall": 2.25 },
      }),
    );
    expect(await screen.findByText("101.2")).toBeInTheDocument();
    expect(screen.getByText("± 3.653 · R² 0.911")).toBeInTheDocument();
    expect(screen.getByText("en az 8 dolu satır gerekir")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("req.barrier.speed_m_s = 20.000 (üst sınır 15.000, 1.3×)");
    expect(screen.getByText("Tepe duvar kuvveti · hybrid")).toBeInTheDocument();
  });

  it("sayı olmayan girdi istek göndermez", async () => {
    render(<CrashPredictPanel />);
    fireEvent.change(await screen.findByLabelText("geom.wall"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Tahmin et" }));
    expect(await screen.findByText("'geom.wall' sayı olmalı.")).toBeInTheDocument();
    expect(predictCrash).not.toHaveBeenCalled();
  });

  it("model yoksa yönlendirir", async () => {
    vi.mocked(fetchCrashModels).mockResolvedValue([]);
    render(<CrashPredictPanel />);
    expect(await screen.findByText("Kayıtlı crash modeli yok. Önce Model aşamasında eğit.")).toBeInTheDocument();
  });
});
