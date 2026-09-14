import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AnalyticComparisonPanel from "./AnalyticComparisonPanel";
import type { AnalyticComparison } from "../templates/analyticCompare";

const OK: AnalyticComparison = {
  template_id: "cantilever_beam",
  skipped: false,
  reason: null,
  warned: false,
  metrics: [
    {
      key: "max_displacement",
      label: "Max deplasman",
      unit: "mm",
      analytic: 23.81,
      fea: 23.92,
      rel_error: 0.0046,
      threshold: 0.1,
      warn: false,
    },
  ],
};

describe("AnalyticComparisonPanel", () => {
  it("analitik ve FEA değerlerini gösterir", () => {
    render(<AnalyticComparisonPanel comparison={OK} />);
    expect(screen.getByText("Analitik referans")).toBeInTheDocument();
    expect(screen.getByText("23.81")).toBeInTheDocument();
    expect(screen.getByText("23.92")).toBeInTheDocument();
    expect(screen.getByText("0.5%")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("eşik aşılınca uyarı verir", () => {
    const warned: AnalyticComparison = {
      ...OK,
      warned: true,
      metrics: [{ ...OK.metrics[0], rel_error: 0.42, warn: true }],
    };
    render(<AnalyticComparisonPanel comparison={warned} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Sapma eşiği aşıldı.");
    expect(screen.getByText(/eşik aşıldı/)).toBeInTheDocument();
  });

  it("atlanmış karşılaştırmada nedeni gösterir", () => {
    render(
      <AnalyticComparisonPanel
        comparison={{
          template_id: "cantilever_beam",
          skipped: true,
          reason: "Analitik karşılaştırma için CLOAD (kuvvet) gerekli.",
          warned: false,
          metrics: [],
        }}
      />,
    );
    expect(screen.getByText(/CLOAD/)).toBeInTheDocument();
  });
});
