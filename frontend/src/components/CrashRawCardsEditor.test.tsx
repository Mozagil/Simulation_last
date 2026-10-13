import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashRawCardsEditor, { RawCardsOpenRow } from "./CrashRawCardsEditor";

function Harness({ initial = "", picks = [] as number[], onClose = () => {} }) {
  const [v, setV] = useState(initial);
  return (
    <>
      <CrashRawCardsEditor value={v} onChange={setV} onClose={onClose} nodePicks={picks} />
      <output data-testid="value">{JSON.stringify(v)}</output>
    </>
  );
}

const area = () => screen.getByLabelText("Ham kart metni") as HTMLTextAreaElement;
const value = () => JSON.parse(screen.getByTestId("value").textContent ?? '""');

describe("CrashRawCardsEditor", () => {
  it("yazılan metin aynen tutulur, satır no ve konum gösterilir", () => {
    render(<Harness />);
    fireEvent.change(area(), { target: { value: "/BCS/900001\nham" } });
    expect(value()).toBe("/BCS/900001\nham");
    expect(screen.getByText("2")).toBeInTheDocument(); // satır no oluğu
    expect(screen.getByTestId("raw-cards-pos")).toHaveTextContent("Satır");
  });

  it("Tab sonraki 10'luk alana boşlukla atlar", () => {
    render(<Harness initial="abc" />);
    const el = area();
    el.setSelectionRange(3, 3);
    fireEvent.keyDown(el, { key: "Tab" });
    expect(value()).toBe("abc" + " ".repeat(7));
  });

  it("seçili düğümler imlece 10'luk alanlarla eklenir", () => {
    render(<Harness initial="/GRNOD/NODE/900001" picks={[101, 102]} />);
    expect(screen.getByTestId("raw-cards-pick-count")).toHaveTextContent("2");
    const el = area();
    el.setSelectionRange(el.value.length, el.value.length);
    fireEvent.click(screen.getByRole("button", { name: "Düğüm ID'lerini imlece ekle" }));
    expect(value()).toBe("/GRNOD/NODE/900001\n       101       102\n");
  });

  it("seçim yoksa ekleme pasif; Esc ve × kapatır", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    expect(screen.getByRole("button", { name: "Düğüm ID'lerini imlece ekle" })).toBeDisabled();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("RawCardsOpenRow", () => {
  it("özet ve açma", () => {
    const onOpen = vi.fn();
    const { rerender } = render(<RawCardsOpenRow rawCards="" onOpen={onOpen} />);
    expect(screen.getByTestId("raw-cards-open")).toHaveTextContent("Ham kart yok");
    rerender(<RawCardsOpenRow rawCards={"a\nb\n"} onOpen={onOpen} />);
    expect(screen.getByTestId("raw-cards-open")).toHaveTextContent("2 satır ham kart");
    fireEvent.click(screen.getByRole("button", { name: "Ham kart editörü" }));
    expect(onOpen).toHaveBeenCalled();
  });
});
