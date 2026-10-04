import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

/** K5 — kafa impaktörü: katalog başlangıç değerleri + toplam kütle + CFC1000. */

vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn(() => Promise.resolve([{ id: 1, name: "S235" }])) }));

const num = (d: number, symbol: string, unit = "mm") => ({ type: "number", default: d, symbol, unit });

vi.mock("../api/templates", () => ({
  fetchTemplates: vi.fn(() =>
    Promise.resolve([
      { id: "plate_ball_shell", name: "Kaput", description: "", tags: ["crash"], regions: [], has_analytic: false,
        params_schema: { properties: { size_x: num(200, "a"), size_z: num(50, "c"), rot_x: num(0, "rx", "°") } } },
    ]),
  ),
}));

vi.mock("../api/crash", () => ({
  fetchCrashCatalog: vi.fn(() =>
    Promise.resolve({
      scenario_templates: { plate_ball_shell: 2 },
      entries: [
        { id: "head_impactor", sector: "otomotiv", title: "Kaput", status: "ready", template_id: "plate_ball_shell",
          mesh_dim: 2, reference: "literatür", validation: "4Mp/L", infrastructure: "", step: "K5", defaults: { geometry: { size_x: 600 }, extras: { ballTotal: "4.5" }, common: { speed: "11.1" }, acc_cfc: 1000 } },
      ],
    }),
  ),
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 1, scenario: {}, crash: { job_id: "j", run_id: 9, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "j", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard — kafa impaktörü", () => {
  it("katalog başlangıç değerleri; toplam kütle ve acc CFC1000 istekte", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("a (mm)")).toHaveValue("600"));
    expect(screen.getByLabelText("v₀ (m/s)")).toHaveValue("11.1");
    expect(screen.getByLabelText("Küre toplam kütle (kg)")).toHaveValue("4.5");
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("plate_ball_shell");
    expect(body.ball_total_mass_kg).toBe(4.5);
    expect(body.speed_m_s).toBe(11.1);
    expect(body.filters).toEqual({ force_cfc: null, acc_cfc: 1000 });
  });
});
