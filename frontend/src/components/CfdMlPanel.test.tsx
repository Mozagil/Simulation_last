import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/cfdMl";
import CfdMlPanel from "./CfdMlPanel";

const MODEL: api.CfdModelInfo = {
  application: "simpleFoam",
  doe_id: null,
  n_runs: 10,
  feature_keys: ["flow.alpha_deg", "flow.mach"],
  constant_features: {},
  bounds: { "flow.alpha_deg": [0, 6], "flow.mach": [0.1, 0.3] },
  targets: [
    { key: "CD", label: "CD", unit: "-", trained: true, cv: { n: 10, r2: 0.91, mae: 0.004, mape: 0.012 } },
    { key: "x_cp_m", label: "x_cp", unit: "m", trained: false, cv: { n: 3, skipped: "en az 8 dolu satır gerekir" } },
  ],
};

describe("CfdMlPanel (2.9)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchCfdDoes").mockResolvedValue([]);
    vi.spyOn(api, "fetchCfdCorpus").mockResolvedValue({ application: "simpleFoam", doe_id: null, n_runs: 10, features: ["flow.mach"], constant_features: { "flow.x_ref_m": 0.9 }, targets: {}, dropped: {} });
    vi.spyOn(api, "fetchCfdModels").mockResolvedValue([]);
  });

  it("DOE isteğini seçili değişken aralıkları ve çözücüyle kurar, örnekleri gösterir", async () => {
    const post = vi.spyOn(api, "postCfdDoe").mockResolvedValue({ doe_id: "d1", status: "running", solver: "rhoSimpleFoam", samples: [] });
    vi.spyOn(api, "fetchCfdDoe").mockResolvedValue({
      doe_id: "d1", status: "done", solver: "rhoSimpleFoam", message: "1/1 örnek çözüldü",
      samples: [{ index: 0, template_params: { fin_span: 95 }, mach: 0.5, alpha_deg: 3, status: "solved", cells: 56000, aero: { CD: 0.41, CN: 0.8, x_cp_m: 1.18 } }],
    });
    render(<CfdMlPanel pollMs={1} />);
    fireEvent.click(screen.getByLabelText("Tara alpha_deg"));
    fireEvent.change(screen.getByLabelText("mach üst"), { target: { value: "0.6" } });
    fireEvent.click(screen.getAllByRole("button", { name: "rhoSimpleFoam" })[0]);
    fireEvent.click(screen.getByRole("button", { name: /DOE başlat \(10 örnek × 2 değişken\)/ }));
    await waitFor(() => expect(screen.getByTestId("cfd-doe-status")).toHaveTextContent("1/1"));
    const body = post.mock.calls[0][0];
    expect(body.ranges).toEqual({ mach: [0.1, 0.6], fin_span: [70, 130] });
    expect(body.alpha_deg).toBe(4);
    expect(body.solve).toMatchObject({ solver: "rhoSimpleFoam", iterations: 400 });
    expect(screen.getByTestId("cfd-doe-samples")).toHaveTextContent("fin_span 95");
  });

  it("eğitir, CV tablosu ve aralık dışı tahmin gösterir", async () => {
    vi.spyOn(api, "trainCfdModel").mockResolvedValue(MODEL);
    vi.spyOn(api, "predictCfd").mockResolvedValue({ prediction: { CD: 0.25, x_cp_m: null }, out_of_domain: ["flow.mach"] });
    render(<CfdMlPanel />);
    await waitFor(() => expect(screen.getByTestId("cfd-corpus")).toHaveTextContent("10 koşu"));
    fireEvent.click(screen.getByRole("button", { name: "Modeli eğit" }));
    await waitFor(() => expect(screen.getByTestId("cfd-model-cv")).toHaveTextContent("0.910"));
    expect(screen.getByTestId("cfd-model-cv")).toHaveTextContent("en az 8 dolu satır");
    fireEvent.change(screen.getByLabelText(/flow.mach \[/), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Tahmin et" }));
    await waitFor(() => expect(screen.getByTestId("cfd-ood")).toHaveTextContent("flow.mach"));
    expect(vi.mocked(api.predictCfd).mock.calls[0][0].inputs).toEqual({ "flow.alpha_deg": 3, "flow.mach": 0.5 });
  });
});
