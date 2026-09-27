import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DatasetPanel from "./DatasetPanel";

vi.mock("../api/dataset", () => ({
  DatasetError: class DatasetError extends Error {},
  fetchDatasetSummary: vi.fn(),
  downloadDataset: vi.fn(),
  importDataset: vi.fn(),
}));
vi.mock("../api/surrogate", () => ({ fetchCorpusList: vi.fn() }));

import { downloadDataset, fetchDatasetSummary } from "../api/dataset";
import { fetchCorpusList } from "../api/surrogate";

const SUMMARY = {
  geometries: 380,
  materials: 8,
  runs: { total: 300, solved: 240, unsolved: 60 },
  training_samples: 200,
  templates: [],
};

describe("DatasetPanel — korpusa göre arşiv", () => {
  beforeEach(() => {
    vi.mocked(fetchDatasetSummary).mockReset();
    vi.mocked(downloadDataset).mockReset();
    vi.mocked(fetchCorpusList).mockReset();
    vi.mocked(fetchDatasetSummary).mockResolvedValue(SUMMARY as never);
    vi.mocked(downloadDataset).mockResolvedValue(undefined as never);
    vi.mocked(fetchCorpusList).mockResolvedValue([
      { name: "kiris-v2", frozen_at: null, n_runs: 200, template_id: "cantilever_beam", n_manual: 8 },
      { name: "plaka-v1", frozen_at: null, n_runs: 198, template_id: "plate_with_hole", n_manual: 0 },
    ] as never);
  });

  it("eğitim seti seçilip indirilebilir", async () => {
    render(<DatasetPanel />);
    const btn = await screen.findByRole("button", { name: /Eğitim setini indir/ });
    // Varsayılan: listenin sonuncusu
    expect(btn).toHaveTextContent("plaka-v1");

    fireEvent.click(btn);
    await waitFor(() => expect(downloadDataset).toHaveBeenCalledTimes(1));
    expect(downloadDataset).toHaveBeenCalledWith(
      expect.objectContaining({ corpusName: "plaka-v1" }),
    );
    expect(
      await screen.findByText(/"plaka-v1" eğitim seti indirildi/),
    ).toBeInTheDocument();
  });

  it("başka set seçilince o set indirilir", async () => {
    render(<DatasetPanel />);
    fireEvent.change(await screen.findByLabelText("Eğitim seti"), {
      target: { value: "kiris-v2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Eğitim setini indir/ }));
    await waitFor(() =>
      expect(downloadDataset).toHaveBeenCalledWith(
        expect.objectContaining({ corpusName: "kiris-v2" }),
      ),
    );
  });

  it("tümünü indir korpus göndermez", async () => {
    render(<DatasetPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /Tümünü indir/ }));
    await waitFor(() => expect(downloadDataset).toHaveBeenCalledTimes(1));
    const arg = vi.mocked(downloadDataset).mock.calls[0][0];
    expect(arg?.corpusName).toBeUndefined();
  });

  it("donmuş set yoksa seçici gösterilmez", async () => {
    vi.mocked(fetchCorpusList).mockResolvedValue([] as never);
    render(<DatasetPanel />);
    await screen.findByRole("button", { name: /Tümünü indir/ });
    expect(screen.queryByLabelText("Eğitim seti")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Eğitim setini indir/ }),
    ).not.toBeInTheDocument();
  });
});
