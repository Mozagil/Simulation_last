import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashDoePanel from "./CrashDoePanel";
import { buildCrashDoeSpecFromForm, initialCrashDoeState } from "./CrashDoeSpecForm";

vi.mock("../api/crashMl", () => ({
  CrashMlApiError: class CrashMlApiError extends Error {},
  fetchCrashDoeStudies: vi.fn(),
  fetchCrashDoeStudy: vi.fn(),
  createCrashDoeStudy: vi.fn(),
  resumeCrashDoeStudy: vi.fn(),
}));
vi.mock("../api/crash", () => ({ fetchCrashCatalog: vi.fn(), fetchCrashJob: vi.fn() }));
vi.mock("../api/templates", () => ({ fetchTemplates: vi.fn() }));
vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn() }));

import {
  createCrashDoeStudy,
  fetchCrashDoeStudies,
  fetchCrashDoeStudy,
  resumeCrashDoeStudy,
} from "../api/crashMl";
import { fetchCrashCatalog, fetchCrashJob } from "../api/crash";
import { fetchTemplates } from "../api/templates";
import { fetchMaterials } from "../api/materials";

const STUDY = {
  id: 4,
  name: "kutu-v1",
  template_id: "crash_box_shell",
  seed: 1,
  status: "completed_with_errors",
  message: "1/2 başarılı",
  created_at: null,
  vary: { speed_m_s: [5, 15] as [number, number] },
  n_cases: 2,
  counts: { solved: 1, failed: 1 },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchCrashCatalog).mockResolvedValue({
    entries: [
      { id: "crash_box", sector: "otomotiv", title: "Crash box eksenel ezilme", status: "ready",
        template_id: "crash_box_shell", mesh_dim: 2, reference: "", validation: "", infrastructure: "", step: "" },
    ],
    scenario_templates: { crash_box_shell: 2, plate_ball_shell: 2 },
  } as never);
  vi.mocked(fetchTemplates).mockResolvedValue([
    { id: "crash_box_shell", name: "Kutu", description: "", tags: [], regions: [], has_analytic: false,
      params_schema: { properties: { wall: { type: "number", default: 3, unit: "mm", symbol: "t" }, box_length: { type: "number", default: 300, unit: "mm", symbol: "L" } } } },
  ] as never);
  vi.mocked(fetchMaterials).mockResolvedValue([{ id: 1, name: "S235" }, { id: 2, name: "6061-T6" }] as never);
  vi.mocked(fetchCrashDoeStudies).mockResolvedValue([STUDY]);
  vi.mocked(fetchCrashDoeStudy).mockResolvedValue({
    ...STUDY,
    cases: [
      { id: 1, index: 0, status: "solved", values: { speed_m_s: 7.25 }, geometry_id: 9, run_id: 31, message: "OpenRadioss bitti" },
      { id: 2, index: 1, status: "failed", values: { speed_m_s: 12.5 }, geometry_id: null, run_id: null, message: "mesh hatası" },
    ],
  });
});

describe("buildCrashDoeSpecFromForm (1.28a)", () => {
  const TPL = { id: "crash_box_shell", name: "Crash box", params_schema: { properties: { wall: { type: "number", default: 3 }, box_length: { type: "number", default: 300 } } } } as never;

  it("şablon varsayılanından form: geometri ±%20 aralık, hız aralık, süre/eleman sabit", () => {
    const st = initialCrashDoeState(TPL);
    expect(st.geometry.wall).toEqual({ mode: "range", fixed: "3", min: "2.4", max: "3.6" });
    expect(st.scenario.speed_m_s.mode).toBe("range");
    expect(st.scenario.t_end_ms).toMatchObject({ mode: "fixed", fixed: "20" });
    expect(st.materialName).toBe("S235");
  });

  it("form → base + vary; sabitler base.geometry'ye, aralıklar vary'ye; gelişmiş JSON tabana eklenir", () => {
    const st = initialCrashDoeState(TPL);
    st.geometry.box_length = { mode: "fixed", fixed: "250", min: "", max: "" };
    st.extraJson = '{"model": {"sigma_y_pa": 2.35e8}}';
    st.name = "deneme";
    const spec = buildCrashDoeSpecFromForm(st);
    expect(spec.base).toEqual({
      template_id: "crash_box_shell", material_name: "S235", t_end_ms: 20, element_size_mm: 5,
      geometry: { box_length: 250 }, model: { sigma_y_pa: 2.35e8 },
    });
    expect(spec.vary).toEqual({ "geometry.wall": [2.4, 3.6], speed_m_s: [8, 12] });
    expect(spec).toMatchObject({ name: "deneme", n_samples: 20, seed: 1 });
  });

  it("hatalı girdiler açık hata verir", () => {
    const st = initialCrashDoeState(TPL);
    expect(() => buildCrashDoeSpecFromForm({ ...st, geometry: { wall: { mode: "range", fixed: "3", min: "4", max: "4" } } })).toThrow(/üst sınır/);
    const allFixed = { ...st, geometry: { wall: { mode: "fixed" as const, fixed: "3", min: "", max: "" } }, scenario: { ...st.scenario, speed_m_s: { mode: "fixed" as const, fixed: "10", min: "", max: "" } } };
    expect(() => buildCrashDoeSpecFromForm(allFixed)).toThrow(/En az bir/);
    expect(() => buildCrashDoeSpecFromForm({ ...st, nSamples: "0" })).toThrow(/1–500/);
    expect(() => buildCrashDoeSpecFromForm({ ...st, extraJson: "{" })).toThrow(/JSON/);
  });
});

