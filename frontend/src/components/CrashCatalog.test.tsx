import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashCatalog from "./CrashCatalog";

vi.mock("../api/crash", () => ({
  fetchCrashCatalog: vi.fn(() =>
    Promise.resolve({
      scenario_templates: { crash_box_shell: 2 },
      entries: [
        { id: "crash_box", sector: "otomotiv", title: "Crash box", status: "ready", template_id: "crash_box_shell",
          mesh_dim: 2, reference: "RD-E 1700", validation: "V1–V3", infrastructure: "", step: "1.13–1.17" },
        { id: "taylor_bar", sector: "savunma", title: "Taylor çubuğu", status: "planned", template_id: null,
          mesh_dim: null, reference: "Taylor (1948)", validation: "L/L0", infrastructure: "solid silindir", step: "K1" },
        { id: "bird_strike", sector: "savunma", title: "Kuş çarpması", status: "major", template_id: null,
          mesh_dim: null, reference: "RD-E 4900", validation: "Hugoniot", infrastructure: "SPH", step: "" },
      ],
    }),
  ),
}));

describe("CrashCatalog", () => {
  it("sektör, durum, referans ve eksik altyapıyı listeler", async () => {
    render(<CrashCatalog />);
    expect(await screen.findByText(/1\/3 hazır/)).toBeInTheDocument();
    expect(screen.getByTestId("crash-catalog-crash_box")).toHaveTextContent("Otomotiv");
    expect(screen.getByTestId("crash-catalog-crash_box")).toHaveTextContent("hazır");
    expect(screen.getByTestId("crash-catalog-taylor_bar")).toHaveTextContent("eksik: solid silindir · K1");
    expect(screen.getByTestId("crash-catalog-bird_strike")).toHaveTextContent("ayrı faz");
  });
});
