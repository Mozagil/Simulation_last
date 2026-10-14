import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// jsdom'da WebGL yok: görüntüleyici sahte — aldığı ortak zamanı yazar, kare zamanlarını bildirir.
vi.mock("./CrashAnimationViewer", async (orig) => {
  const real = await orig<typeof import("./CrashAnimationViewer")>();
  const { useEffect } = await import("react");
  return {
    ...real,
    default: ({ runId, syncTime, onTimes }: { runId: number; syncTime?: number; onTimes?: (t: number[]) => void }) => {
      useEffect(() => onTimes?.(runId === 1 ? [0, 2, 4] : [0, 5, 10]), [runId, onTimes]);
      return <div data-testid={`viewer-${runId}`}>{`t=${syncTime}`}</div>;
    },
  };
});

import CrashCompareAnim, { timeSpan } from "./CrashCompareAnim";

describe("CrashCompareAnim", () => {
  it("timeSpan: iki koşunun zaman birleşimi", () => {
    expect(timeSpan([0, 2, 4], [0, 5, 10])).toEqual([0, 10]);
    expect(timeSpan([0, 4], null)).toEqual([0, 4]);
    expect(timeSpan(null, null)).toBeNull();
  });

  it("iki görüntüleyiciye aynı zamanı verir; kaydırıcı ortak aralıkta (0 … en uzun t)", () => {
    const onClose = vi.fn();
    render(<CrashCompareAnim a={{ id: 1, title: "#1" }} b={{ id: 2, title: "#2" }} onClose={onClose} />);
    const slider = screen.getByLabelText("Ortak zaman (ms)");
    expect(slider).toHaveAttribute("max", "10");
    fireEvent.change(slider, { target: { value: "7.5" } });
    expect(screen.getByTestId("viewer-1")).toHaveTextContent("t=7.5");
    expect(screen.getByTestId("viewer-2")).toHaveTextContent("t=7.5");
    expect(screen.getByTestId("crash-compare-anim-time")).toHaveTextContent("t = 7.500 ms / 10.000 ms");
    fireEvent.click(screen.getByLabelText("Karşılaştırmayı kapat"));
    expect(onClose).toHaveBeenCalled();
  });
});
