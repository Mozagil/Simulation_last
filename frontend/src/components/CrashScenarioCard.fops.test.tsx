import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

/** K6 — FOPS: örneğe özgü ek alanlar (H, g, toplam kütle). */

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
        { id: "fops", sector: "otomotiv", title: "Kaput", status: "ready", template_id: "plate_ball_shell",
          mesh_dim: 2, reference: "literatür", validation: "4Mp/L", infrastructure: "", step: "K5", defaults: { extras: { ballTotal: "227", height: "5210" } } },
      ],
    }),
  ),
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 1, scenario: {}, crash: { job_id: "j", run_id: 9, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "j", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard — FOPS", () => {
  it("H, g ve toplam kütle istekte (örneğe özgü ek alanlar)", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("H düşme (mm)")).toHaveValue("5210"));
    expect(screen.getByLabelText("Küre toplam kütle (kg)")).toHaveValue("227");
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("plate_ball_shell");
    expect(body.drop_height_mm).toBe(5210);
    expect(body.ball_total_mass_kg).toBe(227);
    expect(body.gravity).toEqual({ accel_m_s2: -9.81, direction: "Z" });
  });
});
