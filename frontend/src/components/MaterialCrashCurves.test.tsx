import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Material } from "../api/materials";
import { defaultMatCard, matCardPayload } from "./CrashMaterialCard";
import MaterialCrashCurves from "./MaterialCrashCurves";

vi.mock("../api/materials", () => ({
  setMaterialCrashCurves: vi.fn((id: number, curves: unknown) =>
    Promise.resolve({ ...base, id, is_editable: true, crash_curves: curves }),
  ),
}));

import { setMaterialCrashCurves } from "../api/materials";

const base: Material = {
  id: 9, name: "Özel çelik", category: "custom", standard: null, density: 7850, youngs_modulus: 210e9,
  poisson_ratio: 0.3, yield_strength: 235e6, ultimate_strength: 360e6, elongation: null, sn_curve: null,
  source: "user_defined", is_editable: true, crash_curves: null,
};

describe("MaterialCrashCurves", () => {
  it("kullanıcı malzemesinde eğri ekler ve kaydeder (ayrıştırılmış noktalar)", async () => {
    const onSaved = vi.fn();
    render(<MaterialCrashCurves material={base} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: /Crash LAW36 eğrileri · yok/ }));
    fireEvent.click(screen.getByRole("button", { name: "+ Eğri" }));
    fireEvent.change(screen.getByLabelText("Malzeme eğri 1 noktaları"), { target: { value: "0 235\n0.2 320" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(setMaterialCrashCurves).toHaveBeenCalledWith(9, [
      { eps_dot_per_s: 0, points: [[0, 235], [0.2, 320]] },
    ]));
    expect(onSaved).toHaveBeenCalled();
    expect(await screen.findByText("1 eğri kaydedildi.")).toBeInTheDocument();
  });

  it("kütüphane malzemesi salt okunur", () => {
    render(<MaterialCrashCurves material={{ ...base, is_editable: false, source: "library",
      crash_curves: [{ eps_dot_per_s: 0, points: [[0, 235], [1, 235]] }] }} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Crash LAW36 eğrileri · 1 eğri/ }));
    expect(screen.getByText(/Kütüphane malzemesi değiştirilemez/)).toBeInTheDocument();
    expect(screen.getByLabelText("Malzeme eğri 1 noktaları")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Kaydet" })).not.toBeInTheDocument();
  });
});

describe("CrashMaterialCard — eğriler malzemeden", () => {
  it("işaretliyse tab_curves boş gider (backend malzemenin eğrisini kullanır)", () => {
    const s = { ...defaultMatCard(), law: "tabulated" as const, curvesFromMaterial: true };
    expect(matCardPayload(s).tab_curves).toEqual([]);
  });
});
