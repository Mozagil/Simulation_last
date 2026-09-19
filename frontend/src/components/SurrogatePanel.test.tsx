import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SurrogatePanel from "./SurrogatePanel";

vi.mock("../api/templates", () => ({ fetchTemplates: vi.fn() }));
vi.mock("../api/surrogate", () => ({
  SurrogateApiError: class SurrogateApiError extends Error {},
  fetchSurrogateStatus: vi.fn(),
  fetchCorpusList: vi.fn(),
  freezeCorpus: vi.fn(),
  evaluateForCorpus: vi.fn(),
  addRunsToCorpus: vi.fn(),
  trainScalarRf: vi.fn(),
  trainFieldGnn: vi.fn(),
  predictSurrogate: vi.fn(),
  predictFromParams: vi.fn(),
}));

import {
  addRunsToCorpus,
  evaluateForCorpus,
  fetchCorpusList,
  fetchSurrogateStatus,
  freezeCorpus,
  predictFromParams,
  predictSurrogate,
  trainScalarRf,
} from "../api/surrogate";
import { fetchTemplates } from "../api/templates";

const CANTILEVER = {
  id: "cantilever_beam",
  name: "Ankastre kiriş",
  description: "",
  tags: [],
  params_schema: {
    properties: {
      length: { type: "number", default: 500, unit: "mm", title: "Uzunluk", symbol: "L" },
      thickness: { type: "number", default: 10, unit: "mm", title: "Kalınlık", symbol: "T" },
      width: { type: "number", default: 50, unit: "mm", title: "Genişlik", symbol: "W" },
    },
  },
  regions: [],
  has_analytic: true,
  has_characteristic_length: true,
  default_bcs: [],
};

