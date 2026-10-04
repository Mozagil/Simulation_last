import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

/** K4 — ROPS: itme hızı istekte. */

vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn(() => Promise.resolve([{ id: 1, name: "S235" }])) }));

const num = (d: number, symbol: string, unit = "mm") => ({ type: "number", default: d, symbol, unit });

vi.mock("../api/templates", () => ({
  fetchTemplates: vi.fn(() =>
    Promise.resolve([
      { id: "rops_frame_shell", name: "ROPS", description: "", tags: ["crash"], regions: [], has_analytic: false,
        params_schema: { properties: { size_x: num(200, "a"), size_z: num(50, "c"), rot_x: num(0, "rx", "°") } } },
    ]),
  ),
}));

vi.mock("../api/crash", () => ({
  fetchCrashCatalog: vi.fn(() =>
    Promise.resolve({
      scenario_templates: { rops_frame_shell: 2 },
      entries: [
        { id: "rops", sector: "otomotiv", title: "ROPS", status: "ready", template_id: "rops_frame_shell",
          mesh_dim: 2, reference: "literatür", validation: "4Mp/L", infrastructure: "", step: "K4" },
      ],
    }),
  ),
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 1, scenario: {}, crash: { job_id: "j", run_id: 9, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "j", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard — ROPS", () => {
  it("itme hızı istekte", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("İtme hızı (m/s)")).toHaveValue("1"));
    fireEvent.change(screen.getByLabelText("İtme hızı (m/s)"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("rops_frame_shell");
    expect(body.push_speed_m_s).toBe(0.5);
  });
});
