import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MbdPanel from "./MbdPanel";
import { postMbdSolve, type MbdResult } from "../api/mbd";

vi.mock("../api/mbd", async (orig) => {
  const mod = await orig<typeof import("../api/mbd")>();
  return { ...mod, postMbdSolve: vi.fn() };
});

const solved: MbdResult = {
  job_id: "j1",
  state: "done",
  scalars: {
    body_acc_m_s2_max: 4.2,
    body_acc_m_s2_min: -3.1,
    susp_force_n_max: -3500,
    susp_force_n_min: -4200,
    susp_deflection_m_max: 0.01,
    susp_deflection_m_min: -0.04,
  },
  curves: {
    time: [0, 0.1, 0.2],
    body_acc_m_s2: [0, 4.2, -1],
    susp_force_n: [-3924, -3500, -4200],
    susp_deflection_m: [0, -0.02, -0.04],
  },
  diagnostics: { n_rows: 3, summary: { wall_s: 0.02, steps: 300 } },
};

describe("MbdPanel (MBD · çeyrek araç)", () => {
  beforeEach(() => {
    vi.mocked(postMbdSolve).mockReset().mockResolvedValue(solved);
  });

  it("varsayılanlarla koşar, tepe değerleri ve üç eğriyi gösterir", async () => {
    render(<MbdPanel />);
    expect(screen.getByRole("heading", { name: "Çeyrek araç" })).toBeInTheDocument();
    expect(screen.getByLabelText("Gövde kütlesi")).toHaveValue("400");
    fireEvent.change(screen.getByLabelText("Hız"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Yol profili"), { target: { value: "step" } });
    fireEvent.click(screen.getByRole("button", { name: "Çeyrek aracı çalıştır" }));
    await waitFor(() => expect(screen.getByTestId("mbd-scalars")).toHaveTextContent("4.20"));
    const body = vi.mocked(postMbdSolve).mock.calls[0][0];
    expect(body.sprung_mass_kg).toBe(400);
    expect(body.speed_m_s).toBe(12);
    expect(body.road).toEqual({ kind: "step", height_mm: 50, length_m: 1, start_m: 2 });
    expect(screen.getByTestId("mbd-chart-Gövde ivmesi")).toBeInTheDocument();
    expect(screen.getByTestId("mbd-chart-Süspansiyon kuvveti")).toBeInTheDocument();
    expect(screen.getByTestId("mbd-chart-Sıkışma")).toBeInTheDocument();
    expect(screen.getByText(/300 adım/)).toBeInTheDocument();
  });

  it("geçersiz kütlede isteği göndermez", async () => {
    render(<MbdPanel />);
    fireEvent.change(screen.getByLabelText("Gövde kütlesi"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Çeyrek aracı çalıştır" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("sıfırdan büyük");
    expect(postMbdSolve).not.toHaveBeenCalled();
  });

  it("çözücü hatasını gösterir", async () => {
    vi.mocked(postMbdSolve).mockRejectedValue(new Error("Chrono yapılandırılmamış"));
    render(<MbdPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Çeyrek aracı çalıştır" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("yapılandırılmamış");
  });
});
