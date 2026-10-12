import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CompositeMaterialsPanel from "./CompositeMaterialsPanel";

vi.mock("../../api/composite", () => ({
  fetchCompositeMaterials: vi.fn(),
  createCompositeMaterial: vi.fn(),
}));

import { createCompositeMaterial, fetchCompositeMaterials } from "../../api/composite";

const T300 = {
  id: 1,
  name: "T300/epoxy",
  ply_kind: "ud",
  category: "cfrp",
  standard: "typical handbook",
  density: 1600,
  e1: 135e9,
  e2: 10e9,
  e3: 10e9,
  nu12: 0.3,
  nu13: 0.3,
  nu23: 0.45,
  g12: 5.2e9,
  g13: 5.2e9,
  g23: 3.4e9,
  xt: 1500e6,
  xc: 1200e6,
  yt: 50e6,
  yc: 200e6,
  s12: 70e6,
  s13: 70e6,
  s23: 40e6,
  source: "library",
  is_editable: false,
};

describe("CompositeMaterialsPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchCompositeMaterials).mockReset();
    vi.mocked(createCompositeMaterial).mockReset();
    vi.mocked(fetchCompositeMaterials).mockResolvedValue([T300]);
  });

  it("kütüphane ply'sini listeler ve sabitleri gösterir", async () => {
    render(<CompositeMaterialsPanel />);
    expect(await screen.findByRole("combobox", { name: "Ply seç" })).toHaveDisplayValue(
      "T300/epoxy (cfrp)",
    );
    expect(screen.getByText("135.0 GPa")).toBeInTheDocument();
    expect(screen.getByText("1500 MPa")).toBeInTheDocument();
    expect(screen.getByText("kütüphane")).toBeInTheDocument();
    expect(screen.getByText("typical handbook")).toBeInTheDocument();
  });

  it("özel ply formunu GPa/MPa'dan Pa'ya çevirerek gönderir", async () => {
    const user = userEvent.setup();
    vi.mocked(createCompositeMaterial).mockResolvedValue({
      ...T300,
      id: 9,
      name: "MyUD",
      source: "user_defined",
      is_editable: true,
      category: "custom",
      standard: null,
    });
    render(<CompositeMaterialsPanel />);
    await screen.findByRole("combobox", { name: "Ply seç" });
    await user.click(screen.getByRole("button", { name: "+ ÖZEL" }));
    await user.type(screen.getByLabelText("Ply adı"), "MyUD");
    await user.type(screen.getByLabelText("E1"), "120");
    await user.type(screen.getByLabelText("E2"), "9");
    await user.type(screen.getByLabelText("E3"), "9");
    await user.type(screen.getByLabelText("G12"), "5");
    await user.type(screen.getByLabelText("G13"), "5");
    await user.type(screen.getByLabelText("G23"), "3");
    await user.type(screen.getByLabelText("nu12"), "0.3");
    await user.type(screen.getByLabelText("nu13"), "0.3");
    await user.type(screen.getByLabelText("nu23"), "0.4");
    await user.type(screen.getByLabelText("density"), "1600");
    await user.type(screen.getByLabelText("Xt"), "1400");
    await user.type(screen.getByLabelText("Xc"), "1100");
    await user.type(screen.getByLabelText("Yt"), "45");
    await user.type(screen.getByLabelText("Yc"), "180");
    await user.type(screen.getByLabelText("S12"), "65");
    await user.click(screen.getByRole("button", { name: "Özel ply ekle" }));
    await waitFor(() => {
      expect(createCompositeMaterial).toHaveBeenCalledTimes(1);
    });
    const sent = vi.mocked(createCompositeMaterial).mock.calls[0][0];
    expect(sent.name).toBe("MyUD");
    expect(sent.e1).toBe(120e9);
    expect(sent.xt).toBe(1400e6);
    expect(sent.density).toBe(1600);
    expect(await screen.findByRole("combobox", { name: "Ply seç" })).toHaveDisplayValue("MyUD (custom)");
  });
});
