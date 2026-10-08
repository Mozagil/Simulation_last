import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CfdPlanPanel from "./CfdPlanPanel";

describe("CfdPlanPanel (AKIŞ sekmesi iskeleti)", () => {
  it("Faz 2 planını ve açık kararları veri olarak gösterir; çözücü bağlı değil", () => {
    render(<CfdPlanPanel />);
    expect(screen.getByRole("heading", { name: "Akış (CFD)" })).toBeInTheDocument();
    expect(screen.getAllByText("karar bekliyor")).toHaveLength(2);
    expect(screen.getByText("Case yazıcı")).toBeInTheDocument();
    expect(screen.getByText(/OpenFOAM dağıtımı/)).toBeInTheDocument();
  });
});
