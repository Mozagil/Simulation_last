import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { defaultOutput, outputPayload, type OutputState } from "./CrashOutputCard";
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
