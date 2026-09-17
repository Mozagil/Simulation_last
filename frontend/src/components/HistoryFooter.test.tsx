import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RunSummary } from "../api/runs";
import HistoryFooter from "./HistoryFooter";

const RUN: RunSummary = {
  id: 19,
  geometry_id: 1,
  geometry_filename: "cantilever_beam.step",
  template_id: "cantilever_beam",
  template_params: { length: 500, thickness: 10, width: 50 },
  name: "DOE 19 · varsayılan",
  created_at: "2026-09-17T14:31:17.000Z",
  dimension: 3,
  status: "solved",
  message: null,
  scalars: { max_von_mises: 4.63e2, max_displacement: 8.19e-1 },
};

function renderFooter(overrides: Partial<ComponentProps<typeof HistoryFooter>> = {}) {
  const props: ComponentProps<typeof HistoryFooter> = {
    runs: [RUN],
    compareSelection: [],
    busy: false,
    paramSymbols: { cantilever_beam: { length: "L", thickness: "T", width: "W" } },
    onToggleCompare: vi.fn(),
    onReview: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onCompare: vi.fn(),
    ...overrides,
  };
  return { ...render(<HistoryFooter {...props} />), props };
}

describe("HistoryFooter", () => {
  it("kapalı başlar: sayıyı gösterir, listeyi çizmez", () => {
    renderFooter();
    expect(screen.getByText("Analiz geçmişi")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.queryByText("DOE 19 · varsayılan")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aç" })).toBeInTheDocument();
  });

  it("Aç deyince satırlar gelir, Gizle deyince tekrar kapanır", async () => {
    const user = userEvent.setup();
    renderFooter();
    await user.click(screen.getByRole("button", { name: "Aç" }));
    expect(screen.getByText("DOE 19 · varsayılan")).toBeInTheDocument();
    expect(screen.getByText(/L 500/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Gizle" }));
    expect(screen.queryByText("DOE 19 · varsayılan")).not.toBeInTheDocument();
  });

  it("donmuş set varken üyelik rozetlerini gösterir", async () => {
    const user = userEvent.setup();
    const other: RunSummary = { ...RUN, id: 263, name: "manuel deneme" };
    const forced: RunSummary = { ...RUN, id: 31, name: "override edilen" };
    renderFooter({
      runs: [RUN, other, forced],
      corpusName: "kiris-v1",
      corpusRoles: { 19: "auto", 31: "manual_override" },
    });
    expect(screen.getByText("set: kiris-v1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aç" }));
    expect(screen.getByText("eğitim")).toBeInTheDocument();
    expect(screen.getByText("manuel ⚠")).toBeInTheDocument();
    // Manifestte olmayan run "sette değil" olarak işaretlenir.
    expect(screen.getByText("sette değil")).toBeInTheDocument();
  });

  it("set dondurulmamışsa rozet çizilmez", async () => {
    const user = userEvent.setup();
    renderFooter();
    await user.click(screen.getByRole("button", { name: "Aç" }));
    expect(screen.queryByText("eğitim")).not.toBeInTheDocument();
    expect(screen.queryByText("sette değil")).not.toBeInTheDocument();
  });

  it("iki run seçiliyken karşılaştır butonu görünür", async () => {
    const user = userEvent.setup();
    const onCompare = vi.fn();
    renderFooter({
      compareSelection: [19, 18],
      onCompare,
    });
    expect(screen.getByText("2/2 seçili")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Karşılaştır" }));
    expect(onCompare).toHaveBeenCalledTimes(1);
  });
});
