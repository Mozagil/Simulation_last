import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { dampingFromRequest, defaultOutput, outputPayload, type OutputState } from "./CrashOutputCard";
import CrashSolverControlCard, { solverSummary } from "./CrashSolverControlCard";

function Harness({ onState, scalars }: { onState: (t: string, s: OutputState) => void; scalars?: Record<string, number> }) {
  const [t, setT] = useState("4");
  const [s, setS] = useState(defaultOutput);
  onState(t, s);
  return <CrashSolverControlCard tEnd={t} onTEnd={setT} value={s} onChange={setS} lastScalars={scalars} />;
}

describe("1.23 D2 — çözüm kontrolü kartı", () => {
  it("süre + zaman adımı kartı + Δt alanları tek yerde; payload eskisiyle aynı", () => {
    let t = "";
    let s = defaultOutput();
    render(<Harness onState={(a, b) => ((t = a), (s = b))} />);
    expect(screen.getByLabelText("Δt_sca")).toBeDisabled(); // tür seçilmeden kapalı
    fireEvent.change(screen.getByLabelText("Süre"), { target: { value: "20" } });
    fireEvent.click(within(screen.getByRole("group", { name: "Zaman adımı kartı" })).getByRole("button", { name: "NODA/CST/0" }));
    fireEvent.change(screen.getByLabelText("Δt_sca"), { target: { value: "0.67" } });
    fireEvent.change(screen.getByLabelText("Δt_min (ms)"), { target: { value: "0.0005" } });
    expect(t).toBe("20");
    expect(outputPayload(s).engine).toMatchObject({ dt_kind: "NODA/CST/0", dt_scale: 0.67, dt_min_ms: 0.0005 });
    expect(screen.getAllByText(/kütle ölçekleme/).length).toBeGreaterThan(0); // ipucu + açıklama
  });

  it("özet: süre + Δt kartı", () => {
    expect(solverSummary("4", { dtKind: "", dtScale: "", dtMin: "" })).toBe("4 ms · Δt: Radioss");
    expect(solverSummary("20", { dtKind: "NODA/CST/0", dtScale: "0.67", dtMin: "0.0005" })).toBe(
      "20 ms · /DT/NODA/CST/0 · Δt_sca 0.67 · Δt_min 0.0005 ms",
    );
  });

  it("son koşunun Δt_min ve eklenen kütle oranı veri olarak; adım üst sınırı süre / Δt_min", () => {
    render(<Harness onState={() => undefined} scalars={{ timestep_min: 5.396e-4, mass_added_rel: 0 }} />);
    expect(screen.getByTestId("crash-solver-last")).toHaveTextContent("Δt_min 5.396e-4 ms · eklenen kütle oranı 0");
    expect(screen.getByTestId("crash-solver-last")).toHaveTextContent(/≈ 7413 adım/);
  });
});

describe("1.24c2 — Rayleigh sönümü /DAMP", () => {
  function DampHarness({ onState, parts }: { onState: (s: OutputState) => void; parts: number[] }) {
    const [s, setS] = useState(defaultOutput);
    onState(s);
    return <CrashSolverControlCard tEnd="20" onTEnd={() => undefined} value={s} onChange={setS} partOptions={parts} />;
  }

  it("kapalı varsayılan → damping null; açınca α β kapsam pencere payload'a; özet", () => {
    let s = defaultOutput();
    render(<DampHarness onState={(x) => (s = x)} parts={[0, 1]} />);
    expect(outputPayload(s).damping).toBeNull();
    expect(screen.queryByTestId("crash-damp")).toBeNull();
    fireEvent.click(screen.getByLabelText("Sönüm ekle"));
    fireEvent.change(screen.getByLabelText("Sönüm β (rijitlik orantılı)"), { target: { value: "1e-6" } });
    fireEvent.change(screen.getByLabelText("Sönüm Bitiş (0 = koşu sonu)"), { target: { value: "15" } });
    fireEvent.click(within(screen.getByRole("group", { name: "Sönüm parçaları" })).getByRole("button", { name: "#1" }));
    expect(outputPayload(s).damping).toEqual({ alpha_per_s: 0, beta_s: 1e-6, part_ids: [1], t_start_ms: 0, t_stop_ms: 15 });
    expect(solverSummary("20", s)).toBe("20 ms · Δt: Radioss · /DAMP β 1e-6 s · #1");
  });

  it("α = β = 0 ya da ters pencere gönderilmez (backend kuralı)", () => {
    const s = { ...defaultOutput(), dampOn: true };
    expect(() => outputPayload(s)).toThrow(/α ya da β/);
    expect(() => outputPayload({ ...s, dampAlpha: "5", dampT0: "4", dampT1: "2" })).toThrow(/bitiş/);
  });

  it("tek parçada kapsam çipleri yok (tüm model)", () => {
    render(<DampHarness onState={() => undefined} parts={[0]} />);
    fireEvent.click(screen.getByLabelText("Sönüm ekle"));
    expect(screen.queryByRole("group", { name: "Sönüm parçaları" })).toBeNull();
  });

  it("kayıtlı istekten yükleme: dampingFromRequest", () => {
    expect(dampingFromRequest(null)).toEqual({ dampOn: false });
    expect(dampingFromRequest({ alpha_per_s: 200, beta_s: 0, part_ids: [0], t_start_ms: 1, t_stop_ms: 0 })).toEqual({
      dampOn: true, dampAlpha: "200", dampBeta: "0", dampParts: [0], dampT0: "1", dampT1: "0",
    });
  });
});
