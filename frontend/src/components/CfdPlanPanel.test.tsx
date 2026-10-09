import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CfdPlanPanel from "./CfdPlanPanel";

describe("CfdPlanPanel (AKIŞ sekmesi iskeleti)", () => {
  it("Faz 2 planını ve verilen kararları veri olarak gösterir", () => {
    render(<CfdPlanPanel />);
    expect(screen.getByRole("heading", { name: "Akış (CFD)" })).toBeInTheDocument();
    expect(screen.queryAllByText("karar bekliyor")).toHaveLength(0);
    expect(screen.getAllByText("tamam")).toHaveLength(8);
    expect(screen.getAllByText("verildi")).toHaveLength(3);
    expect(screen.getByText("Case yazıcı")).toBeInTheDocument();
    expect(screen.getByText(/OpenFOAM dağıtımı: ESI/)).toBeInTheDocument();
    expect(screen.getByText(/iç akış \+ dış akış/)).toBeInTheDocument();
    expect(screen.queryByText("Açık kararlar")).toBeNull();
  });
});
