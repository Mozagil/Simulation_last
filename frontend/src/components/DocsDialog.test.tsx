import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CRASH_DOC, CRASH_SCENARIOS } from "../docs/crashDoc";
import { dynaFor } from "../lib/dynaKeywords";
import DocsDialog from "./DocsDialog";

describe("Belgeler penceresi", () => {
  it("içerik tutarlı: her kartın LS-DYNA karşılığı var, 15 senaryo, görseller public/docs/crash altında", () => {
    for (const s of CRASH_DOC) {
      for (const it of s.items ?? []) {
        if (it.card) expect(dynaFor(it.card), `${s.id}: ${it.card}`).not.toBeNull();
      }
      if (s.image) expect(s.image).toMatch(/^\/docs\/crash\//);
    }
    expect(CRASH_SCENARIOS).toHaveLength(15);
  });

  it("bölümler, OpenRadioss + LS-DYNA sütunları; arama süzer; Esc kapatır", () => {
    const onClose = vi.fn();
    render(<DocsDialog onClose={onClose} />);
    const dlg = screen.getByRole("dialog", { name: "Belgeler" });
    expect(within(dlg).getByRole("heading", { name: "4 · Crash → 4 Ek tanımlar" })).toBeInTheDocument();
    expect(within(dlg).getAllByText("*BOUNDARY_SPC_SET").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Belgelerde ara"), { target: { value: "kızak" } });
    expect(within(dlg).queryByRole("heading", { name: "4 · Crash → 3 Temaslar" })).toBeNull();
    expect(within(dlg).getByRole("heading", { name: "4 · Crash → 4 Ek tanımlar" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Belgeler sırası", () => {
  it("bölümler arayüzdeki adım sırasını izler (3 · Material, 4 · Crash'ten önce; Sonuçlar en sonda)", () => {
    const ids = CRASH_DOC.map((s) => s.id);
    expect(ids.indexOf("malzeme")).toBeLessThan(ids.indexOf("carpma"));
    expect(ids.indexOf("cikti")).toBeLessThan(ids.indexOf("sonuclar"));
    expect(ids.indexOf("uzman")).toBeLessThan(ids.indexOf("cikti"));
  });
});

describe("Belgeler · eğitim sayfası", () => {
  it("son sayfa: T1–T18, modele göre gruplu; aramada süzülür", () => {
    render(<DocsDialog onClose={() => undefined} />);
    expect(screen.getByRole("heading", { name: "Eğitim testleri (T1–T18)" })).toBeInTheDocument();
    for (const id of ["T1", "T9", "T18"]) expect(screen.getByTestId(`train-${id}`)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Belgelerde ara"), { target: { value: "kızak" } });
    expect(screen.getByTestId("train-T9")).toBeInTheDocument();
    expect(screen.queryByTestId("train-T1")).toBeNull();
  });
});
