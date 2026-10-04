import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashRunCharts from "./CrashRunCharts";

vi.mock("../api/crash", () => ({
  fetchCrashRun: vi.fn(() =>
    Promise.resolve({
      id: 50, job_id: "j50", geometry_id: 1, name: "kızak", created_at: null, dimension: 2, t_end_ms: 20,
      status: "solved", message: null, solver_ran: true, excluded: false, exclude_reason: null,
      request: {}, materials_snapshot: [], diagnostics: {},
      scalars: { internal_energy_final: 2441.3, energy_balance_rel: 0.0004, hic15: 1.4e9, hic15_cfc1000: 2.6e6 },
      curves: {
        time: [0, 1, 2, 3],
        rwall_force: [0, 126.7, 50, 0],
        rwall_force_cfc600: [0, 125.5, 51, 0],
        acc_g: [0, 120000, 3, 0],
        acc_g_cfc1000: [0, 8000, 2, 0],
        internal_energy: [0, 1000, 2400, 2441],
        kinetic_energy: [2559, 1500, 100, 4.7],
        hourglass_energy: [0, 20, 90, 113],
      },
    }),
  ),
}));

describe("CrashRunCharts", () => {
  it("kuvvet (ham + CFC), ivme (ham + CFC) ve enerji grafikleri; skalerler", async () => {
    render(<CrashRunCharts runId={50} title="#50 kızak" />);
    expect(await screen.findByRole("img", { name: "Kuvvet–zaman grafiği" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "İvme–zaman grafiği" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Enerji–zaman grafiği" })).toBeInTheDocument();
    const box = screen.getByTestId("crash-run-charts");
    expect(box).toHaveTextContent("Rijit duvar CFC600");
    expect(box).toHaveTextContent("|a| CFC1000");
    expect(box).toHaveTextContent("Kinetik enerji");
    expect(box).toHaveTextContent("Hourglass enerjisi");
    expect(box).toHaveTextContent("8000 g"); // CFC ivme tepesi, birim g
    expect(screen.getByTestId("crash-run-scalars")).toHaveTextContent("HIC15 CFC1000 2600000.0");
  });

  it("zaman üst sınırı yalnız görünümü kırpar", async () => {
    render(<CrashRunCharts runId={50} />);
    await screen.findByRole("img", { name: "Kuvvet–zaman grafiği" });
    fireEvent.change(screen.getByLabelText("Grafik zaman üst sınırı"), { target: { value: "1" } });
    const line = screen.getByRole("img", { name: "Kuvvet–zaman grafiği" }).querySelector("polyline");
    expect(line?.getAttribute("points")?.split(" ")).toHaveLength(2);
  });
});