describe("SurrogatePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchSurrogateStatus).mockReset();
    vi.mocked(trainScalarRf).mockReset();
    vi.mocked(predictSurrogate).mockReset();
    vi.mocked(predictFromParams).mockReset();
    vi.mocked(fetchCorpusList).mockReset();
    vi.mocked(freezeCorpus).mockReset();
    vi.mocked(evaluateForCorpus).mockReset();
    vi.mocked(addRunsToCorpus).mockReset();
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null,
      scalar_loglinear: null,
      scalar_hybrid: null,
      templates: {},
      field_gnn: null,
    });
    vi.mocked(fetchCorpusList).mockResolvedValue([]);
    vi.mocked(fetchTemplates).mockResolvedValue([CANTILEVER] as never);
  });

  it("RF eğit ve hızlı tahmin çağırır", async () => {
    vi.mocked(trainScalarRf).mockResolvedValue({
      n_samples: 16,
      metrics: { test: { max_displacement: { r2: 0.9, mae: 1, mape: 0.1 } } },
    });
    const onPrediction = vi.fn();
    vi.mocked(predictSurrogate).mockResolvedValue({
      kind: "scalar",
      source: "surrogate",
      out_of_domain: false,
      run_id: 4,
      geometry_id: 1,
      field_metrics: null,
      message: "Tahmin — tam çözüm değil.",
      preview: {
        node_ids: [],
        nodes: [],
        displacement_magnitude: [],
        displacement_vectors: [],
        von_mises: [],
        max_displacement: 21,
        max_von_mises: 200,
        critical_node_id: null,
        modes: [],
        source: "surrogate_scalar",
      },
    });
    render(<SurrogatePanel geometryId={1} runId={4} onPrediction={onPrediction} />);
    fireEvent.click(await screen.findByRole("button", { name: /Hibrit .* eğit/ }));
    await waitFor(() => expect(trainScalarRf).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Açık run tahmini" }));
    await waitFor(() => expect(predictSurrogate).toHaveBeenCalledTimes(1));
    expect(predictSurrogate).toHaveBeenCalledWith({ runId: 4, geometryId: 1 });
    await waitFor(() => expect(onPrediction).toHaveBeenCalledTimes(1));
  });

  it("parametreyle tahmin ccx/run istemez ve sayıları gösterir", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: { n_samples: 22, has_holdout: true, metrics: { test: { max_displacement: { r2: -3.9, mae: 1, mape: 1 } } } },
      scalar_loglinear: null,
      scalar_hybrid: null,
      templates: {},
      field_gnn: null,
    });
    vi.mocked(predictFromParams).mockResolvedValue({
      kind: "scalar",
      source: "surrogate",
      out_of_domain: false,
      predictions: { max_displacement: 24.1, max_von_mises: 310 },
      features: {},
      fea: { run_id: 4, geometry_id: 1, max_displacement: 23.9, max_von_mises: 330 },
      deviation_pct: { max_displacement_pct: 0.8, max_von_mises_pct: -6.1 },
      message: "Tahmin — ccx çalışmadı, tam çözüm değil. FEA kıyası eklendi.",
    });
    render(<SurrogatePanel geometryId={1} runId={4} />);
    // Şablon listesi asenkron gelir; form alanları ondan sonra kurulur.
    fireEvent.change(await screen.findByLabelText(/L · Uzunluk/), {
      target: { value: "520" },
    });
    fireEvent.change(screen.getByLabelText("Fy (N)"), { target: { value: "-400" } });
    fireEvent.click(await screen.findByRole("button", { name: "Parametreyle tahmin" }));
    await waitFor(() => expect(predictFromParams).toHaveBeenCalledTimes(1));
    expect(predictFromParams).toHaveBeenCalledWith(
      expect.objectContaining({
        template_id: "cantilever_beam",
        params: expect.objectContaining({ length: 520, thickness: 10, width: 50 }),
        load_fy: -400,
        compare_run_id: 4,
      }),
      // Bu senaryoda yalnız RF eğitilmiş; seçici mevcut türe geçer.
      "rf",
    );
    expect(await screen.findByText(/Tahmin u_max/)).toBeInTheDocument();
    expect(screen.getByText(/24.100 mm/)).toBeInTheDocument();
    expect(screen.getByText(/FEA u_max \(run 4\)/)).toBeInTheDocument();
  });

  it("seti dondurur ve eğitimi o setle çalıştırır", async () => {
    vi.mocked(freezeCorpus).mockResolvedValue({ manifest: { run_ids: [1, 2, 3] } });
    vi.mocked(fetchCorpusList).mockResolvedValueOnce([]).mockResolvedValue([
      { name: "kiris-v1", frozen_at: null, n_runs: 3, template_id: "cantilever_beam", n_manual: 0 },
    ]);
    vi.mocked(trainScalarRf).mockResolvedValue({
      n_samples: 3,
      corpus: { source: "manifest", name: "kiris-v1", template_id: "cantilever_beam" },
      metrics: { test: { max_displacement: { r2: 0.74, mae: 1, mape: 0.1 } } },
    });
    const onCorpusChange = vi.fn();
    render(<SurrogatePanel geometryId={1} runId={4} onCorpusChange={onCorpusChange} />);

    fireEvent.click(await screen.findByRole("button", { name: "Seti dondur" }));
    await waitFor(() => expect(freezeCorpus).toHaveBeenCalledWith("kiris-v1"));
    await waitFor(() => expect(onCorpusChange).toHaveBeenCalledWith("kiris-v1"));
    expect(await screen.findByText(/Set donduruldu: kiris-v1 · 3 run/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Hibrit .* eğit/ }));
    await waitFor(() =>
      expect(trainScalarRf).toHaveBeenCalledWith("kiris-v1", "hybrid"),
    );
    expect(await screen.findByText(/set kiris-v1/)).toBeInTheDocument();
  });

  it("karne süzgeci geçmeyen run için override ile ekler", async () => {
    vi.mocked(fetchCorpusList).mockResolvedValue([
      { name: "kiris-v1", frozen_at: null, n_runs: 8, template_id: "cantilever_beam", n_manual: 0 },
    ]);
    vi.mocked(evaluateForCorpus).mockResolvedValue({
      already_present: [],
      verdicts: [
        {
          run_id: 263,
          ok: false,
          reason: "large_displacement",
          u_over_L: 0.1756,
          mesh_ratio: 1.11,
          mesh_deviation: 0.308,
          template_id: "cantilever_beam",
          youngs_modulus: 6.89e10,
        },
      ],
    });
    vi.mocked(addRunsToCorpus).mockResolvedValue({
      name: "kiris-v1",
      n_runs: 9,
      added: [263],
      rejected: [],
      already_present: [],
      verdicts: [],
    });
    render(<SurrogatePanel geometryId={1} runId={263} />);

    fireEvent.change(await screen.findByLabelText("Kullanılan set"), {
      target: { value: "kiris-v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run 263 karnesi" }));
    await waitFor(() => expect(evaluateForCorpus).toHaveBeenCalledWith("kiris-v1", [263]));
    expect(await screen.findByText(/u\/L eşiği aşıldı/)).toBeInTheDocument();
    expect(screen.getByText("0.176")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Yine de ekle (override)" }));
    await waitFor(() =>
      expect(addRunsToCorpus).toHaveBeenCalledWith("kiris-v1", [263], true),
    );
    expect(await screen.findByText(/sete eklendi \(override\)/)).toBeInTheDocument();
  });

  it("model seçimi eğitimi ve tahmini o türe yönlendirir", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: { n_samples: 200, has_holdout: true, metrics: { test: { max_displacement: { r2: 0.895, mae: 0.59, mape: 0.189 } } } },
      scalar_hybrid: {
        n_samples: 200,
        has_holdout: true,
        metrics: { test: { max_displacement: { r2: 1.0, mae: 0.004, mape: 0.0016 } } },
        exponents: {
          max_displacement: [
            { feature: "length", exponent: 2.9894, identifiable: true, reason: null },
            {
              feature: "youngs_modulus",
              exponent: -0.0023,
              identifiable: false,
              reason: "korpus boyunca sabit",
            },
          ],
        },
        constant_features: ["youngs_modulus"],
        collinear_features: [],
      },
      scalar_loglinear: null,
      templates: { cantilever_beam: ["hybrid", "rf"] },
      field_gnn: null,
    });
    vi.mocked(trainScalarRf).mockResolvedValue({ n_samples: 200, has_holdout: true });

    render(<SurrogatePanel />);

    // Varsayılan log-log: üsler görünür, sabit sütun okunamaz diye işaretli.
    expect(await screen.findByText(/Öğrenilen üsler/)).toBeInTheDocument();
    expect(screen.getByText("2.9894")).toBeInTheDocument();
    expect(screen.getByText("korpus boyunca sabit")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Hibrit .* eğit/ }));
    await waitFor(() => expect(trainScalarRf).toHaveBeenCalledWith(null, "hybrid"));

    // RF'e geçilince üs tablosu kalkar ve eğitim o türe gider.
    fireEvent.change(screen.getByLabelText("Skaler model"), { target: { value: "rf" } });
    expect(screen.queryByText(/Öğrenilen üsler/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Random Forest eğit" }));
    await waitFor(() => expect(trainScalarRf).toHaveBeenCalledWith(null, "rf"));
  });
});

