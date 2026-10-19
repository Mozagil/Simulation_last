import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CrashLiveProgress, { elapsedText, livePhase, STALE_S } from "./CrashLiveProgress";

describe("1.23 D3 — canlı koşu ilerlemesi", () => {
  afterEach(() => vi.useRealTimers());

  it("adım, t / t_end, Δt, en küçük Δt ve yüzde", () => {
    const vals = (cycle: number, time_ms: number, dt_ms: number, percent: number) => ({ cycle, time_ms, dt_ms, percent });
    const { rerender } = render(<CrashLiveProgress phase="running" values={vals(100, 0.054, 5.4e-4, 1.35)} tEndMs={4} />);
    const box = screen.getByTestId("crash-live");
    expect(box).toHaveTextContent("Adım100");
    expect(box).toHaveTextContent("t0.054 / 4 ms");
    expect(box).toHaveTextContent("Δt5.400e-4 ms");
    expect(box).toHaveTextContent("İlerleme%1.4");
    // Δt düşer → en küçük güncellenir; yükselince en küçük kalır
    rerender(<CrashLiveProgress phase="running" values={vals(200, 0.108, 5.2e-4, 2.7)} tEndMs={4} />);
    rerender(<CrashLiveProgress phase="running" values={vals(300, 0.16, 5.3e-4, 4)} tEndMs={4} />);
    expect(box).toHaveTextContent("Δt5.300e-4 ms");
    expect(box).toHaveTextContent("Δt en küçük5.200e-4 ms");
  });

  it("Δt yoksa (eski backend) '—'", () => {
    render(<CrashLiveProgress phase="running" values={{ cycle: 1, time_ms: 0, dt_ms: null, percent: 0 }} tEndMs={null} />);
    expect(screen.getByTestId("crash-live")).toHaveTextContent("Δt—");
  });

  it("geçen süre metni", () => {
    expect(elapsedText(7.9)).toBe("7 s");
    expect(elapsedText(125)).toBe("2 dk 05 s");
  });

  it("DM/M ve Radioss'un geçen / kalan süresi", () => {
    render(
      <CrashLiveProgress
        phase="running"
        values={{ cycle: 37000, time_ms: 19.98, dt_ms: 5.3986e-4, percent: 99.9, mass_added_rel: 0, elapsed_s: 15.57, remaining_s: 0.02 }}
        tEndMs={20}
      />,
    );
    const box = screen.getByTestId("crash-live");
    expect(box).toHaveTextContent("Adım37000");
    expect(box).toHaveTextContent("DM/M0");
    expect(box).toHaveTextContent("Geçen15 s");
    expect(box).toHaveTextContent("Kalan (Radioss)0 s");
  });

  it("1.25a livePhase: sürerken adım yoksa başlıyor; bitince durum", () => {
    expect(livePhase("pending", true, null)).toBe("starting");
    expect(livePhase("running", true, 12)).toBe("running");
    expect(livePhase("solved", false, 12)).toBe("finished");
    expect(livePhase("rad_only", false, null)).toBe("finished");
    expect(livePhase("failed", false, 12)).toBe("failed");
  });

  it("1.25a: başlıyor (değerler —) → koşuyor → bitti (son değerler kalır, kalan —)", () => {
    const { rerender } = render(<CrashLiveProgress phase="starting" values={null} tEndMs={4} />);
    expect(screen.getByTestId("crash-live-phase")).toHaveTextContent("Başlıyor");
    expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım—");
    const last = { cycle: 7400, time_ms: 3.99, dt_ms: 5.39e-4, percent: 99.8, remaining_s: 1 };
    rerender(<CrashLiveProgress phase="running" values={last} tEndMs={4} />);
    expect(screen.getByTestId("crash-live-phase")).toHaveTextContent("Koşuyor");
    rerender(<CrashLiveProgress phase="finished" values={last} tEndMs={4} />);
    expect(screen.getByTestId("crash-live-phase")).toHaveTextContent("Bitti · son canlı değerler");
    expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım7400");
    expect(screen.getByTestId("crash-live")).toHaveTextContent("Kalan (Radioss)—");
    rerender(<CrashLiveProgress phase="failed" values={last} tEndMs={4} />);
    expect(screen.getByTestId("crash-live-phase")).toHaveTextContent("Başarısız");
  });

  it("1.25a: STALE_S boyunca yeni değer yoksa son güncellemenin yaşı; yeni değerde kalkar", () => {
    vi.useFakeTimers();
    const v = (cycle: number) => ({ cycle, time_ms: cycle / 1000, dt_ms: 1e-3, percent: 10 });
    const { rerender } = render(<CrashLiveProgress phase="running" values={v(100)} tEndMs={4} />);
    expect(screen.queryByTestId("crash-live-stale")).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime((STALE_S + 2) * 1000));
    expect(screen.getByTestId("crash-live-stale")).toHaveTextContent(/son güncelleme 3\d s önce/);
    rerender(<CrashLiveProgress phase="running" values={v(200)} tEndMs={4} />);
    expect(screen.queryByTestId("crash-live-stale")).not.toBeInTheDocument();
  });
});
