import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api/crash", () => ({
  postDeckPreview: vi.fn(() =>
    Promise.resolve({
      starter: "#RADIOSS\n/BEGIN\nrun\n/NODE\n1 0 0 0\n2 1 0 0\n/MAT/LAW2/1\nsteel\n/END",
      engine: "/RUN/crash/1\n4.0\n/TFILE\n0.01",
      starter_outline: [
        { card: "/BEGIN", line: 2, lines: 2 },
        { card: "/NODE", line: 4, lines: 3 },
        { card: "/MAT/LAW2/1", line: 7, lines: 2 },
        { card: "/END", line: 9, lines: 1 },
      ],
      engine_outline: [
        { card: "/RUN/crash/1", line: 1, lines: 2 },
        { card: "/TFILE", line: 3, lines: 2 },
      ],
    }),
  ),
}));

import { postDeckPreview } from "../api/crash";
import CrashDeckViewer, { cardBlock, filterCards } from "./CrashDeckViewer";

describe("1.23 D1 — üretilen deck görüntüleyici", () => {
  it("panel isteğiyle deck üretir; kart listesi, seçili kartın bloğu satır no'lu; arama; engine sekmesi", async () => {
    const req = { geometry_id: 1, raw_cards: "/FUNCT/900001" } as never;
    render(<CrashDeckViewer request={req} onClose={() => undefined} />);
    expect(postDeckPreview).toHaveBeenCalledWith(req);
    expect(await screen.findByTestId("crash-deck-stats")).toHaveTextContent("9 satır · 4 kart");
    fireEvent.click(screen.getByRole("button", { name: /\/MAT\/LAW2\/1/ }));
    expect(screen.getByTestId("crash-deck-text")).toHaveTextContent("7/MAT/LAW2/1 8steel");
    fireEvent.change(screen.getByLabelText("Kart ara"), { target: { value: "node" } });
    expect(within(screen.getByRole("list", { name: "Kartlar" })).getAllByRole("button")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /^Engine · _0001/ }));
    await waitFor(() => expect(screen.getByTestId("crash-deck-stats")).toHaveTextContent("4 satır · 2 kart"));
  });

  it("filterCards / cardBlock: arama büyük-küçük harf duyarsız; uzun blok kesilir", () => {
    const cards = [{ card: "/RWALL/PLANE/1", line: 1, lines: 3 }, { card: "/NODE", line: 4, lines: 2 }];
    expect(filterCards(cards, "rwall").map((c) => c.card)).toEqual(["/RWALL/PLANE/1"]);
    expect(filterCards(cards, " ")).toHaveLength(2);
    const text = Array.from({ length: 10 }, (_, i) => `l${i + 1}`).join("\n");
    expect(cardBlock(text, { card: "x", line: 2, lines: 6 }, 4)).toEqual({ lines: ["l2", "l3", "l4", "l5"], cut: 2 });
  });
});
