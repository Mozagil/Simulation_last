import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { jet, triangulate, VIEW_VECTORS } from "./CrashAnimationViewer";

vi.mock("../api/crash", () => ({
  fetchCrashRuns: vi.fn(() =>
    Promise.resolve([
      { id: 7, job_id: "j7", geometry_id: 1, name: "çözülmüş", created_at: null, dimension: 2, t_end_ms: 4,
        status: "solved", message: null, solver_ran: true, scalars: {}, excluded: false, exclude_reason: null },
      { id: 8, job_id: "j8", geometry_id: 1, name: "yalnız deck", created_at: null, dimension: 2, t_end_ms: 4,
        status: "rad_only", message: null, solver_ran: false, scalars: {}, excluded: false, exclude_reason: null },
    ]),
  ),
  patchCrashRun: vi.fn(),
  compareCrashRuns: vi.fn(),
  fetchCrashAnimation: vi.fn(() => new Promise(() => undefined)),
}));

// jsdom'da WebGL yok: görüntüleyiciyi yalnız açılma bağlantısı için sahte bileşenle değiştir
vi.mock("./CrashAnimationViewer", async (orig) => {
  const real = await orig<typeof import("./CrashAnimationViewer")>();
  return { ...real, default: ({ runId, title }: { runId: number; title?: string }) => (
    <div data-testid="anim-stub">{`${runId} ${title}`}</div>
  ) };
});

import CrashHistory from "./CrashHistory";

describe("CrashAnimationViewer yardımcıları", () => {
  it("dörtgen iki üçgene, üçgen bir üçgene; kaynak yüz korunur", () => {
    const { vtx, tri_face } = triangulate([[0, 1, 2, 3], [4, 5, 6]]);
    expect(Array.from(vtx)).toEqual([0, 1, 2, 0, 2, 3, 4, 5, 6]);
    expect(Array.from(tri_face)).toEqual([0, 0, 1]);
  });

  it("jet: proje görüntüleyicileriyle aynı uçlar", () => {
    expect(jet(0)).toEqual([0, 0, 0.5]);
    expect(jet(0.5)).toEqual([0.5, 1, 0.5]);
    expect(jet(1)).toEqual([0.5, 0, 0]);
    expect(jet(-3)).toEqual(jet(0)); // kırpılır
  });
});

describe("hazır görünümler", () => {
  it("eksen görünümleri tek eksende, izo üçünde", () => {
    expect(VIEW_VECTORS["+X"]).toEqual([1, 0, 0]);
    expect(VIEW_VECTORS["-X"]).toEqual([-1, 0, 0]);
    expect(VIEW_VECTORS["+Z"]).toEqual([0, 0, 1]);
    expect(VIEW_VECTORS.izo.every((c) => c > 0)).toBe(true);
  });
});

describe("CrashHistory → deforme şekil", () => {
  it("çözülmüş koşuda ▶ görüntüleyiciyi açar / kapatır; çözülmemişte kapalı", async () => {
    render(<CrashHistory geometryId={1} />);
    const btn = await screen.findByRole("button", { name: "çözülmüş deforme şekil" });
    expect(screen.getByRole("button", { name: "yalnız deck deforme şekil" })).toBeDisabled();
    fireEvent.click(btn);
    expect(screen.getByTestId("anim-stub")).toHaveTextContent("7 #7 çözülmüş");
    fireEvent.click(btn);
    expect(screen.queryByTestId("anim-stub")).not.toBeInTheDocument();
  });
});
