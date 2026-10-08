import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CfdPlanPanel from "./CfdPlanPanel";

describe("CfdPlanPanel (AKIŞ sekmesi iskeleti)", () => {
  it("Faz 2 planını ve açık kararları veri olarak gösterir; çözücü bağlı değil", () => {
    render(<CfdPlanPanel />);
    expect(screen.getByRole("heading", { name: "Akış (CFD)" })).toBeInTheDocument();
    expect(screen.queryAllByText("karar bekliyor")).toHaveLength(0);
    expect(screen.getAllByText("tamam")).toHaveLength(4);
    expect(screen.getByText("verildi")).toBeInTheDocument();
    expect(screen.getByText("Case yazıcı")).toBeInTheDocument();
    expect(screen.getByText(/OpenFOAM dağıtımı: ESI/)).toBeInTheDocument();
    expect(screen.getByText(/İlk hedef vaka/)).toBeInTheDocument();
  });
});
