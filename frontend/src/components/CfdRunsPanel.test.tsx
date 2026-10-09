import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CfdRunsPanel from "./CfdRunsPanel";
import { fetchCfdRuns, patchCfdRun, type CfdRunSummary } from "../api/cfd";

vi.mock("../api/cfd", async (orig) => {
  const mod = await orig<typeof import("../api/cfd")>();
  return { ...mod, fetchCfdRuns: vi.fn(), patchCfdRun: vi.fn() };
});

const run = (id: number, cd: number, extra: Partial<CfdRunSummary> = {}): CfdRunSummary => ({
  id,
  job_id: `j${id}`,
  geometry_id: 4,
  name: `koşu ${id}`,
  created_at: "2026-10-09T10:00:00Z",
  application: "simpleFoam",
  turbulence: "kOmegaSST",
  mesh_kind: "snappy",
  status: "solved",
  message: "",
  scalars: { iterations: 200, converged: 1, Cd_mean: cd },
  reference: null,
  excluded: false,
  ...extra,
});

describe("CfdRunsPanel (koşu geçmişi)", () => {
  beforeEach(() => {
    vi.mocked(fetchCfdRuns).mockReset().mockResolvedValue({
      count: 3,
      runs: [run(3, 0.53, { reference: { kind: "rocket_r3", aero: { CN: 1.1, x_cp_m: 1.2206 } } }), run(2, 0.41), run(1, 0.25)],
    });
    vi.mocked(patchCfdRun).mockReset().mockImplementation(async (id, body) => ({ ...run(id, 0), excluded: Boolean(body.excluded) }));
  });

  it("listeler, iki koşuyu yan yana karşılaştırır, dışlar", async () => {
    render(<CfdRunsPanel geometryId={4} />);
    await waitFor(() => expect(fetchCfdRuns).toHaveBeenCalledWith(4));
    fireEvent.click(screen.getByRole("button", { name: /Koşu geçmişi/ }));
    expect(screen.getByText("koşu 2")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Seç 3"));
    expect(screen.queryByTestId("cfd-runs-compare")).toBeNull(); // en az 2
    fireEvent.click(screen.getByLabelText("Seç 2"));
    const cmp = screen.getByTestId("cfd-runs-compare");
    expect(cmp).toHaveTextContent("Cd (ort.)");
    expect(cmp).toHaveTextContent("0.5300");
    expect(cmp).toHaveTextContent("1220.6"); // roket basınç merkezi (mm)
    fireEvent.click(screen.getAllByRole("button", { name: "dışla" })[2]);
    await waitFor(() => expect(patchCfdRun).toHaveBeenCalledWith(1, { excluded: true }));
    expect(await screen.findByRole("button", { name: "geri al" })).toBeInTheDocument();
  });

  it("'yalnız bu geometri' kapatılınca tüm koşular istenir", async () => {
    render(<CfdRunsPanel geometryId={4} />);
    fireEvent.click(screen.getByRole("button", { name: /Koşu geçmişi/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Yalnız bu geometri" }));
    await waitFor(() => expect(fetchCfdRuns).toHaveBeenLastCalledWith(null));
  });
});
