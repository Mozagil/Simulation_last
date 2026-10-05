import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

/** K2 — düşme testi: H ve g ek alanları istekte drop_height_mm + gravity. */

vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn(() => Promise.resolve([{ id: 1, name: "S235" }])) }));

const num = (d: number, symbol: string, unit = "mm") => ({ type: "number", default: d, symbol, unit });

vi.mock("../api/templates", () => ({
  fetchTemplates: vi.fn(() =>
    Promise.resolve([
      { id: "drop_box_shell", name: "Düşme", description: "", tags: ["crash"], regions: [], has_analytic: false,
        params_schema: { properties: { size_x: num(200, "a"), size_z: num(50, "c"), rot_x: num(0, "rx", "°"),
                                       gap: num(1, "g"), floor_size: num(0, "F") } } },
    ]),
  ),
}));

vi.mock("../api/crash", () => ({
  fetchCrashCatalog: vi.fn(() =>
    Promise.resolve({
      scenario_templates: { drop_box_shell: 2 },
      entries: [
        { id: "drop_test", sector: "otomotiv", title: "Düşme testi", status: "ready", template_id: "drop_box_shell",
          mesh_dim: 2, reference: "RD-E 0600", validation: "√(2gH)", infrastructure: "", step: "K2" },
      ],
    }),
  ),
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 1, scenario: {}, crash: { job_id: "j", run_id: 9, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "j", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard — düşme testi", () => {
  it("H ve g istekte; açı alanı şablon şemasından (°)", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("H düşme (mm)")).toHaveValue("1000"));
    expect(screen.getByLabelText("rx (°)")).toHaveValue("0");
    fireEvent.change(screen.getByLabelText("rx (°)"), { target: { value: "45" } });
    fireEvent.change(screen.getByLabelText("H düşme (mm)"), { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("drop_box_shell");
    expect(body.geometry).toEqual({ size_x: 200, size_z: 50, rot_x: 45, gap: 1, floor_size: 0 });
    expect(body.drop_height_mm).toBe(1500);
    expect(body.gravity).toEqual({ accel_m_s2: -9.81, direction: "Z" });
    expect(body.model).toBeUndefined(); // Ishell 0 → sunucu varsayılanı
  });

  it("zemin plakası (F) ve Ishell seçimi istekte; seçim mühendisin", async () => {
    vi.mocked(postCrashScenario).mockClear();
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("F (mm)")).toHaveValue("0"));
    fireEvent.change(screen.getByLabelText("F (mm)"), { target: { value: "400" } });
    fireEvent.change(screen.getByLabelText("g (mm)"), { target: { value: "5" } });
    const ishell = screen.getByLabelText("Senaryo Ishell");
    expect([...(ishell as HTMLSelectElement).options].map((o) => o.value)).toEqual(["0", "1", "2", "3", "4", "12", "24"]);
    fireEvent.change(ishell, { target: { value: "24" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.geometry).toMatchObject({ gap: 5, floor_size: 400 });
    expect(body.model).toEqual({ law: "plastic", shell: { ishell: 24 } });
    expect(body.name).toContain("Ishell 24");
  });
});