const PLATE = {
  id: "plate_with_hole",
  name: "Delikli plaka",
  description: "",
  tags: [],
  params_schema: {
    properties: {
      height: { type: "number", default: 200, unit: "mm", title: "Yükseklik", symbol: "H" },
      width: { type: "number", default: 100, unit: "mm", title: "Genişlik", symbol: "W" },
      thickness: { type: "number", default: 5, unit: "mm", title: "Kalınlık", symbol: "T" },
      diameter: { type: "number", default: 20, unit: "mm", title: "Delik çapı", symbol: "d" },
    },
  },
  regions: [],
  has_analytic: true,
  has_characteristic_length: true,
  default_bcs: [],
};

describe("SurrogatePanel — şablona göre tahmin", () => {
  beforeEach(() => {
    vi.mocked(fetchSurrogateStatus).mockReset();
    vi.mocked(fetchCorpusList).mockReset();
    vi.mocked(predictFromParams).mockReset();
    vi.mocked(fetchCorpusList).mockResolvedValue([]);
    vi.mocked(fetchTemplates).mockResolvedValue([CANTILEVER, PLATE] as never);
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null,
      scalar_loglinear: null,
      scalar_hybrid: { n_samples: 198, has_holdout: true },
      templates: { plate_with_hole: ["hybrid"], cantilever_beam: ["hybrid"] },
      field_gnn: null,
    });
  });

  it("şablon değişince form o şablonun alanlarını gösterir ve durum ona göre okunur", async () => {
    render(<SurrogatePanel />);
    await screen.findByLabelText(/L · Uzunluk/);
    await waitFor(() =>
      expect(fetchSurrogateStatus).toHaveBeenCalledWith("cantilever_beam"),
    );

    fireEvent.change(screen.getByLabelText("Şablon"), {
      target: { value: "plate_with_hole" },
    });

    expect(await screen.findByLabelText(/d · Delik çapı/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/L · Uzunluk/)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(fetchSurrogateStatus).toHaveBeenCalledWith("plate_with_hole"),
    );
  });

  it("delik çapı tahmin isteğinde params içinde gider", async () => {
    vi.mocked(predictFromParams).mockResolvedValue({
      kind: "scalar",
      template_id: "plate_with_hole",
      model_kind: "hybrid",
      source: "surrogate",
      out_of_domain: false,
      predictions: { max_displacement: 0.06, max_von_mises: 188 },
      features: {},
      fea: null,
      deviation_pct: null,
      message: "Tahmin",
    });
    render(<SurrogatePanel />);
    fireEvent.change(await screen.findByLabelText("Şablon"), {
      target: { value: "plate_with_hole" },
    });
    fireEvent.change(await screen.findByLabelText(/d · Delik çapı/), {
      target: { value: "24" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Parametreyle tahmin" }));

    await waitFor(() => expect(predictFromParams).toHaveBeenCalledTimes(1));
    const [body, kind] = vi.mocked(predictFromParams).mock.calls[0];
    expect(body.template_id).toBe("plate_with_hole");
    expect(body.params).toEqual({ height: 200, width: 100, thickness: 5, diameter: 24 });
    expect(kind).toBe("hybrid");
  });

  it("seçili tür o şablonda yoksa mevcut türe geçer", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: { n_samples: 12, has_holdout: true },
      scalar_loglinear: null,
      scalar_hybrid: null,
      templates: { cantilever_beam: ["rf"] },
      field_gnn: null,
    });
    render(<SurrogatePanel />);
    const select = (await screen.findByLabelText("Skaler model")) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("rf"));
    expect(screen.getByRole("button", { name: "Parametreyle tahmin" })).toBeEnabled();
  });
});
