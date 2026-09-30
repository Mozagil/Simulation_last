import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  predictSweep: vi.fn(),
  fetchValidation: vi.fn(),
  fetchCorpusMembership: vi.fn(),
  fetchSurrogateBounds: vi.fn(),
}));

import {
  addRunsToCorpus,
  evaluateForCorpus,
  fetchCorpusList,
  fetchSurrogateStatus,
  freezeCorpus,
  predictFromParams,
  predictSurrogate,
  predictSweep,
  fetchValidation,
  fetchCorpusMembership,
  fetchSurrogateBounds,
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
    vi.mocked(fetchSurrogateBounds).mockReset();
    vi.mocked(fetchSurrogateBounds).mockResolvedValue(null);
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

  it("view=predict yalnız 2·Tahmin'i, view=model yalnız 1·Model + 3·Eğitim'i gösterir", async () => {
    const { unmount } = render(<SurrogatePanel view="predict" />);
    expect(await screen.findByTestId("predict-stage")).toBeInTheDocument();
    expect(screen.getByTestId("sweep-section")).toBeInTheDocument();
    expect(screen.queryByTestId("model-stage")).toBeNull();
    expect(screen.queryByTestId("gnn-prototype-note")).toBeNull();
    unmount();
    render(<SurrogatePanel view="model" />);
    expect(await screen.findByTestId("model-stage")).toBeInTheDocument();
    expect(screen.getByTestId("gnn-prototype-note")).toBeInTheDocument();
    expect(screen.queryByTestId("predict-stage")).toBeNull();
    expect(screen.queryByTestId("sweep-section")).toBeNull();
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
    fireEvent.click(await screen.findByRole("button", { name: "Tahmin et" }));
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
      false,
    );
    expect(await screen.findByText("Maks deplasman")).toBeInTheDocument();
    expect(screen.getByText("24.100")).toBeInTheDocument();
    expect(screen.getByText(/FEA u_max \(run 4\)/)).toBeInTheDocument();
    expect(screen.getByTestId("fea-compare")).toHaveTextContent("23.900 mm");
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
      expect(trainScalarRf).toHaveBeenCalledWith("kiris-v1", "hybrid", "cantilever_beam", false),
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

    fireEvent.click(
      within(await screen.findByRole("group", { name: "Kullanılan set" })).getByRole("button", { name: /kiris-v1/ }),
    );
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
    await waitFor(() =>
      expect(trainScalarRf).toHaveBeenCalledWith(null, "hybrid", "cantilever_beam", false),
    );

    // RF'e geçilince üs tablosu kalkar ve eğitim o türe gider.
    fireEvent.click(within(screen.getByTestId("model-card-rf")).getByRole("button", { name: "Aktif yap" }));
    expect(screen.queryByText(/Öğrenilen üsler/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Random Forest eğit" }));
    await waitFor(() =>
      expect(trainScalarRf).toHaveBeenCalledWith(null, "rf", "cantilever_beam", false),
    );
  });

  it("NLGEOM anahtarı durum, eğitim ve tahmini o modele yönlendirir (TODO 4)", async () => {
    vi.mocked(trainScalarRf).mockResolvedValue({ n_samples: 12, metrics: {} });
    render(<SurrogatePanel geometryId={1} runId={4} />);
    await screen.findByRole("button", { name: /Hibrit .* eğit/ });
    fireEvent.click(screen.getByLabelText("NLGEOM"));
    await waitFor(() =>
      expect(fetchSurrogateStatus).toHaveBeenLastCalledWith("cantilever_beam", true),
    );
    fireEvent.click(screen.getByRole("button", { name: /Hibrit .* eğit/ }));
    await waitFor(() =>
      expect(trainScalarRf).toHaveBeenCalledWith(null, "hybrid", "cantilever_beam", true),
    );
  });

  it("NLGEOM modeli yokken not gösterir ve tahmin butonu kapalı", async () => {
    render(<SurrogatePanel geometryId={1} runId={4} />);
    await screen.findByRole("button", { name: /Hibrit .* eğit/ });
    fireEvent.click(screen.getByLabelText("NLGEOM"));
    expect(await screen.findByTestId("nlgeom-model-missing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tahmin et" })).toBeDisabled();
  });

  it("toplu tarama parametre/aralık ile ister ve tabloyu gösterir", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null, scalar_loglinear: null,
      scalar_hybrid: { n_samples: 192, has_holdout: true, metrics: { test: { max_displacement: { r2: 0.99, mae: 0.1, mape: 0.002 } } } },
      templates: {}, field_gnn: null,
    });
    vi.mocked(predictSweep).mockResolvedValue({
      kind: "sweep", template_id: "cantilever_beam", sweep_param: "thickness", nlgeom: false,
      model_kind: "hybrid", n: 3, n_out_of_domain: 1,
      points: [
        { value: 8, max_displacement: 40.1, max_von_mises: 300, max_von_mises_away: 290, out_of_domain: true, violations: ["thickness", "load_fy"], exceeds_yield: null, sigma_mpa: null },
        { value: 10, max_displacement: 24.0, max_von_mises: 210, max_von_mises_away: 200, out_of_domain: false, violations: [], exceeds_yield: null, sigma_mpa: null },
        { value: 12, max_displacement: 14.0, max_von_mises: 150, max_von_mises_away: 145, out_of_domain: false, violations: [], exceeds_yield: null, sigma_mpa: null },
      ],
    });
    render(<SurrogatePanel geometryId={1} runId={4} />);
    await screen.findByRole("button", { name: "Tahmin et" });
    fireEvent.change(screen.getByLabelText("Parametre"), { target: { value: "thickness" } });
    fireEvent.change(screen.getByLabelText("Min"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Max"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Adım sayısı (2–200)"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Tara" }));
    await waitFor(() => expect(predictSweep).toHaveBeenCalledTimes(1));
    expect(predictSweep).toHaveBeenCalledWith(
      expect.objectContaining({ template_id: "cantilever_beam", sweep_param: "thickness", sweep_min: 8, sweep_max: 12, sweep_n: 3 }),
      "hybrid",
      false,
    );
    const table = await screen.findByTestId("sweep-result");
    expect(table).toHaveTextContent("uzay dışı: T, Fy");
    // Sabit tutulan girdiler açıkça yazılır; taranan (T) listede yoktur.
    const fixed = screen.getByTestId("sweep-fixed-inputs");
    expect(fixed).toHaveTextContent("L=500");
    expect(fixed).toHaveTextContent("Fy=-500");
    expect(fixed).not.toHaveTextContent("T=10");
    expect(table).toHaveTextContent("24.000");
  });

  it("tahmin vs FEA tablosu son N run ve ad süzgeciyle ister", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null, scalar_loglinear: null,
      scalar_hybrid: { n_samples: 192, has_holdout: true, metrics: { test: { max_displacement: { r2: 0.99, mae: 0.1, mape: 0.002 } } } },
      templates: {}, field_gnn: null,
    });
    vi.mocked(fetchValidation).mockResolvedValue({
      template_id: "cantilever_beam", model_kind: "hybrid", nlgeom: false, n: 2, skipped: {},
      mean_abs_dev_u_pct: 0.2, mean_abs_dev_vm_pct: 0.6, max_abs_dev_u_pct: 0.3,
      rows: [
        { run_id: 1457, name: "OOD deneme A", params: { length: 900, thickness: 12, width: 50 }, load_fy: -150,
          fea_u: 24.259, pred_u: 24.224, dev_u_pct: -0.14, fea_vm: 110.3, pred_vm: 110.9, vm_key: "max_von_mises_away",
          dev_vm_pct: 0.54, out_of_domain: true, violations: ["length"], u_over_l: 0.027, nlgeom: false },
        { run_id: 1458, name: "OOD deneme B", params: { length: 500, thickness: 10, width: 50 }, load_fy: -1500,
          fea_u: 71.759, pred_u: 71.972, dev_u_pct: 0.3, fea_vm: 879.9, pred_vm: 874.9, vm_key: "max_von_mises_away",
          dev_vm_pct: -0.57, out_of_domain: true, violations: ["thickness", "load_fy"], u_over_l: 0.144, nlgeom: false },
      ],
    });
    render(<SurrogatePanel geometryId={1} runId={4} />);
    await screen.findByRole("button", { name: "Tahmin et" });
    // Model hazır olunca doğrulama kendiliğinden gelir (korpus yok → son N run).
    await waitFor(() =>
      expect(fetchValidation).toHaveBeenLastCalledWith(
        expect.objectContaining({ templateId: "cantilever_beam", model: "hybrid", nlgeom: false, limit: 10, runIds: null }),
      ),
    );
    const before = vi.mocked(fetchValidation).mock.calls.length;
    fireEvent.change(screen.getByLabelText("Ad içerir (isteğe bağlı)"), { target: { value: "OOD deneme" } });
    fireEvent.click(screen.getByRole("button", { name: "Tabloyu oluştur" }));
    await waitFor(() => expect(fetchValidation).toHaveBeenCalledTimes(before + 1));
    expect(fetchValidation).toHaveBeenLastCalledWith(
      expect.objectContaining({ templateId: "cantilever_beam", model: "hybrid", nlgeom: false, limit: 10, nameContains: "OOD deneme" }),
    );
    const table = await screen.findByTestId("validate-result");
    expect(table).toHaveTextContent("1457 · OOD deneme A");
    expect(table).toHaveTextContent("uzay dışı: L");
    expect(table).toHaveTextContent("uzay dışı: T, Fy · u/L 0.14");
    expect(table).toHaveTextContent("%0.20");
  });

  it("doğrulama seçili korpusun run'larıyla sınırlanır; anahtar kapanınca son N run", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null, scalar_loglinear: null,
      scalar_hybrid: { n_samples: 184, has_holdout: true, metrics: {} },
      templates: {}, field_gnn: null,
    });
    vi.mocked(fetchCorpusList).mockResolvedValue([
      { name: "kiris_v3", frozen_at: null, n_runs: 3, template_id: "cantilever_beam", n_manual: 1 },
    ]);
    vi.mocked(fetchCorpusMembership).mockResolvedValue({
      name: "kiris_v3", frozen_at: null, auto: [11, 12], manual_pass: [13], manual_override: [],
    });
    vi.mocked(fetchValidation).mockResolvedValue({
      template_id: "cantilever_beam", model_kind: "hybrid", nlgeom: false, n: 3, skipped: {},
      mean_abs_dev_u_pct: 0.1, mean_abs_dev_vm_pct: 0.2, max_abs_dev_u_pct: 0.3, rows: [],
    });
    render(<SurrogatePanel view="model" />);
    await waitFor(() =>
      expect(fetchValidation).toHaveBeenLastCalledWith(expect.objectContaining({ runIds: [11, 12, 13], limit: 3 })),
    );
    expect(fetchCorpusMembership).toHaveBeenCalledWith("kiris_v3");
    expect(await screen.findByText(/3 çözülmüş run · kiris_v3/)).toBeInTheDocument();
    expect(screen.getByLabelText("Son N run")).toBeDisabled();

    fireEvent.click(screen.getByLabelText("yalnız kiris_v3"));
    await waitFor(() =>
      expect(fetchValidation).toHaveBeenLastCalledWith(expect.objectContaining({ runIds: null, limit: 10 })),
    );
    expect(screen.getByLabelText("Son N run")).toBeEnabled();
  });

  it("eğitim kutusu bantları tahminden önce gelir; kutu dışı girdi hemen işaretlenir", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null, scalar_loglinear: null,
      scalar_hybrid: { n_samples: 192, has_holdout: true, metrics: {} },
      templates: {}, field_gnn: null,
    });
    vi.mocked(fetchSurrogateBounds).mockResolvedValue({
      template_id: "cantilever_beam", model_kind: "hybrid", nlgeom: false, n_samples: 192,
      features: [
        { feature: "length", min: 401.2, max: 699.2 },
        { feature: "thickness", min: 10.01, max: 16 },
        { feature: "load_fy", min: -219.2, max: -40.5 },
      ],
    });
    render(<SurrogatePanel view="predict" />);
    await waitFor(() => expect(fetchSurrogateBounds).toHaveBeenCalledWith("cantilever_beam", "hybrid", false));
    // L=500 kutuda; Fy=-500 kutunun altında → tahmin yapılmadan işaretli
    expect(await screen.findByTestId("band-length")).toHaveTextContent("eğitim 401.2 – 699.2");
    expect(screen.getByTestId("band-length")).not.toHaveClass("sg-ood-text");
    expect(screen.getByTestId("band-load_fy")).toHaveTextContent("eğitim -219.2 – -40.5");
    expect(screen.getByTestId("band-load_fy")).toHaveClass("sg-ood-text");
    expect(screen.getByTestId("band-width")).toHaveTextContent("eğitim kutusu bilinmiyor");
    fireEvent.change(screen.getByLabelText("Fy (N)"), { target: { value: "-100" } });
    expect(screen.getByTestId("band-load_fy")).not.toHaveClass("sg-ood-text");
  });

  it("GNN prototip olarak işaretli ve holdout u_max hatasını gösterir (TODO 1.3b)", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null,
      scalar_loglinear: null,
      scalar_hybrid: null,
      templates: {},
      field_gnn: {
        n_samples: 88,
        metrics: { holdout: { scalar_rmse: { max_displacement: 1.791 } }, engine: "torch" },
      },
    });
    render(<SurrogatePanel geometryId={1} runId={4} />);
    expect(await screen.findByRole("button", { name: "GNN eğit (prototip)" })).toBeInTheDocument();
    const note = screen.getByTestId("gnn-prototype-note");
    expect(note).toHaveTextContent(/prototip — sonuçlar geçersiz/);
    await waitFor(() => expect(note).toHaveTextContent(/holdout u_max RMSE: 1\.79/));
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
      expect(fetchSurrogateStatus).toHaveBeenCalledWith("cantilever_beam", false),
    );

    fireEvent.change(screen.getByLabelText("Şablon"), {
      target: { value: "plate_with_hole" },
    });

    expect(await screen.findByLabelText(/d · Delik çapı/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/L · Uzunluk/)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(fetchSurrogateStatus).toHaveBeenCalledWith("plate_with_hole", false),
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
    fireEvent.click(screen.getByRole("button", { name: "Tahmin et" }));

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
    const card = await screen.findByTestId("model-card-rf");
    await waitFor(() => expect(within(card).getByRole("button", { name: "Aktif" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Tahmin et" })).toBeEnabled();
  });
});
