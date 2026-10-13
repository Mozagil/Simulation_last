import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Material, MaterialAssignment } from "../api/materials";
import { defaultMatCard, type MatCardState } from "./CrashMaterialCard";
import CrashMaterialStep from "./CrashMaterialStep";

const MATS = [
  { id: 1, name: "S235", category: "steel", youngs_modulus: 210e9, poisson_ratio: 0.3, density: 7850, yield_strength: 235e6, ultimate_strength: 360e6, elongation: 26 },
  { id: 2, name: "6061-T6", category: "aluminum", youngs_modulus: 68.9e9, poisson_ratio: 0.33, density: 2700, yield_strength: 276e6, ultimate_strength: 310e6, elongation: 12 },
] as unknown as Material[];

function Harness({ assignments, onAssign }: { assignments: MaterialAssignment[]; onAssign: (ids: number[]) => void }) {
  const [sel, setSel] = useState<number | null>(1);
  const [mc, setMc] = useState<MatCardState>(defaultMatCard());
  const [pc, setPc] = useState<Record<number, MatCardState>>({});
  return (
    <CrashMaterialStep
      materials={MATS}
      selectedMaterialId={sel}
      onSelectMaterial={setSel}
      partIds={[0, 1]}
      assignments={assignments}
      thicknessByPart={{ 0: 3, 1: null }}
      isShell
      busy={false}
      onAssign={onAssign}
      onCustom={() => undefined}
      matCard={mc}
      setMatCard={setMc}
      partCards={pc}
      setPartCards={setPc}
    />
  );
}

describe("CrashMaterialStep (3 · Material, BC gibi akordeon)", () => {
  it("özetler, eksik sayacı; parçaya ata seçili kütüphane malzemesini gönderir", () => {
    const onAssign = vi.fn();
    const assigned = [{ id: 9, geometry_id: 1, part_id: 0, material_id: 1, material_name: "S235", material_category: "steel" }];
    render(<Harness assignments={assigned} onAssign={onAssign} />);
    expect(screen.getByRole("button", { name: /Kütüphane malzemesi/ })).toHaveTextContent("S235 · E 210.0 GPa · σy 235 MPa");
    // #1 atanmadı + kalınlık yok → 2 eksik; 2 / 3 hazır
    expect(screen.getByRole("button", { name: /Parçalara ata/ })).toHaveTextContent("2 eksik");
    expect(screen.getByTestId("crash-mat-ready")).toHaveTextContent("2 / 3 hazır");
    fireEvent.click(screen.getByRole("button", { name: /Parçalara ata/ }));
    const row1 = screen.getByTestId("crash-mat-part-1");
    expect(row1).toHaveTextContent("atanmadı");
    expect(row1).toHaveTextContent("kalınlık yok");
    fireEvent.click(within(row1).getByRole("button", { name: "S235 ata" }));
    expect(onAssign).toHaveBeenCalledWith([1]);
    expect(within(screen.getByTestId("crash-mat-part-0")).getByRole("button", { name: "atandı" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Tüm parçalara S235 ata" }));
    expect(onAssign).toHaveBeenLastCalledWith([0, 1]);
  });

  it("davranış grubu malzeme modeli kartını içerir (varsayılan LAW2)", () => {
    render(<Harness assignments={[]} onAssign={() => undefined} />);
    expect(screen.getByRole("button", { name: /Malzeme modeli \(LAW\) ve kopma/ })).toHaveTextContent("elasto-plastik (LAW2) · kopma kapalı");
    fireEvent.click(screen.getByRole("button", { name: /Malzeme modeli \(LAW\) ve kopma/ }));
    expect(screen.getByRole("button", { name: "LAW2 plastik" })).toBeInTheDocument();
  });

  it("kütüphane grubu yalnız explicit'te kullanılan değerleri gösterir (Rm / uzama / S-N yok)", () => {
    render(<Harness assignments={[]} onAssign={() => undefined} />);
    const props = screen.getByTestId("crash-mat-props");
    expect(props).toHaveTextContent("E · elastisite modülü");
    expect(props).toHaveTextContent("LAW2 a");
    expect(props).not.toHaveTextContent("Rm");
    expect(props).not.toHaveTextContent("uzama");
  });

  it("geometri / mesh yokken atama grubu 'eksik' değil 'bekliyor'; sayaç 2 grup üzerinden", () => {
    render(
      <CrashMaterialStep
        materials={MATS}
        selectedMaterialId={1}
        onSelectMaterial={() => undefined}
        partIds={[]}
        assignments={[]}
        thicknessByPart={{}}
        isShell={false}
        hasModel={false}
        busy={false}
        onAssign={() => undefined}
        onCustom={() => undefined}
        matCard={defaultMatCard()}
        setMatCard={() => undefined}
        partCards={{}}
        setPartCards={() => undefined}
      />,
    );
    const head = screen.getByRole("button", { name: /Parçalara ata/ });
    expect(head).toHaveTextContent("bekliyor");
    expect(head).not.toHaveTextContent("eksik");
    expect(screen.getByTestId("crash-mat-ready")).toHaveTextContent("2 / 2 hazır");
    fireEvent.click(head);
    expect(screen.getByTestId("crash-mat-no-model")).toBeInTheDocument();
    expect(screen.queryByTestId("crash-mat-part-0")).toBeNull();
  });
});
