import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { dynaFor, setDynaRefs } from "../lib/dynaKeywords";
import Kw, { DynaToggle, KwRef } from "./Kw";

describe("LS-DYNA karşılıkları (bilgi amaçlı)", () => {
  beforeEach(() => {
    setDynaRefs(false);
  });

  it("eşleme tablosu", () => {
    expect(dynaFor("/RWALL")).toBe("*RIGIDWALL_PLANAR");
    expect(dynaFor("/MAT/LAW1")).toBe("*MAT_ELASTIC (001)");
    expect(dynaFor("/YOK")).toBeNull();
  });

  it("varsayılan kapalı; anahtar açınca kart adının yanında ≈ karşılık görünür, tercih saklanır", () => {
    render(
      <>
        <DynaToggle />
        <Kw card="/RWALL" text="/RWALL normal" />
        <KwRef card="/BCS" />
      </>,
    );
    expect(screen.getByText("/RWALL normal")).toBeInTheDocument();
    expect(screen.queryAllByTitle(/LS-DYNA karşılığı/)).toHaveLength(0);
    const btn = screen.getByRole("button", { name: /LS-DYNA karşılıkları/ });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
    const refs = screen.getAllByTitle(/LS-DYNA karşılığı/).map((e) => e.textContent);
    expect(refs).toEqual(["≈ *RIGIDWALL_PLANAR", "≈ *BOUNDARY_SPC_SET"]);
    expect(window.localStorage.getItem("showDynaRefs")).toBe("1");
  });
});
