import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// jsdom'da WebGL yok: görüntüleyici sahte — aldığı ortak zamanı yazar, kare zamanlarını bildirir.
vi.mock("./CrashAnimationViewer", async (orig) => {
  const real = await orig<typeof import("./CrashAnimationViewer")>();
  const { useEffect } = await import("react");
  return {
    ...real,
    default: ({
      runId,
      syncTime,
      onTimes,
      onScalar,
      colorRange,
      linkCamera,
    }: {
      runId: number;
      syncTime?: number;
      onTimes?: (t: number[]) => void;
      onScalar?: (s: string, m: { location: "node" | "face"; min: number; max: number }) => void;
      colorRange?: [number, number] | null;
      linkCamera?: boolean;
    }) => {
      useEffect(() => onTimes?.(runId === 1 ? [0, 2, 4] : [0, 5, 10]), [runId]); // eslint-disable-line
      useEffect(
        () => onScalar?.(scalarOf[runId] ?? "eps", { location: "face", min: 0, max: runId === 1 ? 0.2 : 0.5 }),
        [runId], // eslint-disable-line
      );
      return (
        <div data-testid={`viewer-${runId}`}>{`t=${syncTime} range=${colorRange ? colorRange.join("..") : "own"} cam=${linkCamera}`}</div>
      );
    },
  };
});

import CrashCompareAnim, { commonRange, timeSpan } from "./CrashCompareAnim";
import { CameraLink } from "./CrashAnimationViewer";

const scalarOf: Record<number, string> = {};

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

  it("C5b commonRange: aynı skalerde min–max birleşimi, farklıysa null", () => {
    const m = (min: number, max: number) => ({ min, max });
    expect(commonRange({ scalar: "eps", meta: m(0, 0.2) }, { scalar: "eps", meta: m(0.01, 0.5) })).toEqual([0, 0.5]);
    expect(commonRange({ scalar: "eps", meta: m(0, 0.2) }, { scalar: "disp_x", meta: m(0, 9) })).toBeNull();
    expect(commonRange(null, { scalar: "eps", meta: m(0, 1) })).toBeNull();
  });

  it("C5b CameraLink: poz gönderen dışındaki abonelere gider; abonelik kalkınca gitmez", () => {
    const link = new CameraLink();
    const a = {};
    const b = {};
    const got: string[] = [];
    link.subscribe(a, () => got.push("a"));
    const off = link.subscribe(b, () => got.push("b"));
    const pose = { pos: [1, 2, 3] as [number, number, number], target: [0, 0, 0] as [number, number, number], up: [0, 1, 0] as [number, number, number] };
    link.publish(a, pose);
    expect(got).toEqual(["b"]);
    off();
    link.publish(a, pose);
    expect(got).toEqual(["b"]);
  });

  it("C5b: ortak ölçek ve kamera eşle varsayılan kapalı; açılınca iki pencereye aynı aralık", () => {
    scalarOf[1] = "eps";
    scalarOf[2] = "eps";
    render(<CrashCompareAnim a={{ id: 1, title: "#1" }} b={{ id: 2, title: "#2" }} onClose={() => undefined} />);
    expect(screen.getByTestId("viewer-1")).toHaveTextContent("range=own cam=false");
    fireEvent.click(screen.getByRole("button", { name: "Ortak renk ölçeği" }));
    expect(screen.getByTestId("viewer-1")).toHaveTextContent("range=0..0.5");
    expect(screen.getByTestId("viewer-2")).toHaveTextContent("range=0..0.5");
    expect(screen.getByTestId("crash-compare-scale-note")).toHaveTextContent("Ortak ölçek 0 … 0.5");
    fireEvent.click(screen.getByRole("button", { name: "Kamera eşle" }));
    expect(screen.getByTestId("viewer-2")).toHaveTextContent("cam=true");
  });

  it("C5b: pencerelerde farklı skaler → ortak ölçek uygulanmaz, not yazar", () => {
    scalarOf[1] = "eps";
    scalarOf[2] = "disp_x";
    render(<CrashCompareAnim a={{ id: 1, title: "#1" }} b={{ id: 2, title: "#2" }} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ortak renk ölçeği" }));
    expect(screen.getByTestId("viewer-1")).toHaveTextContent("range=own");
    expect(screen.getByTestId("crash-compare-scale-note")).toHaveTextContent("farklı skaler");
  });
});
