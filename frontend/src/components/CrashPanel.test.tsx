import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashPanel from "./CrashPanel";

vi.mock("../api/crash", () => ({
  CrashApiError: class CrashApiError extends Error {},
  postCrashSolve: vi.fn(),
  fetchCrashJob: vi.fn(),
  crashJobWsUrl: vi.fn(() => "ws://localhost/crash/jobs/j1/ws"),
}));

import { fetchCrashJob, postCrashSolve } from "../api/crash";

describe("CrashPanel", () => {
  beforeEach(() => {
    vi.mocked(postCrashSolve).mockReset();
    vi.mocked(fetchCrashJob).mockReset();
  });

  it("3D mesh yokken gönderimi kapatır", () => {
    render(<CrashPanel geometryId={1} meshDimension={2} />);
    expect(screen.getByRole("button", { name: ".rad üret / çöz" })).toBeDisabled();
    expect(screen.getByText(/3D tet mesh yok/)).toBeInTheDocument();
  });

  it("bariyer gönderir ve rad_only durumunu gösterir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j1",
      geometry_id: 1,
      status: "rad_only",
      message: "rad üretildi",
      starter_url: "/files/crash/j1/crash_0000.rad",
      engine_url: "/files/crash/j1/crash_0001.rad",
      progress_url: "/crash/jobs/j1",
      ws_url: "/crash/jobs/j1/ws",
      cards: { has_tetra4: true, has_rwall: true, has_inivel: true, has_tfile: true },
      openradioss_available: false,
      solver_ran: false,
      scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} />);
    fireEvent.change(screen.getByLabelText("Hız (m/s)"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(
      expect.objectContaining({
        geometry_id: 1,
        run_solver: false,
        scenario: "rigid_wall",
        barrier: expect.objectContaining({ speed_m_s: 15 }),
        model: expect.objectContaining({
          law: "elastic",
          isolid: 1,
          nip: 1,
        }),
      }),
    );
    expect(await screen.findByText(/rad_only/)).toBeInTheDocument();
  });

  it("çözüm skalerlerini ayrı panelde gösterir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j2",
      geometry_id: 1,
      status: "solved",
      message: "OpenRadioss bitti",
      starter_url: "/files/crash/j2/crash_0000.rad",
      engine_url: "/files/crash/j2/crash_0001.rad",
      progress_url: "/crash/jobs/j2",
      ws_url: "/crash/jobs/j2/ws",
      cards: {},
      openradioss_available: true,
      solver_ran: true,
      scalars: { hic15: 1500, hic36: 1500, acc_peak_g: 100 },
    });
    render(<CrashPanel geometryId={1} meshDimension={3} />);
    fireEvent.click(screen.getByLabelText(/OpenRadioss çalıştır/));
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    expect(await screen.findByText(/HIC15 1500/)).toBeInTheDocument();
    expect(screen.getByText(/HIC36 1500/)).toBeInTheDocument();
  });

  it("plaka–küre ve LAW2 alanlarını gönderir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j3",
      geometry_id: 1,
      status: "rad_only",
      message: "rad üretildi",
      starter_url: "/files/crash/j3/crash_0000.rad",
      engine_url: "/files/crash/j3/crash_0001.rad",
      progress_url: "/crash/jobs/j3",
      ws_url: "/crash/jobs/j3/ws",
      cards: { has_law2: true },
      openradioss_available: false,
      solver_ran: false,
      scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} />);
    fireEvent.click(screen.getByRole("button", { name: "Plaka–küre" }));
    fireEvent.click(screen.getByRole("button", { name: "LAW2 plastik" }));
    fireEvent.change(screen.getByLabelText("NIP"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Isolid"), { target: { value: "14" } });
    fireEvent.change(screen.getByLabelText("LAW2 b (MPa)"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(
      expect.objectContaining({
        scenario: "plate_ball",
        barrier: expect.objectContaining({ speed_m_s: 20 }),
        model: expect.objectContaining({
          law: "plastic",
          isolid: 14,
          nip: 4,
          harden_b_mpa: 80,
        }),
      }),
    );
    expect(screen.getByRole("img", { name: /Plaka-küre/i })).toBeInTheDocument();
  });
});
