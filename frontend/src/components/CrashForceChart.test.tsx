import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CrashForceChart, { forceSeriesFromCurves } from "./CrashForceChart";

describe("forceSeriesFromCurves", () => {
  it("temasları numara sırasıyla, duvarı en sona alır; diğer eğrileri atlar", () => {
    const series = forceSeriesFromCurves({
      time: [0, 1],
      rwall_force: [0, 3],
      contact_10_force: [0, 1],
      contact_2_force: [0, 2],
      internal_energy: [0, 9],
    });
    expect(series.map((s) => s.label)).toEqual(["Temas 2", "Temas 10", "Rijit duvar"]);
  });

  it("tek noktalı seri ve eğrisiz iş boş döner", () => {
    expect(forceSeriesFromCurves(undefined)).toEqual([]);
    expect(forceSeriesFromCurves({ time: [0], contact_1_force: [0] })).toEqual([]);
  });
});

describe("CrashForceChart", () => {
  it("seri başına çizgi, lejant ve tepe değeri çizer", () => {
    const { container } = render(
      <CrashForceChart
        time={[0, 1, 2]}
        series={[
          { key: "contact_1_force", label: "Temas 1", values: [0, 5, 1] },
          { key: "rwall_force", label: "Rijit duvar", values: [0, -2, 3] },
        ]}
      />,
    );
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
    expect(screen.getByText("Temas 1 tepe")).toBeInTheDocument();
    expect(screen.getByText("5.00 kN")).toBeInTheDocument();
    // işaret yok sayılır: |−2| < 3, tepe t = 2 ms
    expect(screen.getByText("3.00 kN")).toBeInTheDocument();
    expect(screen.getByText("t = 2.00 ms")).toBeInTheDocument();
  });
});
