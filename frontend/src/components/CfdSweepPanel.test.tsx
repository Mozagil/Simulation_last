import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/cfd";
import CfdSweepPanel, { parseList } from "./CfdSweepPanel";

const BASE = { mesh_id: "m1", rho_kg_m3: 1.225, nu_m2_s: 1.46e-5, temperature_k: 288.15, turbulence_model: "kOmegaSST", solver: "rhoSimpleFoam", iterations: 500, relax_u: 0.5, relax_other: 0.3 } as never;

describe("CfdSweepPanel (R5)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("liste ayrıştırma", () => {
    expect(parseList("0.3, 0.5;0.8  1.2")).toEqual([0.3, 0.5, 0.8, 1.2]);
    expect(parseList("a, 2")).toEqual([2]);
  });

  it("ızgarayı gönderir, noktaları ve Mach tablosunu gösterir", async () => {
    const post = vi.spyOn(api, "postRocketSweep").mockResolvedValue({
      sweep_id: "s1", status: "pending", solver: "rhoSimpleFoam", table: [],
      points: [{ mach: 0.5, alpha_deg: 0, speed_m_s: 170.1, status: "pending" }, { mach: 0.5, alpha_deg: 4, speed_m_s: 170.1, status: "pending" }],
    });
    vi.spyOn(api, "fetchRocketSweep").mockResolvedValue({
      sweep_id: "s1", status: "done", solver: "rhoSimpleFoam", message: "2/2 nokta çözüldü",
      points: [
        { mach: 0.5, alpha_deg: 0, speed_m_s: 170.1, status: "solved", CD: 0.41, CN: 0.0 },
        { mach: 0.5, alpha_deg: 4, speed_m_s: 170.1, status: "solved", CD: 0.46, CN: 1.14, x_cp_m: 1.18 },
      ],
      table: [{ mach: 0.5, n_points: 2, CD_alpha_min: 0.41, alpha_min_deg: 0, CN_alpha_per_rad: 16.3, x_cp_m_mean: 1.18 }],
    });
    render(<CfdSweepPanel base={BASE} temperatureK={288.15} pollMs={1} />);
    fireEvent.change(screen.getByLabelText("Mach listesi"), { target: { value: "0.5" } });
    fireEvent.change(screen.getByLabelText("α listesi"), { target: { value: "0, 4" } });
    fireEvent.click(screen.getByRole("button", { name: /Taramayı başlat \(2 koşu\)/ }));
    await waitFor(() => expect(screen.getByTestId("cfd-sweep-table")).toHaveTextContent("16.30"));
    expect(post.mock.calls[0][0]).toMatchObject({ mesh_id: "m1", machs: [0.5], alphas_deg: [0, 4], solver: "rhoSimpleFoam" });
    expect(screen.getByTestId("cfd-sweep-status")).toHaveTextContent("2/2");
    expect(screen.getByRole("link", { name: "Tablo CSV" })).toHaveAttribute("href", expect.stringContaining("/cfd/rocket/sweep/s1/csv?kind=table"));
  });
});
