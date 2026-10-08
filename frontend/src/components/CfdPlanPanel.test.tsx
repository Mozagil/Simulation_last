import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CfdPlanPanel from "./CfdPlanPanel";

describe("CfdPlanPanel (AKIŞ sekmesi iskeleti)", () => {
  it("Faz 2 planını ve açık kararları veri olarak gösterir; çözücü bağlı değil", () => {
    render(<CfdPlanPanel />);
    expect(screen.getByRole("heading", { name: "Akış (CFD)" })).toBeInTheDocument();
    expect(screen.getAllByText("karar bekliyor")).toHaveLength(1);
    expect(screen.getByText("tamam")).toBeInTheDocument();
    expect(screen.getByText("verildi")).toBeInTheDocument();
    expect(screen.getByText("Case yazıcı")).toBeInTheDocument();
    expect(screen.getByText(/OpenFOAM dağıtımı: ESI/)).toBeInTheDocument();
    expect(screen.getByText(/İlk hedef vaka/)).toBeInTheDocument();
  });
});
