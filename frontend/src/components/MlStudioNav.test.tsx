import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MlStudioNav from "./MlStudioNav";

describe("MlStudioNav", () => {
  it("beş aşamayı sırayla listeler, seçili olanı işaretler, tıklamayı iletir", () => {
    const onSelect = vi.fn();
    render(<MlStudioNav stage="data" onSelect={onSelect} meta={{ data: "412 run" }} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.querySelector(".ml-stage-name")?.textContent)).toEqual([
      "DOE",
      "Veri seti",
      "Yakınsama",
      "Model",
      "Tahmin",
    ]);
    expect(buttons[1]).toHaveAttribute("aria-current", "step");
    expect(buttons[0]).not.toHaveAttribute("aria-current");
    expect(buttons[1]).toHaveTextContent("412 run");
    fireEvent.click(buttons[4]);
    expect(onSelect).toHaveBeenCalledWith("pred");
  });
});
