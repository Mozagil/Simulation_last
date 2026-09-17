import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import DoeResultsTable from "./DoeResultsTable";
import type { DoeResults } from "../api/doe";

const RESULTS: DoeResults = {
  study_id: 1,
  template_id: "cantilever_beam",
  param_columns: ["length", "width"],
  constant_params: { thickness: 10 },
  scalar_columns: { max_displacement: "Deplasman maks [mm]", max_von_mises: "VM maks [MPa]" },
  rows: [
    {
      index: 0, run_id: 11, geometry_id: 101, status: "solved", quality: "ok",
      element_size: 8, material_id: 1, scenario: "tip_-y",
      params: { length: 500, width: 50 },
      scalars: { max_displacement: 23.9, max_von_mises: 330 },
      dev_displacement_pct: 0.5, dev_von_mises_pct: 10.2, message: null,
    },
    {
      index: 1, run_id: 12, geometry_id: 102, status: "solved", quality: "analytic_warn",
      element_size: 12, material_id: 1, scenario: "tip_-y",
      params: { length: 700, width: 40 },
      scalars: { max_displacement: 61.2, max_von_mises: 520 },
      dev_displacement_pct: -18.4, dev_von_mises_pct: 9.0, message: "sapma",
    },
    {
      index: 2, run_id: null, geometry_id: 103, status: "inp_only", quality: "inp_only",
      element_size: 10, material_id: 1, scenario: "tip_-y",
      params: { length: 600, width: 60 },
      scalars: { max_displacement: null, max_von_mises: null },
      dev_displacement_pct: null, dev_von_mises_pct: null, message: null,
    },
  ],
  stats: {
    max_displacement: { min: 23.9, mean: 42.55, max: 61.2, n: 2 },
    dev_displacement_pct: { min: -18.4, mean: -8.95, max: 0.5, n: 2 },
  },
};

function bodyRows() {
  const table = screen.getByRole("table");
  return within(table).getAllByRole("row").slice(1, 4);
}

describe("DoeResultsTable", () => {
  it("değişen parametreleri sütun, sabitleri üstte gösterir", () => {
    render(<DoeResultsTable results={RESULTS} />);
    expect(screen.getByText("Sabit: thickness 10")).toBeInTheDocument();
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toContain("length");
    expect(headers).toContain("width");
    expect(headers?.join()).not.toContain("thickness");
  });

  it("çözülmemiş örnekte sıfır değil tire gösterir", () => {
    render(<DoeResultsTable results={RESULTS} />);
    const row = bodyRows()[2];
    expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
    expect(within(row).getByText("inp_only")).toBeInTheDocument();
  });

  it("sütun başlığına tıklayınca sıralar, boşları sonda tutar", async () => {
    render(<DoeResultsTable results={RESULTS} />);
    await userEvent.click(screen.getByRole("button", { name: /Δ deplasman/ }));
    let first = bodyRows().map((r) => r.firstChild?.textContent);
    expect(first).toEqual(["1", "0", "2"]); // -18.4, +0.5, boş

    await userEvent.click(screen.getByRole("button", { name: /Δ deplasman/ }));
    first = bodyRows().map((r) => r.firstChild?.textContent);
    expect(first).toEqual(["0", "1", "2"]); // ters çevrildi, boş yine sonda
  });

  it("alt satırda min/ort/maks özetini gösterir", () => {
    render(<DoeResultsTable results={RESULTS} />);
    expect(screen.getByText("23.9 / 42.55 / 61.2")).toBeInTheDocument();
    expect(screen.getByText("-18.4% / -8.9% / +0.5%")).toBeInTheDocument();
  });

  it("satıra tıklayınca run'ı açar; run yoksa çağırmaz", async () => {
    const onOpenRun = vi.fn();
    render(<DoeResultsTable results={RESULTS} onOpenRun={onOpenRun} />);
    await userEvent.click(bodyRows()[0]);
    expect(onOpenRun).toHaveBeenCalledWith(11);
    await userEvent.click(bodyRows()[2]);
    expect(onOpenRun).toHaveBeenCalledTimes(1);
  });

  it("örnek yoksa uyarı gösterir", () => {
    render(<DoeResultsTable results={{ ...RESULTS, rows: [], stats: {} }} />);
    expect(screen.getByText("Bu çalışmada örnek yok.")).toBeInTheDocument();
  });
});
