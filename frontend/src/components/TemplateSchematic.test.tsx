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

  it("delikli plaka için H, W, d ve çekme F şemasını gösterir", () => {
    render(<TemplateSchematic templateId="plate_with_hole" />);
    expect(screen.getByRole("img", { name: /delikli plaka/i })).toBeInTheDocument();
    expect(screen.getByText("H")).toBeInTheDocument();
    expect(screen.getByText("W")).toBeInTheDocument();
    expect(screen.getByText("d")).toBeInTheDocument();
    expect(screen.getAllByText("F")).toHaveLength(2);
  });

  it("dogbone için b, B, L0 ve çekme F şemasını gösterir", () => {
    render(<TemplateSchematic templateId="dogbone" />);
    expect(screen.getByRole("img", { name: /dogbone/i })).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByText("L0")).toBeInTheDocument();
    expect(screen.getAllByText("F")).toHaveLength(2);
  });

  it("kalın cidarlı boru için a, b ve iç basınç p şemasını gösterir", () => {
    render(<TemplateSchematic templateId="thick_walled_tube" />);
    expect(screen.getByRole("img", { name: /kalın cidarlı boru/i })).toBeInTheDocument();
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
    expect(screen.getByText("p")).toBeInTheDocument();
  });

  it("burulma mili için L, R ve T şemasını gösterir", () => {
    render(<TemplateSchematic templateId="torsion_shaft" />);
    expect(screen.getByRole("img", { name: /burulma mili/i })).toBeInTheDocument();
    expect(screen.getByText("L")).toBeInTheDocument();
    expect(screen.getByText("R")).toBeInTheDocument();
    expect(screen.getByText("T")).toBeInTheDocument();
    expect(screen.getByText("ankastre")).toBeInTheDocument();
  });

  it("bilinmeyen şablonda bir şey çizmez", () => {
    const { container } = render(<TemplateSchematic templateId="yok" />);
    expect(container).toBeEmptyDOMElement();
  });
});
