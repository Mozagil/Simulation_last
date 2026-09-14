import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DoePanel from "./DoePanel";

vi.mock("../api/doe", () => ({
  DoeApiError: class DoeApiError extends Error {},
  fetchDoeStudies: vi.fn(),
  createDoeStudy: vi.fn(),
  startQualitySet: vi.fn(),
  fetchDoeQuality: vi.fn(),
}));

vi.mock("../api/materials", () => ({
  fetchMaterials: vi.fn(),
}));

import { createDoeStudy, fetchDoeQuality, fetchDoeStudies, startQualitySet } from "../api/doe";
import { fetchMaterials } from "../api/materials";

describe("DoePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchDoeStudies).mockReset();
    vi.mocked(createDoeStudy).mockReset();
    vi.mocked(startQualitySet).mockReset();
    vi.mocked(fetchDoeQuality).mockReset();
    vi.mocked(fetchMaterials).mockReset();
    vi.mocked(fetchDoeStudies).mockResolvedValue([]);
    vi.mocked(fetchDoeQuality).mockResolvedValue({
      study_id: 1,
      n_cases: 8,
      n_ok: 0,
      counts: { inp_only: 8 },
      flagged: { inp_only: [0, 1, 2, 3, 4, 5, 6, 7] },
    });
    vi.mocked(fetchMaterials).mockResolvedValue([{ id: 3, name: "S235" } as never]);
    vi.mocked(createDoeStudy).mockResolvedValue({
      id: 1,
      name: "cantilever LHS",
      template_id: "cantilever_beam",
      seed: 42,
      status: "completed",
      message: "8/8 başarılı",
      n_cases: 8,
      counts: { inp_only: 8 },
      cases: [],
    });
  });

  it("tohum ve örnek sayısıyla DOE başlatır", async () => {
    render(<DoePanel />);
    expect(await screen.findByRole("button", { name: "DOE başlat" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "DOE başlat" }));
    await waitFor(() => expect(createDoeStudy).toHaveBeenCalledTimes(1));
    const [spec, wait] = vi.mocked(createDoeStudy).mock.calls[0];
    expect(wait).toBe(true);
    expect(spec.template_id).toBe("cantilever_beam");
    expect(spec.n_samples).toBe(8);
    expect(spec.seed).toBe(42);
    expect(spec.material_ids).toEqual([3]);
    expect(spec.bc_scenarios).toHaveLength(2);
  });

  it("200'lük kalite setini arka planda başlatır", async () => {
    vi.mocked(startQualitySet).mockResolvedValue({
      id: 9,
      name: "kalite-200 cantilever",
      template_id: "cantilever_beam",
      seed: 2026,
      status: "pending",
      message: null,
      n_cases: 200,
      counts: { pending: 200 },
      cases: [],
    });
    render(<DoePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "200'lük kalite seti" }));
    await waitFor(() => expect(startQualitySet).toHaveBeenCalledTimes(1));
    expect(startQualitySet).toHaveBeenCalledWith({
      material_ids: [3],
      run_solver: false,
      wait: false,
    });
  });
});
