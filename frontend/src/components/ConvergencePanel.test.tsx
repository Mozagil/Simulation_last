import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ConvergencePanel from "./ConvergencePanel";

vi.mock("../api/convergence", async () => {
  const actual = await vi.importActual<typeof import("../api/convergence")>(
    "../api/convergence",
  );
  return { ...actual, runConvergence: vi.fn() };
});

vi.mock("../api/materials", () => ({ fetchMaterials: vi.fn() }));
vi.mock("../api/templates", () => ({ fetchTemplates: vi.fn() }));

import { parseNumberList, runConvergence } from "../api/convergence";
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
      width: { type: "number", default: 50, unit: "mm", title: "Genişlik", symbol: "W" },
    },
  },
  regions: [],
  has_analytic: true,
  default_element_ratio: [0.5, 1.2] as [number, number],
  has_characteristic_length: true,
  default_bcs: [],
};

const S235 = { id: 1, name: "S235", youngs_modulus: 210e9, poisson_ratio: 0.3 };

function row(index: number, es: number, nodes: number, u: number, vm: number) {
  return {
    index,
    element_size: es,
    ratio: es / 10,
    run_id: 900 + index,
    status: "solved",
    message: null,
    node_count: nodes,
    element_count: nodes * 3,
    targets: {
      max_displacement: {
        value: u,
        delta_prev_pct: index === 0 ? null : 0.5,
        delta_finest_pct: 1.0,
      },
      max_von_mises: {
        value: vm,
        delta_prev_pct: index === 0 ? null : -10.48,
        delta_finest_pct: 7.11,
      },
    },
    analytic: {
      skipped: false,
      reason: null,
      warned: false,
      metrics: [
        {
          key: "max_displacement",
          label: "Max deplasman",
          unit: "mm",
          analytic: 23.8095,
          fea: u,
          rel_error: 0.007,
          warn: false,
        },
      ],
    },
  };
}

const REPORT = {
  n_steps: 2,
  n_solved: 2,
  targets: ["max_displacement", "max_von_mises"],
  summary: {
    max_displacement: {
      finest: 23.717,
      finest_element_size: 3,
      finest_node_count: 79962,
      last_step_delta_pct: -0.14,
    },
    max_von_mises: {
      finest: 327.17,
      finest_element_size: 3,
      finest_node_count: 79962,
      last_step_delta_pct: 1.82,
    },
  },
  rows: [row(0, 15, 2407, 23.99, 350.43), row(1, 3, 79962, 23.717, 327.17)],
  geometry_id: 42,
  template_id: "cantilever_beam",
  template_params: { length: 500, thickness: 10, width: 50 },
  material: { id: 1, name: "S235", youngs_modulus: 210e9 },
  name: "yakinsama cantilever_beam",
};

describe("ConvergencePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchTemplates).mockResolvedValue([CANTILEVER] as never);
    vi.mocked(fetchMaterials).mockResolvedValue([S235] as never);
    vi.mocked(runConvergence).mockReset();
  });

  it("şablonun sayısal parametrelerini varsayılanlarıyla doldurur", async () => {
    render(<ConvergencePanel />);
    const length = (await screen.findByLabelText(/L · Uzunluk/)) as HTMLInputElement;
    expect(length.value).toBe("500");
    expect((screen.getByLabelText(/T · Kalınlık/) as HTMLInputElement).value).toBe("10");
  });

  it("oran modunda basamakları element_ratios olarak gönderir", async () => {
    vi.mocked(runConvergence).mockResolvedValue(REPORT as never);
    render(<ConvergencePanel />);
    await screen.findByLabelText(/L · Uzunluk/);

    fireEvent.change(screen.getByLabelText(/Basamaklar/), {
      target: { value: "1.2, 0.8, 0.4" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Taramayı başlat/ }));

    await waitFor(() => expect(runConvergence).toHaveBeenCalled());
    const body = vi.mocked(runConvergence).mock.calls[0][0];
    expect(body.template_id).toBe("cantilever_beam");
    expect(body.material_id).toBe(1);
    expect(body.element_ratios).toEqual([1.2, 0.8, 0.4]);
    expect(body.element_sizes).toBeUndefined();
    expect(body.params).toEqual({ length: 500, thickness: 10, width: 50 });
  });

  it("mutlak moda geçince element_sizes gönderir", async () => {
    vi.mocked(runConvergence).mockResolvedValue(REPORT as never);
    render(<ConvergencePanel />);
    await screen.findByLabelText(/L · Uzunluk/);

    fireEvent.change(screen.getByLabelText(/Basamak tipi/), { target: { value: "mm" } });
    fireEvent.change(screen.getByLabelText(/Basamaklar/), { target: { value: "12, 6" } });
    fireEvent.click(screen.getByRole("button", { name: /Taramayı başlat/ }));

    await waitFor(() => expect(runConvergence).toHaveBeenCalled());
    const body = vi.mocked(runConvergence).mock.calls[0][0];
    expect(body.element_sizes).toEqual([12, 6]);
    expect(body.element_ratios).toBeUndefined();
  });

  it("tek basamakla tarama başlatılamaz", async () => {
    render(<ConvergencePanel />);
    await screen.findByLabelText(/L · Uzunluk/);
    fireEvent.change(screen.getByLabelText(/Basamaklar/), { target: { value: "0.8" } });
    expect(screen.getByRole("button", { name: /Taramayı başlat/ })).toBeDisabled();
    expect(screen.getByText(/En az 2 basamak gerekir/)).toBeInTheDocument();
  });

  it("sonuç tablosunu ve sapma sütunlarını gösterir", async () => {
    vi.mocked(runConvergence).mockResolvedValue(REPORT as never);
    const { container } = render(<ConvergencePanel />);
    await screen.findByLabelText(/L · Uzunluk/);
    fireEvent.click(screen.getByRole("button", { name: /Taramayı başlat/ }));

    await screen.findByText(/2\/2 basamak çözüldü/);
    expect(screen.getByText("23.990")).toBeInTheDocument();
    expect(screen.getByText("350.430")).toBeInTheDocument();
    expect(screen.getByText("-10.48%")).toBeInTheDocument();
    // Analitik referans özet satırında görünür (şablonun kapalı form çözümü).
    // Satır birden çok metin düğümüne bölündüğü için textContent üzerinden bakılır.
    const summary = container.querySelector(".convergence-summary li");
    expect(summary?.textContent).toContain("analitik 23.8");
    expect(summary?.textContent).toContain("son iki basamak arası -0.14%");
    // İki hedef = iki grafik.
    expect(screen.getAllByRole("img", { name: /yakınsama eğrisi/ })).toHaveLength(2);
  });

  it("hata mesajını gösterir ve tabloyu açmaz", async () => {
    vi.mocked(runConvergence).mockRejectedValue(new Error("ccx bulunamadı"));
    render(<ConvergencePanel />);
    await screen.findByLabelText(/L · Uzunluk/);
    fireEvent.click(screen.getByRole("button", { name: /Taramayı başlat/ }));

    await screen.findByText("ccx bulunamadı");
    expect(screen.queryByText(/basamak çözüldü/)).not.toBeInTheDocument();
  });
});

describe("parseNumberList", () => {
  it("virgül/boşluk ayırır, geçersiz ve pozitif olmayanı atar", () => {
    expect(parseNumberList("1.5, 1.2 0.8;0.4")).toEqual([1.5, 1.2, 0.8, 0.4]);
    expect(parseNumberList("1, abc, -2, 0, 3")).toEqual([1, 3]);
    expect(parseNumberList("   ")).toEqual([]);
  });
});
