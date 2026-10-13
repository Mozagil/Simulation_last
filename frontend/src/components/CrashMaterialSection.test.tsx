import { fireEvent, render, screen, within } from "@testing-library/react";
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
    // Varsayılan LAW2; LAW1 seçilince açıklama değişir.
    fireEvent.click(screen.getByRole("button", { name: "LAW1 elastik" }));
    expect(screen.getByTestId("crash-law-hint")).toHaveTextContent("Elastik");
    expect(screen.getByTestId("crash-fail-intro")).toHaveTextContent("Kapalıyken malzeme ne kadar uzarsa uzasın kopmaz");
    fireEvent.click(screen.getByRole("button", { name: "LAW2 plastik" }));
    fireEvent.click(screen.getByLabelText("/FAIL/TENSSTRAIN"));
    expect(screen.getByTestId("sum")).toHaveTextContent("elasto-plastik (LAW2) · kopma: çekme gerinimi");
  });
});

describe("CrashPanel malzeme özeti", () => {
  it("malzeme App'ten gelirse crash panelinde ne kart ne özet (açıklama 3 · Material'da)", () => {
    const m = { ...defaultMatCard(), law: "plastic" as const };
    render(
      <CrashPanel
        geometryId={1}
        meshDimension={3}
        material={{ matCard: m, setMatCard: () => undefined, partCards: {}, setPartCards: () => undefined }}
      />,
    );
    expect(screen.queryByTestId("crash-mat-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crash-mat-global")).not.toBeInTheDocument();
  });
});

function TableHarness() {
  const [mat, setMat] = useState<MatCardState>(defaultMatCard());
  const [parts, setParts] = useState<Record<number, MatCardState>>({});
  return (
    <>
      <CrashMaterialSection
        partIds={[0, 1]}
        matCard={mat}
        setMatCard={setMat}
        partCards={parts}
        setPartCards={setParts}
        hideToggle
        materialOf={(pid) => (pid === 0 ? "6061-T6" : "S235")}
      />
      <output data-testid="parts">{JSON.stringify(Object.fromEntries(Object.entries(parts).map(([k, v]) => [k, v.law])))}</output>
    </>
  );
}

describe("CrashMaterialSection · parça tablosu (1.23 A2)", () => {
  it("her parça: kütüphane malzemesi + model seçimi; LAW seçilince kendi kartı, Ortak'ta kalkar", () => {
    render(<TableHarness />);
    const row1 = screen.getByTestId("crash-mat-row-1");
    expect(within(row1).getByText("S235")).toBeInTheDocument();
    expect(screen.getByLabelText("Parça 1 modeli")).toHaveValue("common");

    fireEvent.change(screen.getByLabelText("Parça 1 modeli"), { target: { value: "elastic" } });
    expect(screen.getByTestId("parts")).toHaveTextContent('{"1":"elastic"}');
    expect(screen.getByTestId("crash-mat-part-1")).toBeInTheDocument();
    expect(screen.getByLabelText("Parça 0 modeli")).toHaveValue("common");

    fireEvent.change(screen.getByLabelText("Parça 1 modeli"), { target: { value: "common" } });
    expect(screen.getByTestId("parts")).toHaveTextContent("{}");
    expect(screen.queryByTestId("crash-mat-part-1")).not.toBeInTheDocument();
  });
});

describe("CrashMaterialSection · varsayılan LAW değişince onay (kullanıcı 2026-10-13)", () => {
  it("kendi modeli olan parça varken varsayılan LAW değişirse sorar; Evet hepsini varsayılana bağlar", () => {
    render(<TableHarness />);
    fireEvent.change(screen.getByLabelText("Parça 1 modeli"), { target: { value: "plastic" } });
    expect(screen.getByLabelText("Parça 1 modeli")).toHaveValue("plastic");
    expect(screen.getByLabelText("Parça 0 modeli")).toHaveDisplayValue("Varsayılan");

    const def = screen.getByTestId("crash-mat-global");
    fireEvent.click(within(def).getByRole("button", { name: "LAW1 elastik" }));
    const ask = screen.getByRole("alertdialog", { name: "Tüm parçalar" });
    expect(ask).toHaveTextContent("Hepsi LAW1 elastik olsun mu?");
    fireEvent.click(within(ask).getByRole("button", { name: "Evet" }));
    expect(screen.getByTestId("parts")).toHaveTextContent("{}");
    expect(screen.getByLabelText("Parça 1 modeli")).toHaveDisplayValue("Varsayılan");
  });

  it("Hayır: yalnız varsayılan değişir, parçanın kendi modeli kalır", () => {
    render(<TableHarness />);
    fireEvent.change(screen.getByLabelText("Parça 1 modeli"), { target: { value: "plastic" } });
    fireEvent.click(within(screen.getByTestId("crash-mat-global")).getByRole("button", { name: "LAW1 elastik" }));
    fireEvent.click(screen.getByRole("button", { name: "Hayır" }));
    expect(screen.getByTestId("parts")).toHaveTextContent('{"1":"plastic"}');
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
