import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/cfd";
import CfdFieldViewer, { range } from "./CfdFieldViewer";

describe("CfdFieldViewer", () => {
  afterEach(() => vi.restoreAllMocks());

  it("range verinin min–max'ı", () => {
    expect(range([3, -1, 2])).toEqual([-1, 3]);
    expect(range([])).toEqual([0, 1]);
  });

  it("katman aralıklarını ve sayıları gösterir", async () => {
    vi.spyOn(api, "fetchCfdFields").mockResolvedValue({
      u_ref_m_s: 40,
      p_ref: 0,
      compressible: false,
      body: { points: [[0, 0, 0], [1, 0, 0]], p: [800, -400], cp: [1, -0.5] },
      slice: { points: [[0, 0, 0]], speed: [38.5] },
      streamlines: [{ points: [[0, 0, 0], [1, 0, 0]], speed: [40, 42] }],
    });
    render(<CfdFieldViewer jobId="j1" />);
    await waitFor(() => expect(screen.getByTestId("cfd-fields")).toBeInTheDocument());
    expect(screen.getByText(/Cp \(gövde\): -0.500 … 1.00/)).toBeInTheDocument();
    expect(screen.getByText(/2 yüzey noktası · 1 kesit noktası · 1 akım çizgisi/)).toBeInTheDocument();
  });

  it("çıktı yoksa mesaj", async () => {
    vi.spyOn(api, "fetchCfdFields").mockRejectedValue(new Error("Bu koşuda alan görselleştirme çıktısı yok."));
    render(<CfdFieldViewer jobId="j2" />);
    await waitFor(() => expect(screen.getByTestId("cfd-fields-missing")).toHaveTextContent("çıktısı yok"));
  });
});
