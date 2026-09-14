import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import TemplateSchematic from "./TemplateSchematic";

describe("TemplateSchematic", () => {
  it("ankastre kiriş için L, T, W ve F şemasını gösterir", () => {
    render(<TemplateSchematic templateId="cantilever_beam" />);
    expect(screen.getByRole("img", { name: /ankastre kiriş/i })).toBeInTheDocument();
    expect(screen.getByText("L")).toBeInTheDocument();
    expect(screen.getByText("T")).toBeInTheDocument();
    expect(screen.getByText("W")).toBeInTheDocument();
    expect(screen.getByText("F")).toBeInTheDocument();
  });

  it("basit mesnetli kiriş için mesnet ve orta nokta F şemasını gösterir", () => {
    render(<TemplateSchematic templateId="simply_supported_beam" />);
    expect(screen.getByRole("img", { name: /basit mesnetli kiriş/i })).toBeInTheDocument();
    expect(screen.getAllByText("mesnet")).toHaveLength(2);
    expect(screen.getByText("F")).toBeInTheDocument();
    expect(screen.queryByText("q")).not.toBeInTheDocument();
  });

  it("bilinmeyen şablonda bir şey çizmez", () => {
    const { container } = render(<TemplateSchematic templateId="yok" />);
    expect(container).toBeEmptyDOMElement();
  });
});
