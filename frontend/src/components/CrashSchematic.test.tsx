import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CrashSchematic from "./CrashSchematic";

describe("CrashSchematic", () => {
  it("rigid wall şemasını gösterir", () => {
    render(<CrashSchematic />);
    expect(screen.getByRole("img", { name: /Rigid wall/i })).toBeInTheDocument();
    expect(screen.getByText(/sonsuz düzlem/)).toBeInTheDocument();
  });
});
