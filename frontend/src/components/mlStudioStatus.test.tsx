import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DoeStudyInfo } from "../api/doe";
import type { SurrogateStatus } from "../api/surrogate";
import MlTemplateChips from "./MlTemplateChips";
import { buildStageMeta, useMlStudioStatus } from "./mlStudioStatus";

vi.mock("../api/doe", () => ({ fetchDoeStudies: vi.fn() }));
vi.mock("../api/surrogate", () => ({ fetchCorpusList: vi.fn(), fetchSurrogateStatus: vi.fn() }));
vi.mock("../api/templates", () => ({ fetchTemplates: vi.fn() }));

import { fetchDoeStudies } from "../api/doe";
import { fetchCorpusList, fetchSurrogateStatus } from "../api/surrogate";
import { fetchTemplates } from "../api/templates";

const study = (id: number, template_id: string, status = "completed"): DoeStudyInfo => ({
  id,
  name: null,
  template_id,
  seed: 1,
  status,
  message: null,
  n_cases: 200,
  counts: {},
  cases: [],
});

const STATUS: SurrogateStatus = {
  template_id: "cantilever_beam",
  templates: { cantilever_beam: ["hybrid"] },
  scalar_rf: null,
  scalar_loglinear: null,
  scalar_hybrid: { metrics: { test: { max_von_mises: { r2: 0.99, mae: 1, mape: 0.0186 } } } },
  field_gnn: null,
};

describe("buildStageMeta", () => {
  it("aşama satırlarını şablona göre üretir", () => {
    const meta = buildStageMeta(
      { templateId: "cantilever_beam", runCount: 412, lastPredictionOod: true },
      [study(15, "plate_with_hole", "running"), study(14, "cantilever_beam")],
      [
        { name: "kiris_v3", frozen_at: null, n_runs: 184, template_id: "cantilever_beam", n_manual: 0 },
        { name: "plaka_v1", frozen_at: null, n_runs: 96, template_id: "plate_with_hole", n_manual: 0 },
      ],
      STATUS,
    );
    expect(meta).toEqual({
      doe: "#14 · 200 örnek",
      data: "412 run · 1 korpus",
      model: "hybrid · σ %1.86",
      pred: "son tahmin uzay dışı",
    });
  });

  it("veri yoksa açık söyler, tahmin yoksa satır bırakmaz", () => {
    const meta = buildStageMeta(
      { templateId: "flange", runCount: 0, lastPredictionOod: null },
      [study(3, "flange", "running")],
      [],
      { ...STATUS, scalar_hybrid: null, templates: {} },
    );
    expect(meta.doe).toBe("#3 · 200 örnek · çalışıyor");
    expect(meta.model).toBe("model yok");
    expect(meta.pred).toBeUndefined();
  });
});

describe("useMlStudioStatus + MlTemplateChips", () => {
  beforeEach(() => {
    vi.mocked(fetchTemplates).mockResolvedValue([
      { id: "cantilever_beam", name: "Ankastre kiriş" },
      { id: "plate_with_hole", name: "Delikli plaka" },
      { id: "flange", name: "Flanş" },
    ] as never);
    vi.mocked(fetchDoeStudies).mockResolvedValue([study(14, "cantilever_beam")]);
    vi.mocked(fetchCorpusList).mockResolvedValue([
      { name: "plaka_v1", frozen_at: null, n_runs: 96, template_id: "plate_with_hole", n_manual: 0 },
    ]);
    vi.mocked(fetchSurrogateStatus).mockResolvedValue(STATUS);
  });

  it("verisi olan şablonları çip yapar, seçimi iletir", async () => {
    const { result } = renderHook(() =>
      useMlStudioStatus({ templateId: "flange", runCount: 5, lastPredictionOod: null }),
    );
    await waitFor(() => expect(result.current.templatesWithData).toEqual(["cantilever_beam", "plate_with_hole"]));
    expect(result.current.meta.doe).toBe("çalışma yok");

    const onSelect = vi.fn();
    render(
      <MlTemplateChips
        templates={result.current.templates}
        withData={result.current.templatesWithData}
        activeId="flange"
        onSelect={onSelect}
      />,
    );
    const chips = screen.getAllByRole("button");
    expect(chips.map((c) => c.textContent)).toEqual(["Flanş", "Ankastre kiriş", "Delikli plaka"]);
    expect(chips[0]).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(chips[2]);
    expect(onSelect).toHaveBeenCalledWith("plate_with_hole");
  });
});
