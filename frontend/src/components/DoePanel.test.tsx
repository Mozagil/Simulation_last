import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DoePanel from "./DoePanel";

vi.mock("../api/doe", () => ({
  DoeApiError: class DoeApiError extends Error {},
  fetchDoeStudies: vi.fn(),
  createDoeStudy: vi.fn(),
  startQualitySet: vi.fn(),
  fetchDoeQuality: vi.fn(),
}));

vi.mock("../api/materials", () => ({
  fetchMaterials: vi.fn(),
}));

vi.mock("../api/templates", () => ({
  fetchTemplates: vi.fn(),
}));

import { createDoeStudy, fetchDoeQuality, fetchDoeStudies, startQualitySet } from "../api/doe";
import { fetchMaterials } from "../api/materials";
import { fetchTemplates } from "../api/templates";

const CANTILEVER = {
  id: "cantilever_beam",
  name: "Ankastre kiriş",
  description: "",
  tags: [],
  params_schema: {
    properties: {
      length: { type: "number", default: 500, unit: "mm", title: "Uzunluk", symbol: "L" },
      thickness: { type: "number", default: 10, unit: "mm", title: "Kalınlık", symbol: "T" },
    },
  },
  regions: [],
  has_analytic: true,
  default_bcs: [
    { type: "fixed", region: "ankastre_uc" },
    { type: "cload", region: "yuk_yuzeyi", fx: 0, fy: -500, fz: 0 },
  ],
};

describe("DoePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchDoeStudies).mockReset();
    vi.mocked(createDoeStudy).mockReset();
    vi.mocked(startQualitySet).mockReset();
    vi.mocked(fetchDoeQuality).mockReset();
    vi.mocked(fetchMaterials).mockReset();
    vi.mocked(fetchTemplates).mockReset();
    vi.mocked(fetchTemplates).mockResolvedValue([CANTILEVER as never]);
    vi.mocked(fetchDoeStudies).mockResolvedValue([]);
    vi.mocked(fetchDoeQuality).mockResolvedValue({
      study_id: 1,
      n_cases: 8,
      n_ok: 0,
      counts: { inp_only: 8 },
      flagged: { inp_only: [0, 1, 2, 3, 4, 5, 6, 7] },
    });
    vi.mocked(fetchMaterials).mockResolvedValue([{ id: 3, name: "S235" } as never]);
    vi.mocked(createDoeStudy).mockResolvedValue({
      id: 1,
      name: "cantilever LHS",
      template_id: "cantilever_beam",
      seed: 42,
      status: "completed",
      message: "8/8 başarılı",
      n_cases: 8,
      counts: { inp_only: 8 },
      cases: [],
    });
  });

  it("varsayılan aralıklarla DOE başlatır", async () => {
    render(<DoePanel />);
    expect(await screen.findByLabelText("Uzunluk min")).toHaveValue(400);
    expect(screen.getByLabelText("Uzunluk maks")).toHaveValue(600);

    fireEvent.click(screen.getByRole("button", { name: "DOE başlat" }));
    await waitFor(() => expect(createDoeStudy).toHaveBeenCalledTimes(1));
    const [spec, wait] = vi.mocked(createDoeStudy).mock.calls[0];
    expect(wait).toBe(true);
    expect(spec.template_id).toBe("cantilever_beam");
    expect(spec.n_samples).toBe(8);
    expect(spec.seed).toBe(42);
    expect(spec.material_ids).toEqual([3]);
    expect(spec.geometry).toEqual({ length: [400, 600], thickness: [8, 12] });
    expect(spec.bc_scenarios[0].bcs).toEqual(CANTILEVER.default_bcs);
    expect(spec.load_scale).toEqual([0.5, 2]);
  });

  it("kullanıcının verdiği aralığı ve sabitlediği parametreyi gönderir", async () => {
    render(<DoePanel />);
    const min = await screen.findByLabelText("Uzunluk min");
    fireEvent.change(min, { target: { value: "300" } });
    fireEvent.change(screen.getByLabelText("Uzunluk maks"), { target: { value: "900" } });
    // Kalınlığı sabitle
    fireEvent.change(screen.getByLabelText("Kalınlık tarama tipi"), { target: { value: "fixed" } });
    fireEvent.change(screen.getByLabelText("Kalınlık sabit değer"), { target: { value: "15" } });

    fireEvent.click(screen.getByRole("button", { name: "DOE başlat" }));
    await waitFor(() => expect(createDoeStudy).toHaveBeenCalledTimes(1));
    const [spec] = vi.mocked(createDoeStudy).mock.calls[0];
    expect(spec.geometry).toEqual({ length: [300, 900] });
    expect(spec.fixed_params).toEqual({ thickness: 15 });
  });

  it("ters aralıkta istek göndermez, hata gösterir", async () => {
    render(<DoePanel />);
    const min = await screen.findByLabelText("Uzunluk min");
    fireEvent.change(min, { target: { value: "700" } });
    fireEvent.change(screen.getByLabelText("Uzunluk maks"), { target: { value: "400" } });

    fireEvent.click(screen.getByRole("button", { name: "DOE başlat" }));
    await waitFor(() =>
      expect(screen.getByText(/maks değer min değerden büyük olmalı/)).toBeInTheDocument(),
    );
    expect(createDoeStudy).not.toHaveBeenCalled();
  });

  it("örnekleme kısıt yüzünden eksik kalırsa uyarır", async () => {
    vi.mocked(createDoeStudy).mockResolvedValue({
      id: 2, name: null, template_id: "cantilever_beam", seed: 42,
      status: "completed", message: null, n_cases: 3, counts: {}, cases: [],
    });
    render(<DoePanel />);
    await screen.findByLabelText("Uzunluk min");
    fireEvent.click(screen.getByRole("button", { name: "DOE başlat" }));
    await waitFor(() =>
      expect(screen.getByText(/8 örnek istendi, 3 üretildi/)).toBeInTheDocument(),
    );
  });

  it("200'lük kalite setini arka planda başlatır", async () => {
    vi.mocked(startQualitySet).mockResolvedValue({
      id: 9,
      name: "kalite-200 cantilever",
      template_id: "cantilever_beam",
      seed: 2026,
      status: "pending",
      message: null,
      n_cases: 200,
      counts: { pending: 200 },
      cases: [],
    });
    render(<DoePanel />);
    await screen.findByLabelText("Uzunluk min");
    fireEvent.click(screen.getByRole("button", { name: "200'lük kalite seti" }));
    await waitFor(() => expect(startQualitySet).toHaveBeenCalledTimes(1));
    expect(startQualitySet).toHaveBeenCalledWith({
      material_ids: [3],
      run_solver: false,
      wait: false,
    });
  });
});
