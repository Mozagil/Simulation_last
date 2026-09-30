import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DoeResultRow, DoeResults, DoeStudyInfo } from "../api/doe";
import DoeDistribution, { topOutliers } from "./DoeDistribution";

const STUDY: DoeStudyInfo = {
  id: 14,
  name: "kalite seti",
  template_id: "cantilever_beam",
  seed: 2026,
  status: "completed",
  message: null,
  n_cases: 4,
  counts: {},
  cases: [],
};

function row(index: number, u: number, vm: number, du: number | null, dvm: number | null, quality = "ok"): DoeResultRow {
  return {
    index,
    run_id: 100 + index,
    geometry_id: 1,
    status: "solved",
    quality,
    element_size: 8,
    material_id: 3,
    scenario: "varsayilan",
    params: { length: 500 + index * 10, thickness: 10 },
    scalars: { max_displacement: u, max_von_mises: vm },
    dev_displacement_pct: du,
    dev_von_mises_pct: dvm,
    message: null,
  };
}

const RESULTS: DoeResults = {
  study_id: 14,
  template_id: "cantilever_beam",
  param_columns: ["length", "thickness"],
  constant_params: {},
  scalar_columns: { max_displacement: "u", max_von_mises: "vm" },
  rows: [
    row(0, 1.0, 100, 0.5, 1.0),
    row(1, 1.2, 120, -0.8, 11.4, "analytic_warn"),
    row(2, 1.4, 140, 0.2, -7.2, "analytic_warn"),
    row(3, 1.6, 160, 0.1, 4.9),
  ],
  stats: {},
};

describe("DoeDistribution", () => {
  it("kalite şeridi, 4 strip, en çok sapan örnekler ve tablo anahtarı", () => {
    const onOpenRun = vi.fn();
    const onToggle = vi.fn();
    render(
      <DoeDistribution
        study={STUDY}
        quality={{ study_id: 14, n_cases: 4, n_ok: 2, counts: { ok: 2, analytic_warn: 2 }, flagged: {} }}
        results={RESULTS}
        loading={false}
        tableOpen={false}
        onToggleTable={onToggle}
        onOpenRun={onOpenRun}
      />,
    );
    expect(screen.getByText(/Çalışma #14 · kalite seti · 4 örnek/)).toBeInTheDocument();
    expect(screen.getByText("tamamlandı")).toBeInTheDocument();
    const strip = screen.getByTestId("quality-strip");
    expect(within(strip).getByText("ok 2")).toBeInTheDocument();
    expect(within(strip).getByText("analytic_warn 2")).toBeInTheDocument();
    // 4 strip: ortalama ve aralık
    expect(within(screen.getByTestId("strip-u")).getByText("1.3")).toBeInTheDocument();
    expect(within(screen.getByTestId("strip-u")).getByText("1 – 1.6")).toBeInTheDocument();
    expect(within(screen.getByTestId("strip-dvm")).getByText("+2.5%")).toBeInTheDocument();
    // sapanlar |Δvm|'ye göre sıralı
    const outliers = screen.getAllByRole("button", { name: /Run'ı aç/ });
    expect(outliers.map((b) => b.textContent)).toEqual([
      expect.stringContaining("#1"),
      expect.stringContaining("#2"),
      expect.stringContaining("#3"),
      expect.stringContaining("#0"),
    ]);
    expect(outliers[0]).toHaveTextContent("+11.4%");
    fireEvent.click(outliers[0]);
    expect(onOpenRun).toHaveBeenCalledWith(101);
    fireEvent.click(screen.getByRole("button", { name: "Tabloyu aç" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("tablo açıkken sonuç tablosunu gösterir; sonuç yokken düğme pasif", () => {
    const { rerender } = render(
      <DoeDistribution study={STUDY} quality={null} results={null} loading tableOpen={false} onToggleTable={() => undefined} />,
    );
    expect(screen.getByRole("button", { name: "Tabloyu aç" })).toBeDisabled();
    expect(screen.getByText(/yükleniyor/)).toBeInTheDocument();
    rerender(
      <DoeDistribution study={STUDY} quality={null} results={RESULTS} loading={false} tableOpen onToggleTable={() => undefined} />,
    );
    expect(screen.getByRole("button", { name: "Tabloyu kapat" })).toBeEnabled();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("topOutliers VM sapması yoksa deplasman sapmasına düşer ve boşları atlar", () => {
    const rows = [row(0, 1, 1, 3.0, null), row(1, 1, 1, null, null), row(2, 1, 1, -9.0, null)];
    expect(topOutliers(rows).map((o) => [o.row.index, o.dev])).toEqual([
      [2, -9.0],
      [0, 3.0],
    ]);
  });
});
