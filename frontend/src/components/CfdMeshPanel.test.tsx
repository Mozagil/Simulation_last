import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CfdMeshPanel from "./CfdMeshPanel";
import { fetchCfdMesh, postCfdMesh, type CfdMeshMeta } from "../api/cfd";

vi.mock("../api/cfd", async (orig) => {
  const mod = await orig<typeof import("../api/cfd")>();
  return { ...mod, postCfdMesh: vi.fn(), fetchCfdMesh: vi.fn() };
});

const base: CfdMeshMeta = {
  mesh_id: "m1",
  geometry_id: 7,
  mesher: "snappy",
  status: "pending",
  message: "mesh kuyrukta",
  patches: ["inlet", "outlet", "sides", "burun", "govde"],
  surface: { regions: ["burun", "govde"], triangles: 1234, triangles_per_region: {}, open_edges: 0, bbox_m: [] },
  domain: { min_m: [], max_m: [], background_cells: [20, 14, 14], body_length_m: 1.5 },
  check: {},
};

const meshed: CfdMeshMeta = {
  ...base,
  status: "meshed",
  message: "mesh hazır · 142346 hücre · checkMesh OK",
  check: {
    cells: 142346,
    hexahedra: 125666,
    polyhedra: 14561,
    non_orthogonality_max: 53.3,
    non_orthogonality_avg: 6.1,
    skewness_max: 1.2,
    aspect_ratio_max: 26.2,
    failed_checks: 0,
    mesh_ok: true,
    patch_faces: { inlet: 100, burun: 500 },
  },
  snappy: { layers: { burun: { faces: 500, target_layers: 2, layers: 1.94, thickness_m: 0.001, thickness_percent: 95.3 } } },
};

describe("CfdMeshPanel (AKIŞ · 2 · Mesh)", () => {
  beforeEach(() => {
    vi.mocked(postCfdMesh).mockReset().mockResolvedValue(base);
    vi.mocked(fetchCfdMesh).mockReset().mockResolvedValue(meshed);
  });

  it("geometri yokken mesh üretilemez", () => {
    render(<CfdMeshPanel geometryId={null} />);
    expect(screen.getByRole("button", { name: "Mesh üret" })).toBeDisabled();
  });

  it("tünel + mesh'leyici ayarlarını gönderir, sonucu checkMesh tablosu ve yamalarla gösterir", async () => {
    const onReady = vi.fn();
    render(<CfdMeshPanel geometryId={7} onMeshReady={onReady} pollMs={1} />);
    fireEvent.change(screen.getByLabelText("Taban hücre"), { target: { value: "0,15" } });
    fireEvent.click(screen.getByRole("button", { name: /Mesh'leyici, inceltme/ }));
    fireEvent.click(screen.getByRole("button", { name: "cfMesh" }));
    expect(screen.getByLabelText("Kenar seviyesi")).toBeDisabled(); // yalnız snappy
    fireEvent.click(screen.getByRole("button", { name: "Mesh üret" }));
    await waitFor(() => expect(onReady).toHaveBeenCalledWith(meshed));
    const body = vi.mocked(postCfdMesh).mock.calls[0][0];
    expect(body.mesher).toBe("cfmesh");
    expect(body.tunnel.base_cell_m).toBe(0.15);
    expect(body.snappy.stl_size_mm).toBeNull();
    expect(screen.getByText("Mesh OK")).toBeInTheDocument();
    expect(screen.getByTestId("cfd-mesh-patches")).toHaveTextContent("burun · 500 yüz");
    expect(screen.getByText("%95.3")).toBeInTheDocument();
  });

  it("başarısız mesh mesajını gösterir", async () => {
    vi.mocked(fetchCfdMesh).mockResolvedValue({ ...base, status: "failed", message: "Mesh üretilemedi (log.snappyHexMesh)" });
    render(<CfdMeshPanel geometryId={7} pollMs={1} />);
    fireEvent.click(screen.getByRole("button", { name: "Mesh üret" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mesh üretilemedi");
  });
});
