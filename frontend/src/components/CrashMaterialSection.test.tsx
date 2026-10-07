import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import CrashMaterialSection, { matCardSummary } from "./CrashMaterialSection";
import { defaultMatCard, type MatCardState } from "./CrashMaterialCard";
import CrashPanel from "./CrashPanel";

function Harness() {
  const [m, setM] = useState<MatCardState>(defaultMatCard());
  const [p, setP] = useState<Record<number, MatCardState>>({});
  return (
    <>
      <CrashMaterialSection partIds={[0, 1]} matCard={m} setMatCard={setM} partCards={p} setPartCards={setP} />
      <span data-testid="sum">{matCardSummary(m)}</span>
    </>
  );
}

describe("CrashMaterialSection (3 · Material)", () => {
  it("LAW ve kopma açıklamaları; özet seçimi izler", () => {
    render(<Harness />);
    expect(screen.getByTestId("crash-law-hint")).toHaveTextContent("Elastik");
    expect(screen.getByTestId("crash-fail-intro")).toHaveTextContent("Kapalıyken malzeme ne kadar uzarsa uzasın kopmaz");
    fireEvent.click(screen.getByRole("button", { name: "LAW2 plastik" }));
    fireEvent.click(screen.getByLabelText("/FAIL/TENSSTRAIN"));
    expect(screen.getByTestId("sum")).toHaveTextContent("elasto-plastik (LAW2) · kopma: çekme gerinimi");
  });
});

describe("CrashPanel malzeme özeti", () => {
  it("malzeme App'ten gelirse kart yerine özet gösterir", () => {
    const m = { ...defaultMatCard(), law: "plastic" as const };
    render(
      <CrashPanel
        geometryId={1}
        meshDimension={3}
        material={{ matCard: m, setMatCard: () => undefined, partCards: {}, setPartCards: () => undefined }}
      />,
    );
    expect(screen.getByTestId("crash-mat-summary")).toHaveTextContent("elasto-plastik (LAW2) · kopma kapalı");
    expect(screen.queryByTestId("crash-mat-global")).not.toBeInTheDocument();
  });
});
