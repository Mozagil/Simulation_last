import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TemplateLoadDialog from "../components/TemplateLoadDialog";
import type { GeometryTemplateInfo } from "../api/templates";

const TEMPLATE = { id: "cantilever_beam", name: "Ankastre kiriş", regions: [], parameters: [] } as unknown as GeometryTemplateInfo;

function setup() {
  const onCancel = vi.fn();
  render(
    <TemplateLoadDialog
      template={TEMPLATE}
      params={{}}
      bcs={[{ type: "cload", region: "yuk", fx: 0, fy: -500, fz: 0 } as never]}
      inputs={{ "0.fx": "0", "0.fy": "-500", "0.fz": "0" }}
      busy={false}
      error={null}
      onInputChange={() => {}}
      onCancel={onCancel}
      onConfirm={() => {}}
    />,
  );
  const backdrop = screen.getByRole("dialog").parentElement as HTMLElement;
  return { onCancel, backdrop };
}

describe("useBackdropClose (1.23 A1)", () => {
  it("alan içinde basılıp dışarıda bırakılan sürükleme pop-up'ı kapatmaz", () => {
    const { onCancel, backdrop } = setup();
    const input = screen.getByLabelText("Fy (N)");
    fireEvent.mouseDown(input);
    fireEvent.click(backdrop); // tarayıcı: ortak ataya click
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("arka plana basıp bırakmak kapatır", () => {
    const { onCancel, backdrop } = setup();
    fireEvent.mouseDown(backdrop);
    fireEvent.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
