import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CrashLiveProgress, { elapsedText } from "./CrashLiveProgress";

describe("1.23 D3 — canlı koşu ilerlemesi", () => {
  it("adım, t / t_end, Δt, en küçük Δt ve yüzde", () => {
    const { rerender } = render(<CrashLiveProgress cycle={100} timeMs={0.054} dtMs={5.4e-4} tEndMs={4} percent={1.35} />);
    const box = screen.getByTestId("crash-live");
    expect(box).toHaveTextContent("Adım100");
    expect(box).toHaveTextContent("t0.054 / 4 ms");
    expect(box).toHaveTextContent("Δt5.400e-4 ms");
    expect(box).toHaveTextContent("İlerleme%1.4");
    // Δt düşer → en küçük güncellenir; yükselince en küçük kalır
    rerender(<CrashLiveProgress cycle={200} timeMs={0.108} dtMs={5.2e-4} tEndMs={4} percent={2.7} />);
    rerender(<CrashLiveProgress cycle={300} timeMs={0.16} dtMs={5.3e-4} tEndMs={4} percent={4} />);
    expect(box).toHaveTextContent("Δt5.300e-4 ms");
    expect(box).toHaveTextContent("Δt en küçük5.200e-4 ms");
  });

  it("Δt yoksa (eski backend) '—'", () => {
    render(<CrashLiveProgress cycle={1} timeMs={0} dtMs={null} tEndMs={null} percent={0} />);
    expect(screen.getByTestId("crash-live")).toHaveTextContent("Δt—");
  });

  it("geçen süre metni", () => {
    expect(elapsedText(7.9)).toBe("7 s");
    expect(elapsedText(125)).toBe("2 dk 05 s");
  });

  it("DM/M ve Radioss'un geçen / kalan süresi", () => {
    render(
      <CrashLiveProgress cycle={37000} timeMs={19.98} dtMs={5.3986e-4} tEndMs={20} percent={99.9} massAddedRel={0} elapsedS={15.57} remainingS={0.02} />,
    );
    const box = screen.getByTestId("crash-live");
    expect(box).toHaveTextContent("Adım37000");
    expect(box).toHaveTextContent("DM/M0");
    expect(box).toHaveTextContent("Geçen15 s");
    expect(box).toHaveTextContent("Kalan (Radioss)0 s");
  });
});
