import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashRawCardsEditor from "./CrashRawCardsEditor";
import {
  CrashApiError,
  postRawCardsCheck,
  postRawCardsInventory,
  type CrashSolveRequest,
  type RawCardsInventoryResponse,
} from "../api/crash";

vi.mock("../api/crash", async (orig) => {
  const mod = await orig<typeof import("../api/crash")>();
  return { ...mod, postRawCardsCheck: vi.fn(), postRawCardsInventory: vi.fn() };
});

const REQUEST = { geometry_id: 7, dimension: 3 } as CrashSolveRequest;

const inventory: RawCardsInventoryResponse = {
  user_id_min: 900000,
  nodes: { count: 120, min: 1, max: 130 },
  elements: { count: 300, min: 1500, max: 1799 },
  ids: { MAT: [1], PART: [1] },
  collisions: [{ line: 1, keyword: "/MAT/LAW1/1", namespace: "MAT", id: 1 }],
  duplicates: [],
  below_user_range: [{ line: 1, keyword: "/MAT/LAW1/1", namespace: "MAT", id: 1 }],
};

function Harness({ build = () => REQUEST as CrashSolveRequest | null }) {
  const [v, setV] = useState("/MAT/LAW1/1\nham\n");
  return <CrashRawCardsEditor value={v} onChange={setV} onClose={() => {}} buildRequest={build} />;
}

describe("CrashRawCardsEditor · Kontrol et (1.22e)", () => {
  beforeEach(() => {
    vi.mocked(postRawCardsInventory).mockReset().mockResolvedValue(inventory);
    vi.mocked(postRawCardsCheck)
      .mockReset()
      .mockResolvedValue({
        exit_code: 1,
        errors: [{ kind: "error", id: 79, lines: ["ERROR ID :           79", "** ERROR : DUPLICATE ID"] }],
        warnings: [],
        raw_cards_deck_line: 4200,
        console_tail: "",
      });
  });

  it("gövde + ham metinle iki uca gider; starter blokları ve çakışmalar aynen görünür", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Kontrol et" }));
    await screen.findByTestId("raw-cards-starter-summary");

    const sent = { ...REQUEST, raw_cards: "/MAT/LAW1/1\nham\n" };
    expect(postRawCardsCheck).toHaveBeenCalledWith(sent);
    expect(postRawCardsInventory).toHaveBeenCalledWith(sent);
    expect(screen.getByTestId("raw-cards-starter-summary")).toHaveTextContent(
      "Çıkış kodu 1 · 1 hata · 0 uyarı · ham kartlar deck'te 4200. satırdan",
    );
    expect(screen.getByText(/DUPLICATE ID/)).toBeInTheDocument();
    const list = screen.getByTestId("raw-cards-collisions");
    expect(list).toHaveTextContent("üretilen deck'te de var");
    expect(list).toHaveTextContent("kullanıcı aralığının (≥ 900.000) altında");
    expect(screen.getByTestId("raw-cards-inventory")).toHaveTextContent("120 düğüm (1–130), 300 eleman (1500–1799)");
  });

  it("metin değişince sonuç eski işaretlenir", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Kontrol et" }));
    await screen.findByTestId("raw-cards-starter-summary");
    fireEvent.change(screen.getByLabelText("Ham kart metni"), { target: { value: "/MAT/LAW1/900001\nham\n" } });
    expect(screen.getByText(/sonuç eski metne ait/)).toBeInTheDocument();
  });

  it("starter yoksa (503) mesaj; envanter yine gösterilir", async () => {
    vi.mocked(postRawCardsCheck).mockRejectedValue(new CrashApiError("OpenRadioss starter bulunamadı"));
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Kontrol et" }));
    await screen.findByText("OpenRadioss starter bulunamadı");
    expect(screen.getByTestId("raw-cards-inventory")).toBeInTheDocument();
  });

  it("kurulum yoksa istek atılmaz, neden yazılır", async () => {
    render(<Harness build={() => null} />);
    fireEvent.click(screen.getByRole("button", { name: "Kontrol et" }));
    await waitFor(() => expect(screen.getByTestId("raw-cards-result")).toHaveTextContent("4 · Crash kurulumu"));
    expect(postRawCardsCheck).not.toHaveBeenCalled();
  });
});
