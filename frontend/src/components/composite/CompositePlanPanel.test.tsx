import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CompositePlanPanel from "./CompositePlanPanel";

describe("CompositePlanPanel (KOMPOZIT sekmesi iskeleti)", () => {
  it("Faz 3 planını ve verilen kararları veri olarak gösterir", () => {
    render(<CompositePlanPanel />);
    expect(screen.getByRole("heading", { name: "Kompozit" })).toBeInTheDocument();
    expect(screen.queryAllByText("karar bekliyor")).toHaveLength(0);
    expect(screen.getAllByText("tamam")).toHaveLength(13);
    expect(screen.getAllByText("planlandı")).toHaveLength(2);
    expect(screen.getAllByText("verildi")).toHaveLength(4);
    expect(screen.getByText("İskelet")).toBeInTheDocument();
    expect(screen.getByText(/Dalga 1 solver: CalculiX/)).toBeInTheDocument();
    expect(screen.getByText(/\/solve refaktör edilmez/)).toBeInTheDocument();
    expect(screen.queryByText("Açık kararlar")).toBeNull();
  });
});
