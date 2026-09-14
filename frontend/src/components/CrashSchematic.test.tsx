import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CrashSchematic from "./CrashSchematic";

describe("CrashSchematic", () => {
  it("rigid wall şemasını gösterir", () => {
    render(<CrashSchematic scenario="rigid_wall" />);
    expect(screen.getByRole("img", { name: /Rigid wall/i })).toBeInTheDocument();
    expect(screen.getByText(/sonsuz düzlem/)).toBeInTheDocument();
  });

  it("plaka-küre şemasını gösterir", () => {
    render(<CrashSchematic scenario="plate_ball" />);
    expect(screen.getByRole("img", { name: /Plaka-küre/i })).toBeInTheDocument();
    expect(screen.getByText(/rijit duvar/)).toBeInTheDocument();
  });
});
