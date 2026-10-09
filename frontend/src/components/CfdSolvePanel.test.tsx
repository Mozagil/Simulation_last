import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CfdSolvePanel from "./CfdSolvePanel";
import { fetchCfdJob, postBarrowman, postCfdSolve, postRocketSolve, type CfdJobSnapshot, type CfdMeshMeta } from "../api/cfd";

vi.mock("../api/cfd", async (orig) => {
  const mod = await orig<typeof import("../api/cfd")>();
  return { ...mod, postCfdSolve: vi.fn(), fetchCfdJob: vi.fn(), postRocketSolve: vi.fn(), postBarrowman: vi.fn() };
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

  it("R4: çözücü elle seçilir; sıkıştırılabilir ayarlar ve çekirdek sayısı isteğe gider", async () => {
    render(<CfdSolvePanel mesh={mesh} pollMs={1} />);
    fireEvent.click(screen.getByRole("button", { name: /Çözücü ve çözüm ayarları/ }));
    expect(screen.queryByLabelText("Courant sınırı")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "rhoCentralFoam" }));
    expect(screen.getByTestId("cfd-solver-hint")).toHaveTextContent("şok yakalayan");
    fireEvent.change(screen.getByLabelText("Courant sınırı"), { target: { value: "0.3" } });
    fireEvent.change(screen.getByLabelText("Çekirdek sayısı"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: /Çalıştır \(rhoCentralFoam\)/ }));
    await waitFor(() => expect(postCfdSolve).toHaveBeenCalled());
    const c = vi.mocked(postCfdSolve).mock.calls[0][0].case;
    expect(c.solver).toBe("rhoCentralFoam");
    expect(c.compressible?.max_co).toBe(0.3);
    expect(c.control.n_procs).toBe(4);
  });
});

const BARROWMAN = {
  cn_alpha: 10.81,
  x_cp_mm: 1176.6,
  x_cp_calibers: 11.8,
  stability_calibers: 2.77,
  reference_diameter_mm: 100,
  components: [
    { name: "burun", cn_alpha: 2, x_mm: 138.7 },
    { name: "kanatcik", cn_alpha: 8.81, x_mm: 1412 },
  ],
  notes: [],
};

describe("CfdSolvePanel · roket rüzgâr tüneli modu (R3)", () => {
  const rocketMesh: CfdMeshMeta = { ...mesh, patches: ["inlet", "outlet", "sides", "burun", "govde", "kanatcik", "taban"] };
  const rocketJob: CfdJobSnapshot = {
    ...solved,
    scalars: { ...solved.scalars, force_burun_x: 0.3, force_burun_pressure_x: 0.05, force_burun_viscous_x: 0.25, force_burun_z: 0.1 },
    rocket_aero: {
      CA: 0.54, CN: 1.1, CD: 0.61, CL: 1.06, Cm: -3.5, x_cp_m: 1.2206, x_cp_calibers: 12.2, CN_alpha_per_rad: 15.8, stability_calibers: 3.2,
      barrowman: { cn_alpha_barrowman: 10.81, x_cp_barrowman_m: 1.1766, cn_alpha_diff_percent: 46.0, x_cp_diff_calibers: 0.44 },
    },
  };

  beforeEach(() => {
    vi.mocked(postRocketSolve).mockReset().mockResolvedValue({ job_id: "r1", status: "pending", message: "kuyrukta", mach: 0.147, barrowman: BARROWMAN });
    vi.mocked(postBarrowman).mockReset().mockResolvedValue(BARROWMAN);
    vi.mocked(postCfdSolve).mockClear();
    vi.mocked(fetchCfdJob).mockReset().mockResolvedValue(rocketJob);
  });

  it("roket yamalarında roket modu açılır; Barrowman ön izleme ve koşu → katsayılar + Barrowman yan yana", async () => {
    render(<CfdSolvePanel mesh={rocketMesh} geometryId={9} pollMs={1} />);
    expect(screen.getByRole("button", { name: "Roket rüzgâr tüneli" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByLabelText("Ağırlık merkezi (burun ucundan)"), { target: { value: "900" } });
    expect(screen.getByTestId("cfd-mach")).toHaveTextContent("0.147");
    fireEvent.click(screen.getByRole("button", { name: /Barrowman/ }));
    expect(await screen.findByTestId("cfd-barrowman")).toHaveTextContent("kararlılık 2.77 kal.");
    expect(vi.mocked(postBarrowman).mock.calls[0][0]).toEqual({ geometry_id: 9, cg_mm: 900 });
    fireEvent.click(screen.getByRole("button", { name: "Roket koşusunu çalıştır" }));
    expect(await screen.findByTestId("cfd-rocket-aero")).toHaveTextContent("1220.6 mm");
    const body = vi.mocked(postRocketSolve).mock.calls[0][0];
    expect(body).toMatchObject({ mesh_id: "m1", speed_m_s: 50, alpha_deg: 4, cg_mm: 900 });
    expect(screen.getByTestId("cfd-rocket-barrowman")).toHaveTextContent("%46.0");
    expect(screen.getByTestId("cfd-patch-forces")).toHaveTextContent("burun");
    expect(vi.mocked(postCfdSolve)).not.toHaveBeenCalled();
  });
});
