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
      useEffect(() => onTimes?.(runId === 1 ? [0, 2, 4] : runId === 3 ? [0, 6, 12] : [0, 5, 10]), [runId]); // eslint-disable-line
      useEffect(
        () => onScalar?.(scalarOf[runId] ?? "eps", { location: "face", min: 0, max: runId === 1 ? 0.2 : runId === 3 ? 0.9 : 0.5 }),
        [runId], // eslint-disable-line
      );
      return (
        <div data-testid={`viewer-${runId}`}>{`t=${syncTime} range=${colorRange ? colorRange.join("..") : "own"} cam=${linkCamera}`}</div>
      );
    },
  };
});

import CrashCompareAnim, { commonRange, gridColumns, timeSpan } from "./CrashCompareAnim";
import { CameraLink } from "./CrashAnimationViewer";

const scalarOf: Record<number, string> = {};

describe("CrashCompareAnim", () => {
  it("timeSpan: iki koşunun zaman birleşimi", () => {
    expect(timeSpan([0, 2, 4], [0, 5, 10])).toEqual([0, 10]);
    expect(timeSpan([0, 2], [0, 5], [1, 12])).toEqual([0, 12]);
    expect(timeSpan([0, 4], null)).toEqual([0, 4]);
    expect(timeSpan(null, null)).toBeNull();
  });

  it("iki görüntüleyiciye aynı zamanı verir; kaydırıcı ortak aralıkta (0 … en uzun t)", () => {
    const onClose = vi.fn();
    render(<CrashCompareAnim runs={[{ id: 1, title: "#1" }, { id: 2, title: "#2" }]} onClose={onClose} />);
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
    expect(commonRange([{ scalar: "eps", meta: m(0, 0.2) }, { scalar: "eps", meta: m(0.01, 0.5) }])).toEqual([0, 0.5]);
    expect(commonRange([{ scalar: "eps", meta: m(0, 0.2) }, { scalar: "eps", meta: m(0.01, 0.5) }, { scalar: "eps", meta: m(-1, 0.1) }])).toEqual([-1, 0.5]);
    expect(commonRange([{ scalar: "eps", meta: m(0, 0.2) }, { scalar: "disp_x", meta: m(0, 9) }])).toBeNull();
    expect(commonRange([null, { scalar: "eps", meta: m(0, 1) }])).toBeNull();
    expect(commonRange([{ scalar: "eps", meta: m(0, 1) }])).toBeNull();
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
    render(<CrashCompareAnim runs={[{ id: 1, title: "#1" }, { id: 2, title: "#2" }]} onClose={() => undefined} />);
    expect(screen.getByTestId("viewer-1")).toHaveTextContent("range=own cam=false");
    fireEvent.click(screen.getByRole("button", { name: "Ortak renk ölçeği" }));
    expect(screen.getByTestId("viewer-1")).toHaveTextContent("range=0..0.5");
    expect(screen.getByTestId("viewer-2")).toHaveTextContent("range=0..0.5");
    expect(screen.getByTestId("crash-compare-scale-note")).toHaveTextContent("Ortak ölçek 0 … 0.5");
    fireEvent.click(screen.getByRole("button", { name: "Kamera eşle" }));
    expect(screen.getByTestId("viewer-2")).toHaveTextContent("cam=true");
  });

  it("1.25b gridColumns: 2 → 2, 3 → 3, 4 → 2×2, 5–6 → 3", () => {
    expect([2, 3, 4, 5, 6].map(gridColumns)).toEqual([2, 3, 2, 3, 3]);
  });

  it("1.25b: 3 koşu ızgarada; ortak zaman / ölçek hepsine; Büyük pencere ESC ile kapanır, sayfa açık kalır", () => {
    scalarOf[1] = "eps";
    scalarOf[2] = "eps";
    scalarOf[3] = "eps";
    const pageEsc = vi.fn();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && pageEsc();
    render(<CrashCompareAnim runs={[1, 2, 3].map((id) => ({ id, title: `#${id}` }))} />);
    window.addEventListener("keydown", onKey); // sayfanın ESC dinleyicisi — büyük pencereden önce bağlı
    expect(screen.getByTestId("crash-compare-anim-grid").style.getPropertyValue("--cmp-cols")).toBe("3");
    expect(screen.getByLabelText("Ortak zaman (ms)")).toHaveAttribute("max", "12");
    fireEvent.change(screen.getByLabelText("Ortak zaman (ms)"), { target: { value: "11" } });
    for (const id of [1, 2, 3]) expect(screen.getByTestId(`viewer-${id}`)).toHaveTextContent("t=11");
    fireEvent.click(screen.getByRole("button", { name: "Ortak renk ölçeği" }));
    expect(screen.getByTestId("viewer-3")).toHaveTextContent("range=0..0.9");
    const big = screen.getByRole("button", { name: "Büyük pencere" });
    fireEvent.click(big);
    expect(screen.getByTestId("crash-compare-anim")).toHaveClass("crash-compare-anim-max");
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.getByTestId("crash-compare-anim")).not.toHaveClass("crash-compare-anim-max");
    expect(pageEsc).not.toHaveBeenCalled();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(pageEsc).toHaveBeenCalledTimes(1);
    window.removeEventListener("keydown", onKey);
  });

  it("C5b: pencerelerde farklı skaler → ortak ölçek uygulanmaz, not yazar", () => {
    scalarOf[1] = "eps";
    scalarOf[2] = "disp_x";
    render(<CrashCompareAnim runs={[{ id: 1, title: "#1" }, { id: 2, title: "#2" }]} onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Ortak renk ölçeği" }));
    expect(screen.getByTestId("viewer-1")).toHaveTextContent("range=own");
    expect(screen.getByTestId("crash-compare-scale-note")).toHaveTextContent("farklı skaler");
  });
});
