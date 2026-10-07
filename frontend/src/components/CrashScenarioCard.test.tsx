import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

vi.mock("../api/materials", () => ({
  fetchMaterials: vi.fn(() =>
    Promise.resolve([
      { id: 3, name: "6061-T6" },
      { id: 1, name: "S235" },
    ]),
  ),
}));

const num = (d: number, symbol: string, unit = "mm") => ({ type: "number", default: d, symbol, unit });

vi.mock("../api/templates", () => ({
  fetchTemplates: vi.fn(() =>
    Promise.resolve([
      { id: "crash_box_shell", name: "Crash box", description: "", tags: [], regions: [], has_analytic: false,
        params_schema: { properties: { box_length: num(300, "L"), box_height: num(50, "h"), box_width: num(40, "b"), wall: num(3, "t") } } },
      { id: "plate_ball_shell", name: "Plaka–küre", description: "", tags: [], regions: [], has_analytic: false,
        params_schema: { properties: { plate_size: num(300, "a"), plate_thickness: num(5, "t"), ball_diameter: num(50, "D"), gap: num(1, "g") } } },
    ]),
  ),
}));

vi.mock("../api/crash", () => ({
  fetchCrashCatalog: vi.fn(() =>
    Promise.resolve({
      scenario_templates: { crash_box_shell: 2, plate_ball_shell: 2 },
      entries: [
        { id: "crash_box", sector: "otomotiv", title: "Crash box eksenel ezilme", status: "ready",
          template_id: "crash_box_shell", mesh_dim: 2, reference: "RD-E 1700", validation: "V1–V3", infrastructure: "", step: "" },
        { id: "taylor_bar", sector: "savunma", title: "Taylor çubuğu", status: "planned",
          template_id: null, mesh_dim: null, reference: "Taylor (1948)", validation: "L/L0", infrastructure: "solid", step: "K1" },
        { id: "plate_perforation", sector: "savunma", title: "Plaka delinme", status: "ready",
          template_id: "plate_ball_shell", mesh_dim: 2, reference: "RD-E 2600", validation: "V4 V5", infrastructure: "", step: "" },
      ],
    }),
  ),
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 4000, scenario: {}, crash: { job_id: "jx", run_id: 77, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "jx", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard", () => {
  it("katalogdaki hazır örnekleri listeler (planlı olanı değil); geometri alanları şablon şemasından", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("L (mm)")).toHaveValue("300"));
    const opts = [...(screen.getByLabelText("Senaryo şablonu") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).toEqual(["crash_box", "plate_perforation"]);
    expect(screen.getByText(/Referans: RD-E 1700/)).toBeInTheDocument();
  });

  it("crash box: şablon parametreleri, kızak (rijit gövde) ve CFC ile senaryo gönderir; S235 varsayılan", async () => {
    vi.mocked(postCrashScenario).mockClear();
    const onDone = vi.fn();
    render(<CrashScenarioCard onDone={onDone} />);
    await waitFor(() => expect(screen.getByLabelText("Senaryo malzemesi")).toHaveValue("1"));
    await waitFor(() => expect(screen.getByLabelText("L (mm)")).toHaveValue("300"));
    fireEvent.change(screen.getByLabelText("L (mm)"), { target: { value: "250" } });
    fireEvent.change(screen.getByLabelText("Kızak (kg)"), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText("Senaryo kuvvet CFC"), { target: { value: "600" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("crash_box_shell");
    expect(body.geometry).toEqual({ box_length: 250, box_height: 50, box_width: 40, wall: 3 });
    expect(body.material_id).toBe(1);
    expect(body.rigid_bodies).toEqual([{ name: "kizak", region: "kutu_arka", mass_kg: 50 }]);
    expect(body.filters).toEqual({ force_cfc: 600, acc_cfc: null });
    expect(body.wait).toBe(false);
    expect(await screen.findByTestId("crash-scenario-status")).toHaveTextContent("koşu #77 · geometri 4000");
    expect(onDone).toHaveBeenCalled();
  });

  it("geçersiz sayı hata", async () => {
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("t (mm)")).toHaveValue("3"));
    fireEvent.change(screen.getByLabelText("t (mm)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    expect(await screen.findByText(/t: sayı geçersiz/)).toBeInTheDocument();
  });

  it("plaka–küre: şema alanları + küre kütlesi / kabuk kalınlığı; kızak alanı yok", async () => {
    vi.mocked(postCrashScenario).mockClear();
    render(<CrashScenarioCard />);
    await waitFor(() => expect(screen.getByLabelText("Senaryo malzemesi")).toHaveValue("1"));
    await waitFor(() => expect(screen.getByLabelText("L (mm)")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Senaryo şablonu"), { target: { value: "plate_perforation" } });
    await waitFor(() => expect(screen.getByLabelText("D (mm)")).toHaveValue("50"));
    expect(screen.queryByLabelText("Kızak (kg)")).not.toBeInTheDocument();
    expect(screen.getByText(/Plaka kenarı sabit/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("D (mm)"), { target: { value: "40" } });
    fireEvent.change(screen.getByLabelText("Küre ek kütle (kg)"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("v₀ (m/s)"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.template_id).toBe("plate_ball_shell");
    expect(body.geometry).toEqual({ plate_size: 300, plate_thickness: 5, ball_diameter: 40, gap: 1 });
    expect(body.ball_mass_kg).toBe(2);
    expect(body.ball_thickness_mm).toBe(1);
    expect(body.speed_m_s).toBe(30);
    expect(body.rigid_bodies).toBeUndefined();
  });

  it("senaryonun ürettiği geometriyi App'e bildirir (TODO 11.6: viewport boş kalmasın)", async () => {
    vi.mocked(postCrashScenario).mockClear();
    const onGeometry = vi.fn();
    render(<CrashScenarioCard onGeometry={onGeometry} />);
    await waitFor(() => expect(screen.getByLabelText("Senaryo malzemesi")).toHaveValue("1"));
    await waitFor(() => expect(screen.getByLabelText("L (mm)")).toHaveValue("300"));
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(onGeometry).toHaveBeenCalledWith(4000, "crash_box_shell.step"));
  });
});
