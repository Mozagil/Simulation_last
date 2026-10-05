import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

/** K12 — kuş çarpması: kuş kütlesi ve boy/çap. */

vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn(() => Promise.resolve([{ id: 1, name: "S235" }])) }));

const num = (d: number, symbol: string, unit = "mm") => ({ type: "number", default: d, symbol, unit });

vi.mock("../api/templates", () => ({
  fetchTemplates: vi.fn(() =>
    Promise.resolve([
      { id: "blast_plate_shell", name: "Kaput", description: "", tags: ["crash"], regions: [], has_analytic: false,
        params_schema: { properties: { size_x: num(200, "a"), size_z: num(50, "c"), rot_x: num(0, "rx", "°") } } },
    ]),
  ),
}));

vi.mock("../api/crash", () => ({
  fetchCrashCatalog: vi.fn(() =>
    Promise.resolve({
      scenario_templates: { blast_plate_shell: 2 },
      entries: [
        { id: "bird_strike", sector: "otomotiv", title: "Kaput", status: "ready", template_id: "blast_plate_shell",
          mesh_dim: 2, reference: "literatür", validation: "4Mp/L", infrastructure: "", step: "K5", defaults: { extras: { birdKg: "1.82", ld: "2" }, common: { speed: "150" } } },
      ],
    }),
  ),
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 1, scenario: {}, crash: { job_id: "j", run_id: 9, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "j", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard — kuş çarpması", () => {
  it("kuş kütlesi, boy/çap ve hız istekte", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("Kuş kütlesi (kg)")).toHaveValue("1.82"));
    expect(screen.getByLabelText("v₀ (m/s)")).toHaveValue("150");
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("blast_plate_shell");
    expect(body.bird_mass_kg).toBe(1.82);
    expect(body.bird_ld).toBe(2);
    expect(body.speed_m_s).toBe(150);
  });
});
