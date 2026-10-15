import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./CrashCompareAnim", () => ({ default: () => <div data-testid="compare-anim" /> }));

import type { CrashRunCompared } from "../api/crash";
import CrashComparePage, { extraScalarRow } from "./CrashComparePage";

function cmp(id: number, extra: Partial<CrashRunCompared> = {}): CrashRunCompared {
  return {
    id, job_id: `j${id}`, geometry_id: 3931, name: null, created_at: "2026-10-15T07:00:00Z",
    dimension: 2, t_end_ms: 4, status: "solved", message: null, solver_ran: true,
    scalars: {}, excluded: false, exclude_reason: null, curves: { time: [0, 1], rwall_force: [0, id] }, ...extra,
  } as CrashRunCompared;
}

describe("CrashComparePage — 1.25d skaler tablosu", () => {
  it("okunur ad + ayrı birim sütunu + koşu başlıkları; oranlar % olarak", () => {
    const runs = [
      cmp(321, {
        name: "kizak 100 kg",
        scalars: { rwall_force_max: 122.34, energy_balance_rel: 0.0123, elements_deleted: 183, contact_2_force_max: 5.5 },
      }),
      cmp(325, { t_end_ms: 8, scalars: { rwall_force_max: 130.9, energy_balance_rel: 0.004, timestep_min: 5.393e-4 } }),
    ];
    render(<CrashComparePage runs={runs} onClose={() => {}} />);
    const table = screen.getByRole("table", { name: "Skaler karşılaştırma" });

    const head = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(head[0]).toBe("Büyüklük");
    expect(head[1]).toBe("Birim");
    expect(head[2]).toBe("#321kizak 100 kggeo 3931 · 4 ms");
    expect(head[3]).toBe("#325geo 3931 · 8 ms");

    const cells = (label: string) =>
      within(within(table).getByRole("rowheader", { name: label }).closest("tr")!)
        .getAllByRole("cell")
        .map((c) => c.textContent);
    expect(cells("Duvar kuvveti, tepe")).toEqual(["kN", "122.3", "130.9"]);
    expect(cells("Enerji dengesi |ΔE| / E")).toEqual(["%", "1.23", "0.40"]);
    expect(cells("Silinen eleman")).toEqual(["adet", "183", "—"]);
    expect(cells("En küçük zaman adımı Δt")).toEqual(["ms", "—", "0.0005393"]);
    expect(cells("Temas 2 kuvveti, tepe")).toEqual(["kN", "5.500", "—"]);
    // hiçbir koşuda olmayan satır gösterilmez
    expect(within(table).queryByRole("rowheader", { name: "Kinetik enerji, son" })).not.toBeInTheDocument();
  });

  it("kesit / temas satır adı; diğer anahtarlar ek satır değil", () => {
    expect(extraScalarRow("section_10_force_max")).toEqual({ key: "section_10_force_max", label: "Kesit 10 kuvveti, tepe", unit: "kN" });
    expect(extraScalarRow("contact_1_impulse_final")).toBeNull();
  });
});
