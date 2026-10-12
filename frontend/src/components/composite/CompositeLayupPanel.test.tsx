import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CompositeLayupPanel from "./CompositeLayupPanel";

vi.mock("../../api/composite", () => ({
  fetchCompositeMaterials: vi.fn(),
  fetchCompositeLayups: vi.fn(),
  putCompositeLayup: vi.fn(),
  computeClt: vi.fn(),
  createCompositeMaterial: vi.fn(),
}));

import {
  computeClt,
  fetchCompositeLayups,
  fetchCompositeMaterials,
  putCompositeLayup,
} from "../../api/composite";

const T300 = {
  id: 1,
  name: "T300/epoxy",
  ply_kind: "ud",
  category: "cfrp",
  standard: "typical handbook",
  density: 1600,
  e1: 135e9,
  e2: 10e9,
  e3: 10e9,
  nu12: 0.3,
  nu13: 0.3,
  nu23: 0.45,
  g12: 5.2e9,
  g13: 5.2e9,
  g23: 3.4e9,
  xt: 1500e6,
  xc: 1200e6,
  yt: 50e6,
  yc: 200e6,
  s12: 70e6,
  s13: 70e6,
  s23: 40e6,
  source: "library",
  is_editable: false,
};

const ABD = {
  n_plies: 3,
  h_mm: 0.375,
  A_N_per_mm: [
    [35110.12, 375.04, 0],
    [375.04, 19634.08, 0],
    [0, 0, 1950.0],
  ],
  B_N: [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ],
  D_N_mm: [
    [410.5, 4.88, 0],
    [4.88, 122.4, 0],
    [0, 0, 25.39],
  ],
};

const SAVED = {
  id: 4,
  geometry_id: 7,
  part_id: 0,
  n_plies: 3,
  plies: [
    { material_id: 1, material_name: "T300/epoxy", thickness_mm: 0.125, angle_deg: 0 },
    { material_id: 1, material_name: "T300/epoxy", thickness_mm: 0.125, angle_deg: 90 },
    { material_id: 1, material_name: "T300/epoxy", thickness_mm: 0.125, angle_deg: 0 },
  ],
};

describe("CompositeLayupPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchCompositeMaterials).mockReset();
    vi.mocked(fetchCompositeLayups).mockReset();
    vi.mocked(putCompositeLayup).mockReset();
    vi.mocked(computeClt).mockReset();
    vi.mocked(fetchCompositeMaterials).mockResolvedValue([T300]);
    vi.mocked(fetchCompositeLayups).mockResolvedValue([SAVED]);
    vi.mocked(putCompositeLayup).mockResolvedValue(SAVED);
    vi.mocked(computeClt).mockResolvedValue(ABD);
  });

  it("geometri yokken kaydetmez", () => {
    render(<CompositeLayupPanel geometryId={null} partIds={[0]} selectedPartId={null} />);
    expect(screen.getByText(/Geometri yükle/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kaydet" })).toBeNull();
  });

  it("kayıtlı [0/90/0] yükler, CLT canlı gelir, Kaydet PUT eder", async () => {
    const user = userEvent.setup();
    render(<CompositeLayupPanel geometryId={7} partIds={[0]} selectedPartId={0} />);
    expect(await screen.findByLabelText("Katman 1 açı")).toHaveValue("0");
    expect(screen.getByLabelText("Katman 2 açı")).toHaveValue("90");
    expect(screen.getByLabelText("Katman 3 açı")).toHaveValue("0");
    await waitFor(() => {
      expect(computeClt).toHaveBeenCalled();
    });
    expect(await screen.findByTestId("composite-abd")).toBeInTheDocument();
    expect(screen.getByText("35110.12")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => {
      expect(putCompositeLayup).toHaveBeenCalledTimes(1);
    });
    const sent = vi.mocked(putCompositeLayup).mock.calls[0][0];
    expect(sent.geometry_id).toBe(7);
    expect(sent.part_id).toBe(0);
    expect(sent.plies.map((p) => p.angle_deg)).toEqual([0, 90, 0]);
  });

  it("aşağı taşı sıra değiştirir", async () => {
    const user = userEvent.setup();
    render(<CompositeLayupPanel geometryId={7} partIds={[0]} selectedPartId={0} />);
    await screen.findByLabelText("Katman 1 açı");
    await user.click(screen.getByRole("button", { name: "Katman 1 aşağı" }));
    expect(screen.getByLabelText("Katman 1 açı")).toHaveValue("90");
    expect(screen.getByLabelText("Katman 2 açı")).toHaveValue("0");
  });
});
