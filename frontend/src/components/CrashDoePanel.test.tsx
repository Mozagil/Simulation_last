import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashDoePanel, { buildCrashDoeSpec } from "./CrashDoePanel";

vi.mock("../api/crashMl", () => ({
  CrashMlApiError: class CrashMlApiError extends Error {},
  fetchCrashDoeStudies: vi.fn(),
  fetchCrashDoeStudy: vi.fn(),
  createCrashDoeStudy: vi.fn(),
  resumeCrashDoeStudy: vi.fn(),
}));
vi.mock("../api/crash", () => ({ fetchCrashCatalog: vi.fn() }));
vi.mock("../api/templates", () => ({ fetchTemplates: vi.fn() }));

import {
  createCrashDoeStudy,
  fetchCrashDoeStudies,
  fetchCrashDoeStudy,
  resumeCrashDoeStudy,
} from "../api/crashMl";
import { fetchCrashCatalog } from "../api/crash";
import { fetchTemplates } from "../api/templates";

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
      params_schema: { properties: { wall: { type: "number" }, box_length: { type: "number" } } } },
  ]);
  vi.mocked(fetchCrashDoeStudies).mockResolvedValue([STUDY]);
  vi.mocked(fetchCrashDoeStudy).mockResolvedValue({
    ...STUDY,
    cases: [
      { id: 1, index: 0, status: "solved", values: { speed_m_s: 7.25 }, geometry_id: 9, run_id: 31, message: "OpenRadioss bitti" },
      { id: 2, index: 1, status: "failed", values: { speed_m_s: 12.5 }, geometry_id: null, run_id: null, message: "mesh hatası" },
    ],
  });
});

describe("buildCrashDoeSpec", () => {
  it("taban + aralıklar → istek gövdesi", () => {
    const spec = buildCrashDoeSpec(
      '{"template_id":"crash_box_shell","t_end_ms":6}',
      [{ path: "speed_m_s", lo: "5", hi: "15" }, { path: " ", lo: "", hi: "" }],
      "200",
      "3",
      "kutu-v1",
    );
    expect(spec).toEqual({
      name: "kutu-v1",
      base: { template_id: "crash_box_shell", t_end_ms: 6 },
      vary: { speed_m_s: [5, 15] },
      n_samples: 200,
      seed: 3,
    });
  });

  it("hatalı girdiler açık hata verir", () => {
    expect(() => buildCrashDoeSpec("{", [], "1", "0", "")).toThrow(/JSON/);
    expect(() => buildCrashDoeSpec("{}", [], "1", "0", "")).toThrow(/En az bir/);
    expect(() => buildCrashDoeSpec("{}", [{ path: "a", lo: "2", hi: "2" }], "1", "0", "")).toThrow(/üst sınır/);
    expect(() => buildCrashDoeSpec("{}", [{ path: "a", lo: "1", hi: "2" }], "0", "0", "")).toThrow(/1–500/);
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

  it("şablon seçimi taban senaryoyu günceller, DOE başlatır", async () => {
    vi.mocked(createCrashDoeStudy).mockResolvedValue({ ...STUDY, id: 5 });
    render(<CrashDoePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "plate_ball" }));
    const base = screen.getByLabelText("Taban senaryo") as HTMLTextAreaElement;
    expect(JSON.parse(base.value).template_id).toBe("plate_ball_shell");
    fireEvent.click(screen.getByRole("button", { name: "DOE başlat" }));
    await waitFor(() => expect(createCrashDoeStudy).toHaveBeenCalled());
    const spec = vi.mocked(createCrashDoeStudy).mock.calls[0][0];
    expect(spec.base.template_id).toBe("plate_ball_shell");
    expect(spec.vary).toEqual({ speed_m_s: [5, 15] });
    expect(spec.n_samples).toBe(20);
  });

  it("şablon parametreleri yol önerisi olarak gelir", async () => {
    const { container } = render(<CrashDoePanel />);
    await waitFor(() =>
      expect(container.querySelector('#crash-doe-paths option[value="geometry.wall"]')).not.toBeNull(),
    );
  });
});
