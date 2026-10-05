import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

/** K3 — direk: çap ve uç kütlesi istekte. */

vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn(() => Promise.resolve([{ id: 1, name: "S235" }])) }));

const num = (d: number, symbol: string, unit = "mm") => ({ type: "number", default: d, symbol, unit });

vi.mock("../api/templates", () => ({
  fetchTemplates: vi.fn(() =>
    Promise.resolve([
      { id: "pole_beam_shell", name: "Direk", description: "", tags: ["crash"], regions: [], has_analytic: false,
        params_schema: { properties: { size_x: num(200, "a"), size_z: num(50, "c"), rot_x: num(0, "rx", "°") } } },
    ]),
  ),
}));

vi.mock("../api/crash", () => ({
  fetchCrashCatalog: vi.fn(() =>
    Promise.resolve({
      scenario_templates: { pole_beam_shell: 2 },
      entries: [
        { id: "pole_side", sector: "otomotiv", title: "Direk yan çarpması", status: "ready", template_id: "pole_beam_shell",
          mesh_dim: 2, reference: "literatür", validation: "4Mp/L", infrastructure: "", step: "K3" },
      ],
    }),
  ),
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 1, scenario: {}, crash: { job_id: "j", run_id: 9, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "j", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard — direk yan çarpması", () => {
  it("direk çapı ve uç kütlesi istekte", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("Direk Ø (mm)")).toHaveValue("254"));
    fireEvent.change(screen.getByLabelText("Uç kütlesi (kg, her biri)"), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("pole_beam_shell");
    expect(body.pole_diameter_mm).toBe(254);
    expect(body.end_mass_kg).toBe(25);
    expect(body.drop_height_mm).toBeUndefined();
  });
});
