import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashHistory from "./CrashHistory";

vi.mock("../api/crash", () => ({
  fetchCrashRuns: vi.fn(),
  patchCrashRun: vi.fn(),
  compareCrashRuns: vi.fn(),
}));

import { compareCrashRuns, fetchCrashRuns, patchCrashRun, type CrashRunSummary } from "../api/crash";

function run(id: number, extra: Partial<CrashRunSummary> = {}): CrashRunSummary {
  return {
    id, job_id: `j${id}`, geometry_id: 3931, name: `koşu ${id}`, created_at: "2026-10-03T12:17:05Z",
    dimension: 2, t_end_ms: 4, status: "solved", message: null, solver_ran: true,
    scalars: { rwall_force_max: 100 + id }, excluded: false, exclude_reason: null, ...extra,
  };
}

describe("CrashHistory", () => {
  beforeEach(() => {
    vi.mocked(fetchCrashRuns).mockReset();
    vi.mocked(patchCrashRun).mockReset();
    vi.mocked(compareCrashRuns).mockReset();
  });

  it("geometri koşularını listeler; dışlananı gizler, istenince gösterir", async () => {
    vi.mocked(fetchCrashRuns).mockResolvedValue([run(1), run(2, { excluded: true, status: "failed" })]);
    render(<CrashHistory geometryId={3931} />);
    expect(await screen.findByText("koşu 1")).toBeInTheDocument();
    expect(fetchCrashRuns).toHaveBeenCalledWith(3931);
    expect(screen.queryByText("koşu 2")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Dışlananları göster \(1 gizli\)/));
    expect(screen.getByText("koşu 2")).toBeInTheDocument();
    expect(screen.getByText("101.0")).toBeInTheDocument(); // duvar Fmax
  });

  it("ıraksayan koşu (Hata #1) failed kırmızı; grafik/animasyon yine açılır, diğer hata kapalı", async () => {
    vi.mocked(fetchCrashRuns).mockResolvedValue([
      run(7, { status: "failed", scalars: { diverged_at_ms: 0.014 } }),
      run(8, { status: "failed", solver_ran: false, scalars: {} }),
    ]);
    render(<CrashHistory geometryId={3931} />);
    expect(await screen.findByText("koşu 7")).toBeInTheDocument();
    expect(screen.getAllByText("failed")[0]).toHaveClass("crash-run-failed");
    expect(screen.getByRole("button", { name: "koşu 7 grafikler" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "koşu 7 deforme şekil" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "koşu 8 grafikler" })).toBeDisabled();
  });

  it("1.22f: ham kartlı koşu etiketli", async () => {
    vi.mocked(fetchCrashRuns).mockResolvedValue([run(1), run(3, { has_raw_cards: true })]);
    render(<CrashHistory geometryId={3931} />);
    expect(await screen.findByText("ham kart")).toBeInTheDocument();
    expect(screen.getAllByText("ham kart")).toHaveLength(1);
  });

  it("geometri yokken tüm geometriler; dışla PATCH gönderir", async () => {
    vi.mocked(fetchCrashRuns).mockResolvedValue([run(5)]);
    vi.mocked(patchCrashRun).mockResolvedValue(run(5, { excluded: true }));
    render(<CrashHistory geometryId={null} />);
    expect(await screen.findByText(/tüm geometriler/)).toBeInTheDocument();
    expect(fetchCrashRuns).toHaveBeenCalledWith(null);
    expect(screen.getByText(/geo 3931/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "koşu 5 dışla" }));
    await waitFor(() => expect(patchCrashRun).toHaveBeenCalledWith(5, { excluded: true }));
    await waitFor(() => expect(screen.queryByText("koşu 5")).not.toBeInTheDocument());
  });

  it("seçilen koşuları karşılaştırır: eğri seçimi + skaler tablosu", async () => {
    vi.mocked(fetchCrashRuns).mockResolvedValue([run(1), run(2)]);
    vi.mocked(compareCrashRuns).mockResolvedValue([
      { ...run(1, { scalars: { rwall_force_max: 122.3, section_1_force_max: 120 } }),
        curves: { time: [0, 0.02, 0.04], rwall_force: [0, 122.3, 0], section_1_force: [0, 120, 0] } },
      { ...run(2, { scalars: { rwall_force_max: 130.9 } }),
        curves: { time: [0, 0.002, 0.004, 0.006], rwall_force: [0, 130.9, 50, 0] } },
    ]);
    render(<CrashHistory geometryId={3931} />);
    fireEvent.click(await screen.findByLabelText("koşu 1 seç"));
    fireEvent.click(screen.getByLabelText("koşu 2 seç"));
    fireEvent.click(screen.getByRole("button", { name: "Karşılaştır (2/6)" }));
    await waitFor(() => expect(compareCrashRuns).toHaveBeenCalledWith([1, 2]));
    const box = await screen.findByTestId("crash-compare");
    expect(within(box).getByRole("img", { name: "Kuvvet–zaman grafiği" })).toBeInTheDocument();
    expect(within(box).getByLabelText("Karşılaştırma eğrisi")).toHaveValue("rwall_force");
    const table = within(box).getByRole("table");
    expect(table).toHaveTextContent("Duvar Fmax (kN)");
    expect(table).toHaveTextContent("130.9");
    expect(table).toHaveTextContent("Kesit 1 Fmax (kN)");
    // yalnız koşu 1'de olan eğri seçilince tek seri
    fireEvent.change(within(box).getByLabelText("Karşılaştırma eğrisi"), { target: { value: "section_1_force" } });
    expect(box.querySelectorAll("polyline")).toHaveLength(1);
    // zaman üst sınırı yalnız görünümü kırpar: t ≤ 0.02 → iki nokta
    fireEvent.change(within(box).getByLabelText("Grafik zaman üst sınırı"), { target: { value: "0.02" } });
    expect(box.querySelector("polyline")?.getAttribute("points")?.split(" ")).toHaveLength(2);
  });

  it("11.4: onAnimate verilince deforme şekil App'e bildirilir, yan panelde açılmaz", async () => {
    vi.mocked(fetchCrashRuns).mockResolvedValue([run(7)]);
    const onAnimate = vi.fn();
    const { rerender } = render(<CrashHistory geometryId={3931} onAnimate={onAnimate} activeAnimId={null} />);
    const btn = await screen.findByLabelText("koşu 7 deforme şekil");
    fireEvent.click(btn);
    expect(onAnimate).toHaveBeenCalledWith({ id: 7, title: "#7 koşu 7" });
    expect(screen.queryByTestId("crash-anim")).not.toBeInTheDocument();
    rerender(<CrashHistory geometryId={3931} onAnimate={onAnimate} activeAnimId={7} />);
    expect(screen.getByLabelText("koşu 7 deforme şekil")).toHaveTextContent("■");
    fireEvent.click(screen.getByLabelText("koşu 7 deforme şekil"));
    expect(onAnimate).toHaveBeenLastCalledWith(null);
  });
});
