import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashPanel from "./CrashPanel";

vi.mock("../api/crash", () => ({
  CrashApiError: class CrashApiError extends Error {},
  postCrashSolve: vi.fn(),
  fetchCrashJob: vi.fn(),
  crashJobWsUrl: vi.fn(() => "ws://localhost/crash/jobs/j1/ws"),
  fetchCrashRuns: vi.fn(() => Promise.resolve([])),
  patchCrashRun: vi.fn(),
  compareCrashRuns: vi.fn(() => Promise.resolve([])),
  fetchCrashValidation: vi.fn(() => new Promise(() => undefined)),
  fetchValidationThresholds: vi.fn(() => new Promise(() => undefined)),
  putValidationThresholds: vi.fn(),
  postCrashScenario: vi.fn(),
  fetchCrashCatalog: vi.fn(() => new Promise(() => undefined)),
}));

vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn(() => Promise.resolve([])) }));
vi.mock("../api/templates", () => ({ fetchTemplates: vi.fn(() => new Promise(() => undefined)) }));

import { fetchCrashJob, postCrashSolve } from "../api/crash";

/** Akordeon grubunu aç (Çarpma açık başlar; Parçalar / Temaslar kapalı). */
const openGroup = (title: string) =>
  fireEvent.click(screen.getByRole("button", { name: new RegExp(title), expanded: false }));

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
    const { rerender } = render(
      <CrashPanel
        geometryId={1}
        meshDimension={3}
        partIds={[0, 1]}
        materialAssignments={[{ part_id: 0, material_name: "S235" }]}
      />,
    );
    openGroup("Parçalar");
    const table = screen.getByTestId("crash-parts");
    expect(table).toHaveTextContent("#0");
    expect(table).toHaveTextContent("S235");
    expect(table).toHaveTextContent("malzeme yok");
    // Eksik malzeme: düğme pasif, nedeni yazılı (tasarım kuralı 5)
    expect(screen.getByTestId("crash-blockers")).toHaveTextContent("malzemesiz #1");
    expect(screen.getByRole("button", { name: ".rad üret / çöz" })).toBeDisabled();
    fireEvent.click(
      within(screen.getByRole("group", { name: "Parça 1 rolü" })).getByRole("button", { name: "Sabit" }),
    );
    // Sabit parçanın malzemesi yine gerekir; listede yoksa atanmış sayılmaz → atanınca düğme açılır
    rerender(
      <CrashPanel
        geometryId={1}
        meshDimension={3}
        partIds={[0, 1]}
        materialAssignments={[{ part_id: 0, material_name: "S235" }, { part_id: 1, material_name: "S235" }]}
      />,
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

  it("2D mesh: kabuk kartı, ürün ağacı kalınlığını gösterir, dimension=2 gönderir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j8", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: { has_shell: true }, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(
      <CrashPanel geometryId={1} meshDimension={2} partIds={[0, 1]} componentThickness={{ 0: 3, 1: null }} />,
    );
    expect(screen.getByText("Kabuk — /PROP/TYPE1")).toBeInTheDocument();
    expect(screen.queryByText("Eleman — /PROP/TYPE14")).not.toBeInTheDocument();
    // kalınlık yalnız gösterilir (tek kaynak: ürün ağacı); girdi yok
    openGroup("Parçalar");
    expect(screen.getByTestId("crash-parts")).toHaveTextContent("t 3 mm");
    expect(screen.getByTestId("crash-parts")).toHaveTextContent("t yok mm");
    expect(screen.queryByLabelText(/t (mm) — ortak/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ishell"), { target: { value: "24" } });
    fireEvent.change(screen.getByLabelText("N"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Hourglass Hm"), { target: { value: "0.02" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashSolve).mock.calls[0][0];
    expect(body.dimension).toBe(2);
    expect(body.parts).toEqual([
      { part_id: 0, role: "moving" },
      { part_id: 1, role: "moving" },
    ]);
    expect(body.model?.shell).toEqual({ ishell: 24, ish3n: 0, ismstr: 0, nip: 5, hm: 0.02, hf: 0, hr: 0 });
    expect(body.model?.solid_hourglass_h).toBe(0);
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
    fireEvent.change(screen.getByLabelText("Hız"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(
      expect.objectContaining({
        geometry_id: 1,
        run_solver: false,
        barrier: expect.objectContaining({ speed_m_s: 15, wall: { point: [0, 0, 0], normal: [0, 0, 1] } }),
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
    // eski "Plaka–küre" ön ayarı kaldırıldı — seçici yok
    expect(screen.queryByRole("button", { name: "Plaka–küre" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "LAW2 plastik" }));
    fireEvent.change(screen.getByLabelText("NIP"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Isolid"), { target: { value: "14" } });
    fireEvent.change(screen.getByLabelText("LAW2 b (MPa)"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(postCrashSolve).toHaveBeenCalledWith(
      expect.objectContaining({
        barrier: expect.objectContaining({ speed_m_s: 10 }),
        model: expect.objectContaining({
          law: "plastic",
          isolid: 14,
          nip: 4,
          harden_b_mpa: 80,
        }),
      }),
    );
    expect(vi.mocked(postCrashSolve).mock.calls[0][0]).not.toHaveProperty("scenario");
  });
  it("temas satırlarını ve duvar bayrağını gönderir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j5", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} partIds={[0, 1]} />);
    openGroup("Temaslar");
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
    // 11.2 — engel sorusu: Yok → duvar alanları gizlenir, ilk hız yönü vektörle
    openGroup("Çarpma");
    fireEvent.click(screen.getByRole("radio", { name: "Duvarsız · yalnız ilk hız" }));
    expect(screen.queryByLabelText("Duvar konumu")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Çarpma/ })).toHaveTextContent("duvarsız");
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
    openGroup("Temaslar");
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
  it("1.14e: parça başına ayrı kart yalnız o parçaya model gönderir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j10", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} partIds={[0, 1]} />);
    // global LAW2, parça 1 ayrı kart (global kopyası) → LAW36 + TENSSTRAIN
    fireEvent.click(
      within(screen.getByTestId("crash-mat-global")).getByRole("button", { name: "LAW2 plastik" }),
    );
    fireEvent.click(
      within(screen.getByRole("group", { name: "Parça 1 kartı" })).getByRole("button", { name: "Ayrı" }),
    );
    const card = screen.getByTestId("crash-mat-part-1");
    expect(within(card).getByRole("button", { name: "LAW2 plastik" })).toHaveClass("active");
    fireEvent.click(within(card).getByRole("button", { name: "LAW36 tablo" }));
    fireEvent.change(within(card).getByLabelText("Eğri 1 noktaları"), { target: { value: "0 235\n1 235" } });
    fireEvent.click(within(card).getByLabelText("/FAIL/TENSSTRAIN"));
    fireEvent.change(within(card).getByLabelText("ε_t1"), { target: { value: "0.1" } });
    fireEvent.change(within(card).getByLabelText("ε_t2"), { target: { value: "0.2" } });
    fireEvent.change(screen.getByLabelText("Isolid"), { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashSolve).mock.calls[0][0];
    expect(body.model).toMatchObject({ law: "plastic", isolid: 14 });
    expect(body.model?.fail).toBeUndefined();
    expect(body.parts?.[0]).toEqual({ part_id: 0, role: "moving" });
    expect(body.parts?.[1].model).toMatchObject({
      law: "tabulated",
      isolid: 14, // eleman bayrakları globalden
      tab_curves: [{ eps_dot_per_s: 0, points: [[0, 235], [1, 235]] }],
      fail: { tensstrain: { eps_t1: 0.1, eps_t2: 0.2 } },
    });
    // Global'e dönünce parça kartı kalkar
    fireEvent.click(
      within(screen.getByRole("group", { name: "Parça 1 kartı" })).getByRole("button", { name: "Global" }),
    );
    expect(screen.queryByTestId("crash-mat-part-1")).not.toBeInTheDocument();
  });

  it("1.14e: geçersiz eğri gönderilmez, hata alan adıyla gösterilir", async () => {
    render(<CrashPanel geometryId={1} meshDimension={3} />);
    fireEvent.click(screen.getByRole("button", { name: "LAW36 tablo" }));
    fireEvent.change(screen.getByLabelText("Eğri 1 noktaları"), { target: { value: "0 235 9" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    expect(await screen.findByText(/Global eğri 1: "0 235 9" iki sütun/)).toBeInTheDocument();
    expect(postCrashSolve).not.toHaveBeenCalled();
  });

  it("1.14f: silinen eleman ve starter mesaj ID'lerini gösterir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j11", geometry_id: 1, status: "solved", message: "OpenRadioss bitti",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: true, solver_ran: true,
      scalars: { elements_deleted: 133, deletion_time_first: 0.054, deletion_time_last: 3.78 },
      diagnostics: { starter_errors: {}, starter_warnings: { "1912": 1, "1220": 2 } },
    });
    render(<CrashPanel geometryId={1} meshDimension={2} />);
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    expect(await screen.findByTestId("crash-deleted")).toHaveTextContent(
      "Silinen eleman 133 · ilk ≤ 5.400e-2 ms · son ≤ 3.780 ms",
    );
    expect(screen.getByTestId("crash-starter-msgs")).toHaveTextContent(
      "Starter · 0 hata · uyarı ID 1220 ×2, 1912",
    );
  });
  it("1.15d: engine / th / sections gönderir; kesit ve Δt sonuçlarını gösterir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j12", geometry_id: 1, status: "solved", message: "OpenRadioss bitti",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: true, solver_ran: true,
      scalars: {
        section_1_force_max: 123.9, section_1_impulse_final: 13.42,
        timestep_min: 0.001, mass_added_rel: 0.565,
      },
    });
    render(<CrashPanel geometryId={1} meshDimension={2} partIds={[0]} />);
    fireEvent.change(screen.getByLabelText("TH aralığı (ms)"), { target: { value: "0.002" } });
    fireEvent.click(screen.getByRole("button", { name: "+ Kesit ekle" }));
    fireEvent.change(screen.getByLabelText("Kesit 1 M1 y"), { target: { value: "60" } });
    fireEvent.change(screen.getByLabelText("Kesit 1 M2 z"), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashSolve).mock.calls[0][0];
    expect(body.engine?.th_dt_ms).toBe(0.002);
    expect(body.th?.rwall.vars).toEqual(["FNX", "FNY", "FNZ"]);
    expect(body.sections).toHaveLength(1);
    expect(body.sections?.[0].corner1).toEqual([0, 60, 0]);
    expect(await screen.findByText(/Kesit 1 Fmax 123\.9 kN · impuls 13\.420 N·s/)).toBeInTheDocument();
    expect(screen.getByTestId("crash-timestep")).toHaveTextContent("Δt_min 1.000e-3 ms · eklenen kütle %56.5");
  });
  it("1.17e: CFC sınıfı gönderilir, süzülmüş tepeler gösterilir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j13", geometry_id: 1, status: "solved", message: "", starter_url: "", engine_url: "",
      progress_url: "", ws_url: "", cards: {}, openradioss_available: true, solver_ran: true,
      scalars: { rwall_force_max: 130.9, rwall_force_max_cfc600: 101.2, sample_ratio_cfc600: 833 },
    });
    render(<CrashPanel geometryId={1} meshDimension={2} />);
    fireEvent.change(screen.getByLabelText("Kuvvet CFC"), { target: { value: "600" } });
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    expect(vi.mocked(postCrashSolve).mock.calls[0][0].filters).toEqual({ force_cfc: 600, acc_cfc: null });
    const peaks = await screen.findAllByTestId("crash-cfc-peak");
    expect(peaks.map((p) => p.textContent)).toEqual(["rwall_force_max CFC600 101.2"]);
  });
  it("1.17g: iş bitince eski cycle satırı gösterilmez", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j14", geometry_id: 1, status: "pending", message: "çalışıyor", starter_url: "", engine_url: "",
      progress_url: "", ws_url: "", cards: {}, openradioss_available: true, solver_ran: false, scalars: {},
    });
    vi.mocked(fetchCrashJob).mockResolvedValue({ job_id: "j14", status: "solved", message: "bitti", cycle: 1, time_ms: 0 });
    render(<CrashPanel geometryId={1} meshDimension={2} />);
    fireEvent.click(screen.getByLabelText(/OpenRadioss çalıştır/));
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    expect(await screen.findByText(/solved · bitti/)).toBeInTheDocument();
    expect(screen.queryByText(/cycle 1/)).not.toBeInTheDocument();
  });

  it("11.7: parça satırı seçimi / hover App'e bildirilir; seçili satır işaretli", () => {
    const onPartSelect = vi.fn();
    const onPartHover = vi.fn();
    render(
      <CrashPanel
        geometryId={1}
        meshDimension={3}
        partIds={[0, 1]}
        selectedPartIds={[1]}
        onPartSelect={onPartSelect}
        onPartHover={onPartHover}
      />,
    );
    openGroup("Parçalar");
    const table = screen.getByTestId("crash-parts");
    const pick1 = within(table).getByRole("button", { name: "#1" });
    expect(pick1).toHaveAttribute("aria-pressed", "true");
    expect(pick1.closest(".crash-behavior")).toHaveClass("crash-part-selected");
    expect(within(table).getByRole("button", { name: "#0" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(within(table).getByRole("button", { name: "#0" }));
    expect(onPartSelect).toHaveBeenCalledWith(0);
    fireEvent.mouseEnter(pick1.closest(".crash-behavior")!);
    expect(onPartHover).toHaveBeenLastCalledWith(1);
    fireEvent.mouseLeave(pick1.closest(".crash-behavior")!);
    expect(onPartHover).toHaveBeenLastCalledWith(null);
  });

  it("tasarım: akordeon özetleri + hazır sayacı; yön düğmeleri duvar normalini verir", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j12", geometry_id: 1, status: "rad_only", message: "",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    render(<CrashPanel geometryId={1} meshDimension={3} partIds={[0, 1]} />);
    const impact = screen.getByRole("button", { name: /Çarpma/, expanded: true });
    expect(impact).toHaveTextContent("10 m/s · −Z yönü · rijit duvar z=0");
    expect(impact).toHaveTextContent("hazır");
    expect(screen.getByRole("button", { name: /Parçalar/ })).toHaveTextContent("#0 hareketli · #1 hareketli");
    expect(screen.getByRole("button", { name: /Temaslar/ })).toHaveTextContent("isteğe bağlı");
    expect(screen.getByTestId("crash-ready-count")).toHaveTextContent("3 / 3 hazır");
    // duvar −X'e baksın → parça +X yönünde ilerler
    fireEvent.click(screen.getByRole("radio", { name: "-X" }));
    expect(screen.getByText(/normalin tersine \(\+X\) ilerler/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Duvar konumu"), { target: { value: "120, 0, 0" } });
    expect(impact).toHaveTextContent("rijit duvar x=120");
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(postCrashSolve).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashSolve).mock.calls[0][0];
    expect(body.barrier.wall).toEqual({ point: [120, 0, 0], normal: [-1, 0, 0] });
    expect(body.use_rigid_wall).toBe(true);
  });

  it("tasarım: eksik bilgi düğmeyi kapatır ve nedenini yazar; duvarsızda temas eksik sayılır", () => {
    render(<CrashPanel geometryId={1} meshDimension={3} partIds={[0, 1]} />);
    fireEvent.change(screen.getByLabelText("Duvar konumu"), { target: { value: "1, 2" } });
    expect(screen.getByTestId("crash-blockers")).toHaveTextContent("duvar konumu 'x, y, z' olmalı");
    expect(screen.getByRole("button", { name: ".rad üret / çöz" })).toBeDisabled();
    expect(screen.getByTestId("crash-ready-count")).toHaveTextContent("2 / 3 hazır");
    fireEvent.click(screen.getByRole("radio", { name: "Duvarsız · yalnız ilk hız" }));
    expect(screen.getByTestId("crash-blockers")).toHaveTextContent("parçalar arası temas yok");
    expect(screen.getByRole("button", { name: /Temaslar/ })).toHaveTextContent("1 eksik");
  });

  it("tasarım: varsayılan bayraklar boş, gri 'varsayılan' yazar", () => {
    render(<CrashPanel geometryId={1} meshDimension={2} partIds={[0]} />);
    expect(screen.getByLabelText("Ishell")).toHaveValue("");
    expect(screen.getByLabelText("Ishell")).toHaveAttribute("placeholder", "varsayılan");
  });

  it("adım 3: view=setup kurulum + çalıştır; view=results sonuçlar + çıktı ayarları", async () => {
    vi.mocked(postCrashSolve).mockResolvedValue({
      job_id: "j20", geometry_id: 1, status: "rad_only", message: "rad üretildi",
      starter_url: "", engine_url: "", progress_url: "", ws_url: "",
      cards: {}, openradioss_available: false, solver_ran: false, scalars: {},
    });
    const onRunStarted = vi.fn();
    const onJobKey = vi.fn();
    const { rerender } = render(
      <CrashPanel geometryId={1} meshDimension={3} view="setup" onRunStarted={onRunStarted} onJobKey={onJobKey} />,
    );
    expect(screen.queryByLabelText("Sonuçlar")).not.toBeInTheDocument();
    expect(screen.queryByText(/Çıktı — kayıt aralığı/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: ".rad üret / çöz" }));
    await waitFor(() => expect(onRunStarted).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onJobKey).toHaveBeenCalledWith("j20:rad_only"));
    rerender(<CrashPanel geometryId={1} meshDimension={3} view="results" onRunStarted={onRunStarted} onJobKey={onJobKey} />);
    expect(screen.getByLabelText("Sonuçlar")).toHaveTextContent("j20");
    expect(screen.getByText(/Çıktı — kayıt aralığı/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: ".rad üret / çöz" })).not.toBeInTheDocument();
  });

  it("tasarım 2: viewport işaretleri bildirilir; Modelden seç duvar konumunu doldurur", async () => {
    const onMarkersChange = vi.fn();
    let done: ((p: [number, number, number]) => void) | null = null;
    render(
      <CrashPanel
        geometryId={1}
        meshDimension={3}
        partIds={[0, 1]}
        onMarkersChange={onMarkersChange}
        onRequestPointPick={(cb) => {
          done = cb;
        }}
      />,
    );
    await waitFor(() =>
      expect(onMarkersChange).toHaveBeenLastCalledWith({
        wall: { point: [0, 0, 0], normal: [0, 0, 1] },
        velocity: { dir: [0, 0, -1], label: "10 m/s" },
        partLabels: { 0: "#0 hareketli", 1: "#1 hareketli" },
        partRoles: { 0: "moving", 1: "moving" },
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "⌖ Modelden seç" }));
    expect(done).not.toBeNull();
    act(() => done!([12.5, 0, 40]));
    expect(screen.getByLabelText("Duvar konumu")).toHaveValue("12.5, 0, 40");
    await waitFor(() =>
      expect(onMarkersChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ wall: { point: [12.5, 0, 40], normal: [0, 0, 1] } }),
      ),
    );
  });
});
