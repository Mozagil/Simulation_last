import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SurrogatePanel from "./SurrogatePanel";

vi.mock("../api/surrogate", () => ({
  SurrogateApiError: class SurrogateApiError extends Error {},
  fetchSurrogateStatus: vi.fn(),
  trainScalarRf: vi.fn(),
  trainFieldGnn: vi.fn(),
  predictSurrogate: vi.fn(),
}));

import { fetchSurrogateStatus, predictSurrogate, trainScalarRf } from "../api/surrogate";

describe("SurrogatePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchSurrogateStatus).mockReset();
    vi.mocked(trainScalarRf).mockReset();
    vi.mocked(predictSurrogate).mockReset();
    vi.mocked(fetchSurrogateStatus).mockResolvedValue({
      scalar_rf: null,
      field_gnn: null,
    });
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
    fireEvent.click(screen.getByRole("button", { name: "Hızlı tahmin" }));
    await waitFor(() => expect(predictSurrogate).toHaveBeenCalledTimes(1));
    expect(predictSurrogate).toHaveBeenCalledWith({ runId: 4, geometryId: 1 });
    await waitFor(() => expect(onPrediction).toHaveBeenCalledTimes(1));
  });
});
