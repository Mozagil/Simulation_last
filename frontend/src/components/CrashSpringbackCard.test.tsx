import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/crash", () => ({ fetchCrashAnimation: vi.fn() }));

import { fetchCrashAnimation } from "../api/crash";
import CrashSpringbackCard from "./CrashSpringbackCard";

const SC = {
  model_disp_peak_mm: 100, model_disp_peak_t_ms: 2, model_disp_final_mm: 100, springback_mm: 0, springback_ratio: 0,
  model_def_peak_mm: 1.5, model_def_peak_t_ms: 1, model_def_final_mm: 0.75, springback_def_mm: 0.75, springback_def_ratio: 0.5,
  part_0_def_peak_mm: 1.5, part_0_springback_def_mm: 0.75, part_0_springback_def_ratio: 0.5,
};

const ANIM = {
  faces: [[0, 1, 2]],
  face_part: [1], // kart 1 → mesh #0
  scalars: {},
  frames: [0, 1, 2].map((t) => ({ time: t, positions: [t * 10, 0, 0, 1 + t * 10, 0, 0, t * 10, 1, 0] })),
};

describe("1.24c3 CrashSpringbackCard", () => {
  beforeEach(() => vi.mocked(fetchCrashAnimation).mockReset());

  it("tablo: kapsam × tanım satırları, oran %; eğri animasyondan, kapsam çipleri", async () => {
    vi.mocked(fetchCrashAnimation).mockResolvedValue(ANIM);
    render(<CrashSpringbackCard scalars={SC} runId={370} />);
    const table = screen.getByRole("table", { name: "Geri sekme" });
    const rows = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual([
      "ModelMutlak |u|100.02.000100.000.0",
      "ModelÖteleme çıkarılmış |u − ū|1.5001.0000.7500.75050.0",
      "Parça #0Öteleme çıkarılmış |u − ū|1.500——0.75050.0",
    ]);
    expect(fetchCrashAnimation).toHaveBeenCalledWith(370);
    expect(await screen.findByRole("img", { name: "Yer değiştirme–zaman grafiği" })).toBeInTheDocument();
    const chips = within(screen.getByRole("group", { name: "Geri sekme eğrisi kapsamı" })).getAllByRole("button");
    expect(chips.map((c) => c.textContent)).toEqual(["Model", "#0"]);
    fireEvent.click(chips[1]);
    expect(chips[1]).toHaveAttribute("aria-pressed", "true");
  });

  it("skaler yoksa kart yok; koşu no yoksa animasyon istenmez", async () => {
    const { container, rerender } = render(<CrashSpringbackCard scalars={{ rwall_force_max: 1 }} runId={1} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CrashSpringbackCard scalars={SC} runId={null} />);
    await waitFor(() => expect(screen.getByTestId("crash-springback")).toBeInTheDocument());
    expect(fetchCrashAnimation).not.toHaveBeenCalled(); // skaler yokken de, runId yokken de istek yok
  });
});
