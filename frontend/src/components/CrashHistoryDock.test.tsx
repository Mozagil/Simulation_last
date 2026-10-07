import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./CrashHistory", () => ({ default: () => <div data-testid="crash-history-inner" /> }));
vi.mock("./CrashCatalog", () => ({ default: () => <div data-testid="catalog" /> }));
vi.mock("./CrashScenarioCard", () => ({
  default: ({ onGeometry }: { onGeometry: (id: number, n: string) => void }) => (
    <button type="button" onClick={() => onGeometry(42, "x.step")}>
      senaryo
    </button>
  ),
}));
vi.mock("./CrashSchematic", () => ({ default: () => null }));

import CrashHistoryDock from "./CrashHistoryDock";
import CrashNewCaseDialog from "./CrashNewCaseDialog";

describe("Crash geçmişi dock / yeni vaka (tasarım adım 3)", () => {
  it("dock kapalı başlar, açılınca geçmişi gösterir", () => {
    render(<CrashHistoryDock geometryId={1} refreshKey="" activeAnimId={null} onAnimate={() => undefined} />);
    expect(screen.queryByTestId("crash-history-inner")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Crash geçmişi/ }));
    expect(screen.getByTestId("crash-history-inner")).toBeInTheDocument();
  });

  it("açık dock alçak başlar, üst kenardan sürüklenip büyür ve yükseklik hatırlanır", () => {
    window.localStorage.removeItem("crashHistoryDockH");
    render(<CrashHistoryDock geometryId={1} refreshKey="" activeAnimId={null} onAnimate={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: /Crash geçmişi/ }));
    const dock = screen.getByTestId("crash-history-dock");
    expect(dock.style.height).toBe("200px");
    fireEvent.mouseDown(screen.getByRole("separator"), { clientY: 500 });
    fireEvent.mouseMove(window, { clientY: 440 });
    fireEvent.mouseUp(window);
    expect(dock.style.height).toBe("260px");
    expect(window.localStorage.getItem("crashHistoryDockH")).toBe("260");
  });

  it("yeni vaka penceresi: katalog + senaryo; geometri bildirilir, dışa tık kapatır", () => {
    const onGeometry = vi.fn();
    const onClose = vi.fn();
    render(<CrashNewCaseDialog onClose={onClose} onGeometry={onGeometry} onDone={() => undefined} />);
    expect(screen.getByRole("dialog", { name: "Yeni crash vakası" })).toBeInTheDocument();
    expect(screen.getByTestId("catalog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "senaryo" }));
    expect(onGeometry).toHaveBeenCalledWith(42, "x.step");
    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));
    expect(onClose).toHaveBeenCalled();
  });
});
