import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CompositeCltPanel from "./CompositeCltPanel";

vi.mock("../../api/composite", () => ({
  fetchCompositeMaterials: vi.fn(),
  computeClt: vi.fn(),
  createCompositeMaterial: vi.fn(),
}));

import { computeClt, fetchCompositeMaterials } from "../../api/composite";

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

describe("CompositeCltPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchCompositeMaterials).mockReset();
    vi.mocked(computeClt).mockReset();
    vi.mocked(fetchCompositeMaterials).mockResolvedValue([T300]);
    vi.mocked(computeClt).mockResolvedValue(ABD);
  });

  it("[0/90/0] için ABD sayılarını gösterir", async () => {
    const user = userEvent.setup();
    render(<CompositeCltPanel />);
    expect(await screen.findByLabelText("Katman 1 açı")).toHaveValue("0");
    expect(screen.getByLabelText("Katman 2 açı")).toHaveValue("90");
    expect(screen.getByLabelText("Katman 3 açı")).toHaveValue("0");
    await user.click(screen.getByRole("button", { name: "ABD hesapla" }));
    await waitFor(() => {
      expect(computeClt).toHaveBeenCalledTimes(1);
    });
    const sent = vi.mocked(computeClt).mock.calls[0][0];
    expect(sent).toHaveLength(3);
    expect(sent.map((p) => p.angle_deg)).toEqual([0, 90, 0]);
    expect(sent[0].e1).toBe(135e9);
    expect(sent[0].thickness_mm).toBe(0.125);
    expect(await screen.findByTestId("composite-abd")).toBeInTheDocument();
    expect(screen.getByText("35110.12")).toBeInTheDocument();
    expect(screen.getByText("n = 3 · h = 0.375 mm")).toBeInTheDocument();
    expect(screen.getByText("A · N/mm")).toBeInTheDocument();
    expect(screen.getByText("B · N")).toBeInTheDocument();
    expect(screen.getByText("D · N·mm")).toBeInTheDocument();
  });
});
