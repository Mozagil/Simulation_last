import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CrashScenarioCard from "./CrashScenarioCard";

vi.mock("../api/materials", () => ({
  fetchMaterials: vi.fn(() =>
    Promise.resolve([
      { id: 3, name: "6061-T6" },
      { id: 1, name: "S235" },
    ]),
  ),
}));

vi.mock("../api/crash", () => ({
  postCrashScenario: vi.fn(() =>
    Promise.resolve({ geometry_id: 4000, scenario: {}, crash: { job_id: "jx", run_id: 77, status: "pending" } }),
  ),
  fetchCrashJob: vi.fn(() => Promise.resolve({ job_id: "jx", status: "solved", percent: 100 })),
}));

import { postCrashScenario } from "../api/crash";

describe("CrashScenarioCard", () => {
  it("şablon parametreleri, kızak (rijit gövde) ve CFC ile senaryo gönderir; S235 varsayılan", async () => {
    const onDone = vi.fn();
    render(<CrashScenarioCard onDone={onDone} />);
    await waitFor(() => expect(screen.getByLabelText("Senaryo malzemesi")).toHaveValue("1"));
    fireEvent.change(screen.getByLabelText("L (mm)"), { target: { value: "250" } });
    fireEvent.change(screen.getByLabelText("Kızak (kg)"), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText("Senaryo kuvvet CFC"), { target: { value: "600" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    await waitFor(() => expect(postCrashScenario).toHaveBeenCalledTimes(1));
    const body = vi.mocked(postCrashScenario).mock.calls[0][0];
    expect(body.geometry).toEqual({ box_length: 250, box_height: 50, box_width: 40, wall: 3 });
    expect(body.material_id).toBe(1);
    expect(body.rigid_bodies).toEqual([{ name: "kizak", region: "kutu_arka", mass_kg: 50 }]);
    expect(body.filters).toEqual({ force_cfc: 600, acc_cfc: null });
    expect(body.wait).toBe(false);
    expect(await screen.findByTestId("crash-scenario-status")).toHaveTextContent("koşu #77 · geometri 4000");
    expect(onDone).toHaveBeenCalled();
  });

  it("kızak boşsa rijit gövde yok; geçersiz sayı hata", async () => {
    render(<CrashScenarioCard />);
    fireEvent.change(screen.getByLabelText("t (mm)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Senaryoyu koş" }));
    expect(await screen.findByText(/t: sayı geçersiz/)).toBeInTheDocument();
  });
});
