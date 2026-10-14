import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CrashForceChart, { forceSeriesFromCurves, niceTicks } from "./CrashForceChart";

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
  it("1.17e: CFC süzülmüş kopyalar ham serilerden sonra, sınıfla etiketlenir", () => {
    const s = forceSeriesFromCurves({ time: [0, 1, 2], rwall_force: [0, 5, 0], rwall_force_cfc600: [0, 4, 0], section_1_force_cfc600: [0, 3, 0], section_1_force: [0, 6, 0] });
    expect(s.map((x) => x.label)).toEqual(["Rijit duvar", "Kesit 1", "Rijit duvar CFC600", "Kesit 1 CFC600"]);
  });
  it("1.17e2: CFC serisi ham eşiyle aynı renk ve kalın, eşi olan ham soluk", () => {
    const { container } = render(
      <CrashForceChart time={[0, 1, 2]} series={[
        { key: "rwall_force", label: "ham", values: [0, 5, 0] },
        { key: "section_1_force", label: "kesit", values: [0, 3, 0] },
        { key: "rwall_force_cfc600", label: "cfc", values: [0, 4, 0] },
      ]} />,
    );
    const cls = [...container.querySelectorAll("polyline")].map((p) => p.getAttribute("class"));
    expect(cls).toEqual([
      "crash-force-line crash-series-0 crash-force-line-raw",
      "crash-force-line crash-series-1",
      "crash-force-line crash-series-0 crash-force-line-cfc",
    ]);
  });
});

describe("1.23 C8 eksen + tepe işareti", () => {
  it("niceTicks: 0'dan 1·2·2.5·5 adımla üst sınırı kapsar", () => {
    expect(niceTicks(122.3)).toEqual([0, 50, 100, 150]);
    expect(niceTicks(57.1)).toEqual([0, 20, 40, 60]);
    expect(niceTicks(0.9)).toEqual([0, 0.25, 0.5, 0.75, 1]);
    expect(niceTicks(0)).toEqual([0, 1]);
  });

  it("y ekseni adı + birim, tikler, tepe noktası ve açıklama", () => {
    render(
      <CrashForceChart
        time={[0, 1, 2]}
        series={[{ key: "rwall_force", label: "Rijit duvar", values: [0, 122.3, 40] }]}
        note="Kuvvet = impuls türevi"
      />,
    );
    expect(screen.getByText("kuvvet (kN)")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
    const peak = screen.getByTestId("crash-chart-peak");
    expect(peak).toHaveTextContent("122");
    expect(peak).toHaveAttribute("title", "Rijit duvar tepe 122 kN · t = 1.00 ms");
    expect(screen.getByText("Kuvvet = impuls türevi")).toBeInTheDocument();
  });

  it("CFC eşi olan ham serinin tepesi işaretlenmez", () => {
    render(
      <CrashForceChart
        time={[0, 1]}
        series={[
          { key: "rwall_force", label: "ham", values: [0, 10] },
          { key: "rwall_force_cfc60", label: "CFC60", values: [0, 8] },
        ]}
      />,
    );
    expect(screen.getAllByTestId("crash-chart-peak")).toHaveLength(1);
  });
});
