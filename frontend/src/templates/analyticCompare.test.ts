import { describe, expect, it } from "vitest";
import {
  comparisonFromScalars,
  formatRelPercent,
  isAnalyticComparison,
  pickAnalyticComparison,
} from "./analyticCompare";

describe("formatRelPercent", () => {
  it("göreli sapmayı yüzdeye çevirir", () => {
    expect(formatRelPercent(0.0046)).toBe("0.5%");
    expect(formatRelPercent(0.102)).toBe("10.2%");
  });
});

describe("isAnalyticComparison", () => {
  it("geçerli gövdeyi kabul eder", () => {
    expect(
      isAnalyticComparison({
        template_id: "cantilever_beam",
        skipped: false,
        reason: null,
        warned: false,
        metrics: [],
      }),
    ).toBe(true);
  });

  it("geçersiz değeri reddeder", () => {
    expect(isAnalyticComparison(null)).toBe(false);
    expect(isAnalyticComparison({ warned: true })).toBe(false);
  });
});

describe("comparisonFromScalars", () => {
  it("skalerlerdeki _analytic_comparison alanını okur", () => {
    const cmp = {
      template_id: "cantilever_beam",
      skipped: false,
      reason: null,
      warned: false,
      metrics: [],
    };
    expect(comparisonFromScalars({ max_displacement: 1, _analytic_comparison: cmp })).toEqual(cmp);
    expect(comparisonFromScalars({ max_displacement: 1 })).toBeNull();
  });

  it("üst düzey alanı skaler yedeğine tercih eder", () => {
    const a = {
      template_id: "cantilever_beam",
      skipped: false,
      reason: null,
      warned: false,
      metrics: [],
    };
    const b = { ...a, template_id: "other" };
    expect(pickAnalyticComparison(a, { _analytic_comparison: b })).toEqual(a);
    expect(pickAnalyticComparison(null, { _analytic_comparison: b })).toEqual(b);
  });
});
