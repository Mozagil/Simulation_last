import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/composite";
import CompositeResultsPanel, { elementValues, plyRows, valueRange } from "./CompositeResultsPanel";

const SET: api.CompositePlySet = {
  element_ids: [11, 12],
  plies: [
    { material: "T300", angle_deg: 0 },
    { material: "T300", angle_deg: 90 },
  ],
  s11: [
    [100, -5],
    [-300, 4],
  ],
  s22: [
    [1, 20],
    [2, 22],
  ],
  s12: [
    [3, 3],
    [4, 4],
  ],
  tsai_wu_irf: [
    [0.05, 0.4],
    [0.2, 0.45],
  ],
  hashin_irf: [
    [0.06, 0.38],
    [0.25, 0.44],
  ],
  hashin_mode: [
    [0, 2],
    [1, 2],
  ],
  nodes: [
    [0, 0, 0],
    [1, 0, 0],
    [1, 1, 0],
    [0, 1, 0],
    [2, 0, 0],
  ],
  faces: [
    [0, 1, 2, 3],
    [1, 4, 2],
  ],
};

const FIELD: api.CompositePlyField = {
  run_id: 7,
  name: "plaka",
  scalars: {
    tsai_wu_irf_max: 0.45,
    tsai_wu_element: 12,
    tsai_wu_ply: 2,
    hashin_irf_max: 0.44,
    hashin_element: 12,
    hashin_ply: 2,
    hashin_mode: 2,
    hashin_mc_s23: 1,
  },
  f12_star: -0.5,
  hashin_modes: ["fiber_tension", "fiber_compression", "matrix_tension", "matrix_compression"],
  sets: { PART_0: SET },
};

const RUN = {
  id: 7,
  job_id: "j",
  geometry_id: 1,
  part_id: 0,
  name: "plaka",
  dimension: 2,
  status: "solved",
  message: null,
  solver_ran: true,
  inp_url: null,
  scalars: {},
  has_ply_field: true,
};

describe("CompositeResultsPanel (3.13)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("eleman değerleri: katman, IRF zarfı en büyük, gerilme zarfı işaretli en büyük |σ|", () => {
    expect(elementValues(SET, "tsai_wu", 0)).toEqual([0.05, 0.2]);
    expect(elementValues(SET, "tsai_wu", "env")).toEqual([0.4, 0.45]);
    expect(elementValues(SET, "s11", "env")).toEqual([100, -300]);
    expect(elementValues({ ...SET, tsai_wu_irf: [[null, null], [null, null]] }, "tsai_wu", "env")).toEqual([null, null]);
  });

  it("katman satırları en büyük IRF ve Hashin kipini taşır; IRF ölçeği 0'dan başlar", () => {
    const rows = plyRows(SET);
    expect(rows[0]).toMatchObject({ angle: 0, twMax: 0.2, hsMax: 0.25, hsMode: 1 });
    expect(rows[1]).toMatchObject({ angle: 90, twMax: 0.45, hsMax: 0.44, hsMode: 2 });
    expect(valueRange([0.2, 0.45], true)).toEqual([0, 0.45]);
    expect(valueRange([100, -300], false)).toEqual([-300, 100]);
  });

  it("koşuyu yükler; özet, katman seçici ve büyüklük değiştirir", async () => {
    vi.spyOn(api, "fetchCompositeRuns").mockResolvedValue([RUN, { ...RUN, id: 8, has_ply_field: false }]);
    vi.spyOn(api, "fetchCompositePlyField").mockResolvedValue(FIELD);
    render(<CompositeResultsPanel geometryId={1} />);
    await waitFor(() => expect(screen.getByTestId("composite-kpis")).toBeInTheDocument());
    expect(api.fetchCompositePlyField).toHaveBeenCalledWith(7);
    expect(screen.getAllByRole("option", { name: /#/ })).toHaveLength(1); // yalnız alanı olan koşu
    expect(screen.getByText(/RF en küçük 2.22 · eleman 12 · katman 2/)).toBeInTheDocument();
    expect(screen.getByText(/matris çekme · eleman 12/)).toBeInTheDocument();
    const caption = screen.getByTestId("composite-view-caption");
    expect(caption).toHaveTextContent("Tsai-Wu IRF · zarf · min 0.400 · maks 0.450 · RF 2.22");

    fireEvent.click(screen.getByRole("option", { name: /^1\s*0°/ }));
    expect(caption).toHaveTextContent("katman 1 (0°) · min 0.050 · maks 0.200");
    fireEvent.click(screen.getByRole("tab", { name: "σ11" }));
    expect(caption).toHaveTextContent("σ11 (MPa) · katman 1 (0°) · min -300.0 · maks 100.0");
    expect(caption).not.toHaveTextContent("RF");
  });

  it("çözülmüş koşu yoksa mesaj", async () => {
    vi.spyOn(api, "fetchCompositeRuns").mockResolvedValue([{ ...RUN, has_ply_field: false }]);
    render(<CompositeResultsPanel geometryId={1} />);
    await waitFor(() => expect(screen.getByTestId("composite-results-empty")).toBeInTheDocument());
  });
});
