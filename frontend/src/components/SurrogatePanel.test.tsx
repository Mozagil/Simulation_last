import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SurrogatePanel from "./SurrogatePanel";

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
      field_gnn: null,
    });
    vi.mocked(fetchCorpusList).mockResolvedValue([]);
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
    fireEvent.click(await screen.findByRole("button", { name: "RF eğit" }));
    await waitFor(() => expect(trainScalarRf).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Açık run tahmini" }));
    await waitFor(() => expect(predictSurrogate).toHaveBeenCalledTimes(1));
    expect(predictSurrogate).toHaveBeenCalledWith({ runId: 4, geometryId: 1 });
    await waitFor(() => expect(onPrediction).toHaveBeenCalledTimes(1));
  });

  it("parametreyle tahmin ccx/run istemez ve sayıları gösterir", async () => {
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: { n_samples: 22, metrics: { test: { max_displacement: { r2: -3.9, mae: 1, mape: 1 } } } },
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
    fireEvent.change(screen.getByLabelText("L (mm)"), { target: { value: "520" } });
    fireEvent.change(screen.getByLabelText("Fy (N)"), { target: { value: "-400" } });
    fireEvent.click(await screen.findByRole("button", { name: "Parametreyle tahmin" }));
    await waitFor(() => expect(predictFromParams).toHaveBeenCalledTimes(1));
    expect(predictFromParams).toHaveBeenCalledWith(
      expect.objectContaining({
        length: 520,
        load_fy: -400,
        compare_run_id: 4,
      }),
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

    fireEvent.click(screen.getByRole("button", { name: "RF eğit" }));
    await waitFor(() => expect(trainScalarRf).toHaveBeenCalledWith("kiris-v1"));
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
});
