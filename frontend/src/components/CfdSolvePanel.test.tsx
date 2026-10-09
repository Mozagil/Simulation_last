import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CfdSolvePanel from "./CfdSolvePanel";
import { fetchCfdJob, postCfdSolve, type CfdJobSnapshot, type CfdMeshMeta } from "../api/cfd";

vi.mock("../api/cfd", async (orig) => {
  const mod = await orig<typeof import("../api/cfd")>();
  return { ...mod, postCfdSolve: vi.fn(), fetchCfdJob: vi.fn() };
});

const mesh: CfdMeshMeta = {
  mesh_id: "m1",
  geometry_id: 7,
  mesher: "snappy",
  status: "meshed",
  message: "mesh hazır",
  patches: ["inlet", "outlet", "sides", "burun", "govde"],
  surface: { regions: [], triangles: 1, triangles_per_region: {}, open_edges: 0, bbox_m: [] },
  domain: { min_m: [], max_m: [], background_cells: [1, 1, 1], body_length_m: 1.5 },
  check: { cells: 56298, mesh_ok: true },
};

const solved: CfdJobSnapshot = {
  job_id: "j1",
  status: "solved",
  message: "simpleFoam bitti · 120 iterasyon · yakınsadı",
  curves: { iteration: [1, 2, 3], residuals: { p: [1, 0.1, 0.01], Ux: [1, 0.05, 0.002] } },
  scalars: { iterations: 120, converged: 1, Cd: 0.53, Cd_mean: 0.531, Cd_std: 0.002, Cl_mean: 0.01, CdA_m2: 0.0042, force_total_x: 6.4 },
};

describe("CfdSolvePanel (AKIŞ · 3 · Akış)", () => {
  beforeEach(() => {
    vi.mocked(postCfdSolve).mockReset().mockResolvedValue({ job_id: "j1", status: "pending", message: "kuyrukta", run_id: 3 });
    vi.mocked(fetchCfdJob).mockReset().mockResolvedValue(solved);
  });

  it("mesh yokken yalnız yönlendirme gösterir", () => {
    render(<CfdSolvePanel mesh={null} />);
    expect(screen.getByText(/Önce 2 · Mesh/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Çalıştır/ })).toBeNull();
  });

  it("yama rollerini mesh'ten varsayar, isteği kurar, residual grafiği ve özet gösterir", async () => {
    const onSolved = vi.fn();
    render(<CfdSolvePanel mesh={mesh} pollMs={1} onSolved={onSolved} />);
    expect(screen.getByLabelText("Yama sides")).toHaveValue("slip");
    expect(screen.getByLabelText("Yama burun")).toHaveValue("wall");
    fireEvent.change(screen.getByLabelText("Yama sides"), { target: { value: "farfield" } });
    fireEvent.click(screen.getByRole("button", { name: /Akışkan ve türbülans/ }));
    expect(screen.getByTestId("cfd-re")).toHaveTextContent("Re");
    fireEvent.click(screen.getByRole("button", { name: /Kuvvet ve katsayılar/ }));
    fireEvent.change(screen.getByLabelText("Referans alan A"), { target: { value: "0.00785" } });
    fireEvent.change(screen.getByLabelText("Referans uzunluk l"), { target: { value: "0.1" } });
    fireEvent.click(screen.getByLabelText("Kuvvet govde"));
    fireEvent.click(screen.getByRole("button", { name: /Çalıştır/ }));
    await waitFor(() => expect(onSolved).toHaveBeenCalledWith(solved));
    const body = vi.mocked(postCfdSolve).mock.calls[0][0];
    expect(body.mesh_id).toBe("m1");
    const sides = body.case.patches.find((p) => p.name === "sides");
    expect(sides).toEqual({ name: "sides", kind: "farfield", velocity_m_s: [10, 0, 0] });
    expect(body.case.patches.find((p) => p.name === "outlet")).toEqual({ name: "outlet", kind: "outlet", pressure: 0 });
    expect(body.case.forces?.patches).toEqual(["burun"]);
    expect(body.case.forces?.u_ref_m_s).toBeCloseTo(10);
    expect(screen.getByTestId("cfd-residual-chart")).toBeInTheDocument();
    expect(screen.getByTestId("cfd-solve-summary")).toHaveTextContent("0.5300");
  });

  it("kuvvet referansları boşsa kuvvet istenmez; hata mesajı gösterilir", async () => {
    vi.mocked(fetchCfdJob).mockResolvedValue({ job_id: "j1", status: "failed", message: "OpenFOAM simpleFoam hata: çıkış kodu 136" });
    render(<CfdSolvePanel mesh={mesh} pollMs={1} />);
    fireEvent.click(screen.getByRole("button", { name: /Çalıştır/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("çıkış kodu 136");
    expect(vi.mocked(postCfdSolve).mock.calls[0][0].case.forces).toBeNull();
  });
});