describe("CrashDoePanel", () => {
  it("çalışma ilerlemesini ve örnek tablosunu gösterir, devam ettirir", async () => {
    vi.mocked(resumeCrashDoeStudy).mockResolvedValue(STUDY);
    render(<CrashDoePanel />);
    expect(await screen.findByText("#4 · kutu-v1")).toBeInTheDocument();
    expect(await screen.findByText("7.250")).toBeInTheDocument();
    expect(screen.getByText("mesh hatası")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Devam ettir (1)" }));
    await waitFor(() => expect(resumeCrashDoeStudy).toHaveBeenCalledWith(4));
  });

  it("şablon parametreleri Aralık/Sabit satırları olarak gelir; malzeme çipi; DOE başlat form gövdesini yollar", async () => {
    vi.mocked(createCrashDoeStudy).mockResolvedValue({ ...STUDY, id: 5 });
    render(<CrashDoePanel />);
    expect(await screen.findByLabelText("wall alt")).toHaveValue(2.4);
    expect(screen.getByLabelText("Çarpma hızı alt")).toHaveValue(8);
    fireEvent.click(screen.getByRole("button", { name: "6061-T6" }));
    fireEvent.change(screen.getByLabelText("wall üst"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "DOE başlat" }));
    await waitFor(() => expect(createCrashDoeStudy).toHaveBeenCalled());
    const spec = vi.mocked(createCrashDoeStudy).mock.calls[0][0];
    expect(spec.base).toMatchObject({ template_id: "crash_box_shell", material_name: "6061-T6" });
    expect(spec.vary).toEqual({ "geometry.wall": [2.4, 4], "geometry.box_length": [240, 360], speed_m_s: [8, 12] });
    expect(spec.n_samples).toBe(20);
  });

  it("şablon değişince geometri satırları yeni şablondan kurulur", async () => {
    vi.mocked(fetchTemplates).mockResolvedValue([
      { id: "crash_box_shell", name: "Crash box", params_schema: { properties: { wall: { type: "number", default: 3 } } } },
      { id: "plate_ball_shell", name: "Plaka", params_schema: { properties: { plate_t: { type: "number", default: 2, unit: "mm" } } } },
    ] as never);
    render(<CrashDoePanel />);
    await screen.findByLabelText("wall alt");
    fireEvent.click(screen.getByRole("button", { name: "plate_ball" }));
    expect(await screen.findByLabelText("plate_t alt")).toBeInTheDocument();
    expect(screen.queryByLabelText("wall alt")).not.toBeInTheDocument();
  });
});

describe("1.25a2 — DOE canlı ilerleme", () => {
  it("çalışan örneğin işi yoklanır: örnek no + canlı değerler; çalışma bitmişken panel yok", async () => {
    const RUN = { ...STUDY, status: "running", counts: { solved: 1, running: 1 }, current_job_id: "abcdef12-0000", current_case_index: 1 };
    vi.mocked(fetchCrashDoeStudies).mockResolvedValue([RUN]);
    vi.mocked(fetchCrashDoeStudy).mockResolvedValue({ ...RUN, cases: [] });
    vi.mocked(fetchCrashJob).mockResolvedValue({ job_id: "abcdef12-0000", status: "pending", cycle: 3700, time_ms: 2, percent: 49.95 });
    render(<CrashDoePanel />);
    const live = await screen.findByTestId("crash-doe-live");
    expect(live).toHaveTextContent("Örnek #1");
    expect(live).toHaveTextContent("iş abcdef12");
    await waitFor(() => expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım3700"));
    expect(screen.getByTestId("crash-live-phase")).toHaveTextContent("Koşuyor");
    expect(fetchCrashJob).toHaveBeenCalledWith("abcdef12-0000");
  });

  it("çalışan iş yoksa (bitmiş çalışma) canlı panel gösterilmez", async () => {
    render(<CrashDoePanel />);
    expect(await screen.findByText("#4 · kutu-v1")).toBeInTheDocument();
    expect(screen.queryByTestId("crash-doe-live")).not.toBeInTheDocument();
    expect(fetchCrashJob).not.toHaveBeenCalled();
  });
});
