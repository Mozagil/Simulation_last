import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CfdResults, { patchForces } from "./CfdResults";

describe("CfdResults", () => {
  it("patchForces: toplam / basınç / viskoz ve yama adı alt çizgili olsa da ayrışır", () => {
    const pf = patchForces({
      force_total_x: 6.4,
      force_total_pressure_x: 4,
      force_ust_kanat_x: 1.5,
      force_ust_kanat_viscous_x: 0.2,
      moment_total_y: 9,
      Cd: 0.5,
    });
    expect(pf.total).toEqual({ x: 6.4, pressure_x: 4 });
    expect(pf.ust_kanat).toEqual({ x: 1.5, viscous_x: 0.2 });
    expect(Object.keys(pf)).toHaveLength(2);
  });

  it("katsayı geçmişi doğrusal grafikte; α ≈ 0 roketinde basınç merkezi tanımsız yazılır", () => {
    render(
      <CfdResults
        job={{
          job_id: "j",
          status: "solved",
          message: "",
          scalars: { iterations: 10, converged: 1, Cd: 0.5, Cd_mean: 0.5, Cd_std: 0.01 },
          curves: { force_coeffs: { iteration: [1, 2, 3], Cd: [0.6, 0.55, 0.5], Cl: [0, 0.01, 0] } },
          rocket_aero: { CA: 0.53, CN: 0.002, CD: 0.53, CL: 0.002, Cm: -0.04 },
        }}
      />,
    );
    expect(screen.getByTestId("cfd-coeff-chart")).toBeInTheDocument();
    expect(screen.getByTestId("cfd-rocket-aero")).toHaveTextContent("α ≈ 0 — tanımsız");
  });
});
