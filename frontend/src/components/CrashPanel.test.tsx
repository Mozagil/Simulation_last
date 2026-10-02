import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("parça rollerini gönderir; malzemesiz parçayı işaretler", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j9", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(
      <CrashPanel
        geometryId={1}
        meshDimension={3}
        partIds={[0, 1]}
        materialAssignments={[{ part_id: 0, material_name: "S235" }]}
      />,
    );
    const table = screen.getByTestId("crash-parts");
    expect(table).toHaveTextContent("#0");
    expect(table).toHaveTextContent("S235");
    expect(table).toHaveTextContent("atama yok");
    fireEvent.click(
      within(screen.getByRole("group", { name: "Parça 1 rolü" })).getByRole("button", { name: "Sabit" }),
    );
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(
      expect.objectContaining({
        parts: [
          { part_id: 0, role: "moving" },
          { part_id: 1, role: "fixed" },
        ],
      }),
    );
  });

  it("mesh yokken gönderimi kapatır", () => {
    render(<CrashPanel geometryId={1} meshDimension={null} />);
    expect(screen.getByRole("button", { name: ".rad üret / çöz" })).toBeDisabled();
    expect(screen.getByText(/Mesh yok/)).toBeInTheDocument();
  });

  it("2D mesh: kabuk kartı, parça kalınlığı ve dimension=2 gönderir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j8", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: { has_shell: true }, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={2} partIds={[0, 1]} />);
    expect(screen.getByText("Kabuk — /PROP/TYPE1")).toBeInTheDocument();
    expect(screen.queryByText("Eleman — /PROP/TYPE14")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("t (mm) — ortak"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Parça 1 t"), { target: { value: "1.5" } });
    fireEvent.change(screen.getByLabelText("Ishell"), { target: { value: "24" } });
    fireEvent.change(screen.getByLabelText("N"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(
      expect.objectContaining({
        dimension: 2,
        parts: [
          { part_id: 0, role: "moving", thickness_mm: null },
          { part_id: 1, role: "moving", thickness_mm: 1.5 },
        ],
        model: expect.objectContaining({
          shell: { thickness_mm: 3, ishell: 24, ish3n: 0, ismstr: 0, nip: 5 },
        }),
      }),
    );
  });

  it("3D mesh: solid kartı gösterir, kabuk alanı göndermez", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j9", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} partIds={[0]} />);
    expect(screen.getByText("Eleman — /PROP/TYPE14")).toBeInTheDocument();
    expect(screen.queryByLabelText("Parça 0 t")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashSolve).mock.calls[0][0];
    expect(body.dimension).toBe(3);
    expect(body.model).not.toHaveProperty("shell");
    expect(body.parts?.[0]).not.toHaveProperty("thickness_mm");
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
  it("temas satırlarını ve duvar bayrağını gönderir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j5", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} partIds={[0, 1]} />);
    expect(screen.queryByTestId("crash-contacts")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Temas ekle" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Temas ekle" }));
    // 1: TYPE7, kutu (0) düğümleri → plaka (1); sürtünme + gap
    fireEvent.change(screen.getByLabelText("Temas 1 Fric"), { target: { value: "0.2" } });
    fireEvent.change(screen.getByLabelText("Temas 1 GAPmin"), { target: { value: "0.5" } });
    // 2: TYPE24 self-contact parça 0, kenar–kenar açık
    fireEvent.click(within(screen.getByRole("group", { name: "Temas 2 tipi" })).getByRole("button", { name: "TYPE24" }));
    fireEvent.change(screen.getByLabelText("Temas 2 master"), { target: { value: "0" } });
    expect(screen.queryByLabelText("Temas 2 GAPmin")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Temas 1 Iedge")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Temas 2 Iedge"), { target: { value: "1" } });
    expect(screen.getByTestId("crash-contacts")).toHaveTextContent("2 · self");
    fireEvent.click(screen.getByLabelText("Rijit duvar (/RWALL)"));
    expect(screen.getByText(/duvar kapalı, yalnız ilk hız yönü/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(
      expect.objectContaining({
        use_rigid_wall: false,
        contacts: [
          { type: 7, master_part: 1, slave_part: 0, fric: 0.2, stfac: 1, gapmin: 0.5, istf: 0, inacti: 0, iedge: 0 },
          { type: 24, master_part: 0, slave_part: 0, fric: 0, stfac: 1, gapmin: 0, istf: 0, inacti: 0, iedge: 1 },
        ],
      }),
    );
  });

  it("temas satırı silinir; tanım yoksa boş liste ve duvar açık gider", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j6", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} />);
    fireEvent.click(screen.getByRole("button", { name: "+ Temas ekle" }));
    fireEvent.click(screen.getByRole("button", { name: "Temas 1 sil" }));
    expect(screen.queryByTestId("crash-contacts")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(expect.objectContaining({ contacts: [], use_rigid_wall: true }));
  });

  it("çözülen işte temas kuvveti grafiğini ve tepe değerini gösterir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j7", geometry_id: 1, status: "pending", message: "kuyrukta",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: true, solver_ran: false, scalars: {},
    });
    vi.mocked(fetchCrashJob).mockResolvedValue({
      job_id: "j7", status: "solved", message: "OpenRadioss bitti",
      scalars: { contact_1_force_max: 86.35, contact_1_impulse_final: 6.743 },
      curves: { time: [0, 0.1, 0.2, 0.3], contact_1_force: [0, 40, 86.35, 0] },
    });
    render(<CrashPanel geometryId={1} meshDimension={3} />);
    fireEvent.click(screen.getByLabelText(/OpenRadioss çalıştır/));
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    expect(await screen.findByRole("img", { name: "Kuvvet–zaman grafiği" })).toBeInTheDocument();
    expect(screen.getByText(/Temas 1 Fmax 86.350 kN · impuls 6.743 N·s/)).toBeInTheDocument();
    expect(screen.getByText("Temas 1 tepe")).toBeInTheDocument();
    expect(screen.getByText("t = 0.200 ms")).toBeInTheDocument();
  });
});

