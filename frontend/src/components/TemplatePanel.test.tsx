import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TemplatePanel, { templatesForKind } from "./TemplatePanel";

vi.mock("../api/templates", () => ({
  TemplateApiError: class TemplateApiError extends Error {},
  fetchTemplates: vi.fn(),
  createGeometryFromTemplate: vi.fn(),
  downloadGeometryStep: vi.fn(),
}));

import {
  TemplateApiError,
  createGeometryFromTemplate,
  downloadGeometryStep,
  fetchTemplates,
} from "../api/templates";

const CANTILEVER = {
  id: "cantilever_beam",
  name: "Ankastre kiriş (dikdörtgen kesit)",
  description: "Test açıklama",
  tags: ["grup1"],
  params_schema: {
    properties: {
      length: {
        type: "number", default: 500, exclusiveMinimum: 0, unit: "mm", title: "Length", symbol: "L",
      },
      thickness: { type: "number", default: 10, exclusiveMinimum: 0, unit: "mm", symbol: "T" },
      width: { type: "number", default: 50, exclusiveMinimum: 0, unit: "mm", symbol: "W" },
    },
  },
  regions: [
    { name: "ankastre_uc", description: "Ankastre uç (x=0)", dim: 2 },
    { name: "yuk_yuzeyi", description: "Serbest uç (x=L)", dim: 2 },
  ],
  has_analytic: true,
  default_bcs: [
    { type: "fixed", region: "ankastre_uc" },
    { type: "cload", region: "yuk_yuzeyi", fx: 0, fy: -500, fz: 0 },
  ],
};

const CREATED = {
  geometry_id: 9,
  original_filename: "cantilever_beam.step",
  current_filename: "9.step",
  template_id: "cantilever_beam",
  template_params: { length: 500, thickness: 10, width: 50 },
  regions: { ankastre_uc: [1], yuk_yuzeyi: [2] },
  default_bcs: [
    { type: "fixed", region: "ankastre_uc", face_ids: [1] },
    { type: "cload", region: "yuk_yuzeyi", face_ids: [2], fx: 0, fy: -500, fz: 0 },
  ],
  tessellation_url: "/files/tessellations/9.stl",
  triangle_count: 12,
  face_count: 6,
  triangle_to_face: [],
  triangle_to_face_url: "",
  part_count: 1,
  triangle_to_part: [],
  triangle_to_part_url: "",
  volume_part_ids: [0],
};

describe("TemplatePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchTemplates).mockReset();
    vi.mocked(createGeometryFromTemplate).mockReset();
    vi.mocked(downloadGeometryStep).mockReset();
    vi.mocked(fetchTemplates).mockResolvedValue([CANTILEVER]);
    vi.mocked(createGeometryFromTemplate).mockResolvedValue(CREATED);
    vi.mocked(downloadGeometryStep).mockResolvedValue(undefined);
  });

  it("şema varsayılanlarını doldurur ve üretince API'ye parametre gönderir", async () => {
    const onCreated = vi.fn();
    render(
      <TemplatePanel busy={false} onCreated={onCreated} />,
    );

    expect(await screen.findByDisplayValue("500")).toBeInTheDocument();
    expect(screen.getByDisplayValue("10")).toBeInTheDocument();
    expect(screen.getByDisplayValue("50")).toBeInTheDocument();
    expect(screen.getByText("Test açıklama")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /ankastre kiriş/i }),
    ).toBeInTheDocument();
    // STEP indir artık Geometri adımında (GeometryStepDownload, TODO 11.6)
    expect(screen.queryByRole("button", { name: "STEP indir" })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Model üret" }));
    // Onay penceresi: şema, kısıt ve yük alanları
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("img", { name: /ankastre kiriş/i })).toBeInTheDocument();
    expect(within(dialog).getByText(/ankastre_uc/)).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("-500")).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "Modeli üret" }));
    await waitFor(() => expect(createGeometryFromTemplate).toHaveBeenCalledTimes(1));
    expect(createGeometryFromTemplate).toHaveBeenCalledWith("cantilever_beam", {
      length: 500,
      thickness: 10,
      width: 50,
    });
    expect(onCreated).toHaveBeenCalledWith(CREATED);
  });

  it("kullanıcı parametre değiştirince o değerleri gönderir", async () => {
    render(
      <TemplatePanel busy={false} onCreated={vi.fn()} />,
    );
    const length = await screen.findByDisplayValue("500");
    await userEvent.clear(length);
    await userEvent.type(length, "400");

    await userEvent.click(screen.getByRole("button", { name: "Model üret" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Modeli üret" }),
    );
    await waitFor(() => expect(createGeometryFromTemplate).toHaveBeenCalledTimes(1));
    expect(createGeometryFromTemplate).toHaveBeenCalledWith("cantilever_beam", {
      length: 400,
      thickness: 10,
      width: 50,
    });
  });

  it("geçersiz sayıda üretmez ve hata gösterir", async () => {
    render(
      <TemplatePanel busy={false} onCreated={vi.fn()} />,
    );
    const length = await screen.findByDisplayValue("500");
    fireEvent.change(length, { target: { value: "abc" } });

    await userEvent.click(screen.getByRole("button", { name: "Model üret" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("length geçerli bir sayı olmalı.");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(createGeometryFromTemplate).not.toHaveBeenCalled();
  });

  it("üretim API hatasını gösterir", async () => {
    vi.mocked(createGeometryFromTemplate).mockRejectedValue(new TemplateApiError("L ≥ 5T"));
    render(
      <TemplatePanel busy={false} onCreated={vi.fn()} />,
    );
    await screen.findByDisplayValue("500");
    await userEvent.click(screen.getByRole("button", { name: "Model üret" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Modeli üret" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("L ≥ 5T");
  });

  it("şablon listesi alınamazsa hata gösterir", async () => {
    vi.mocked(fetchTemplates).mockRejectedValue(new Error("network"));
    render(
      <TemplatePanel busy={false} onCreated={vi.fn()} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("network");
  });

  it("kullanıcının girdiği yük değerini bağlı BC'lere uygular", async () => {
    const onCreated = vi.fn();
    render(
      <TemplatePanel busy={false} onCreated={onCreated} />,
    );
    await screen.findByDisplayValue("500");
    await userEvent.click(screen.getByRole("button", { name: "Model üret" }));
    const dialog = await screen.findByRole("dialog");

    const fy = within(dialog).getByDisplayValue("-500");
    await userEvent.clear(fy);
    await userEvent.type(fy, "-1200");
    await userEvent.click(within(dialog).getByRole("button", { name: "Modeli üret" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    const passed = onCreated.mock.calls[0][0];
    expect(passed.default_bcs).toEqual([
      { type: "fixed", region: "ankastre_uc", face_ids: [1] },
      { type: "cload", region: "yuk_yuzeyi", face_ids: [2], fx: 0, fy: -1200, fz: 0 },
    ]);
  });

  it("geçersiz yük değerinde üretmez", async () => {
    render(
      <TemplatePanel busy={false} onCreated={vi.fn()} />,
    );
    await screen.findByDisplayValue("500");
    await userEvent.click(screen.getByRole("button", { name: "Model üret" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByDisplayValue("-500"), { target: { value: "" } });
    await userEvent.click(within(dialog).getByRole("button", { name: "Modeli üret" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Fy geçerli bir sayı olmalı.");
    expect(createGeometryFromTemplate).not.toHaveBeenCalled();
  });

  it("vazgeçince üretmez ve pencereyi kapatır", async () => {
    render(
      <TemplatePanel busy={false} onCreated={vi.fn()} />,
    );
    await screen.findByDisplayValue("500");
    await userEvent.click(screen.getByRole("button", { name: "Model üret" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Vazgeç" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(createGeometryFromTemplate).not.toHaveBeenCalled();
  });

  it("parametre etiketinde şemadaki harfi gösterir", async () => {
    render(
      <TemplatePanel busy={false} onCreated={vi.fn()} />,
    );
    const length = await screen.findByDisplayValue("500");
    const label = length.closest("label");
    expect(label).toHaveTextContent("Length");
    expect(label).toHaveTextContent("L");
    expect(label).toHaveTextContent("(mm)");
  });
});

describe("templatesForKind", () => {
  it("crash sekmesi yalnız crash etiketli şablonları, durability geri kalanını görür", () => {
    const mk = (id: string, tags: string[]) => ({ id, tags }) as unknown as Parameters<typeof templatesForKind>[0][number];
    const list = [mk("cantilever_beam", ["grup1"]), mk("crash_box_shell", ["crash", "kabuk"]), mk("plate_ball_shell", ["crash"])];
    expect(templatesForKind(list, "crash").map((t) => t.id)).toEqual(["crash_box_shell", "plate_ball_shell"]);
    expect(templatesForKind(list, "durability").map((t) => t.id)).toEqual(["cantilever_beam"]);
  });

  it("akış (cfd) sekmesi yalnız cfd etiketli şablonları (roket) görür; durability görmez", () => {
    const mk = (id: string, tags: string[]) => ({ id, tags }) as unknown as Parameters<typeof templatesForKind>[0][number];
    const list = [mk("cantilever_beam", ["grup1"]), mk("rocket", ["cfd", "roket"]), mk("crash_box_shell", ["crash"])];
    expect(templatesForKind(list, "cfd").map((t) => t.id)).toEqual(["rocket"]);
    expect(templatesForKind(list, "durability").map((t) => t.id)).toEqual(["cantilever_beam"]);
    expect(templatesForKind(list, "crash").map((t) => t.id)).toEqual(["crash_box_shell"]);
  });
});

describe("TemplatePanel · R6 .ork içe aktarma", () => {
  it("roket şablonunda .ork parametreleri forma doldurur ve notları gösterir", async () => {
    const cfd = await import("../api/cfd");
    const spy = vi.spyOn(cfd, "postRocketOrk").mockResolvedValue({
      name: "Deneme",
      params: { nose_length: 280, nose_shape: "von_karman" },
      notes: ["2 gövde tüpü tek tüp olarak birleştirildi (toplam boy)."],
      valid: true,
    });
    const ROCKET = {
      ...CANTILEVER,
      id: "rocket",
      name: "Roket",
      tags: ["cfd"],
      regions: [],
      default_bcs: [],
      params_schema: {
        properties: {
          nose_shape: { type: "string", enum: ["ogive", "von_karman"], default: "ogive", title: "Burun" },
          nose_length: { type: "number", default: 300, exclusiveMinimum: 0, unit: "mm", symbol: "Ln" },
        },
      },
    };
    vi.mocked(fetchTemplates).mockResolvedValue([ROCKET] as never);
    render(<TemplatePanel busy={false} onCreated={vi.fn()} kind="cfd" />);
    const input = await screen.findByLabelText("OpenRocket dosyası");
    fireEvent.change(input, { target: { files: [new File(["x"], "d.ork")] } });
    await waitFor(() => expect(screen.getByTestId("ork-notes")).toHaveTextContent("2 parametre dolduruldu"));
    expect(spy).toHaveBeenCalled();
    expect(screen.getByDisplayValue("280")).toBeInTheDocument();
    spy.mockRestore();
  });
  it("1.23 A6: crash sekmesinde şablonun durability BC'leri gösterilmez ve yüklenmez", async () => {
    const TAYLOR = {
      ...CANTILEVER,
      id: "taylor_bar",
      name: "Taylor çubuğu",
      tags: ["crash"],
      default_bcs: [{ type: "pressure", region: "on_yuz", magnitude: 10 }],
    };
    vi.mocked(fetchTemplates).mockResolvedValue([TAYLOR]);
    vi.mocked(createGeometryFromTemplate).mockResolvedValue({
      ...CREATED,
      template_id: "taylor_bar",
      default_bcs: [{ type: "pressure", region: "on_yuz", face_ids: [3], magnitude: 10 }],
    });
    const onCreated = vi.fn();
    render(<TemplatePanel busy={false} onCreated={onCreated} kind="crash" />);
    await userEvent.click(await screen.findByRole("button", { name: "Model üret" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText("Basınç (MPa)")).toBeNull();
    expect(within(dialog).getByTestId("template-dialog-note")).toHaveTextContent("4 · Crash");
    await userEvent.click(within(dialog).getByRole("button", { name: "Modeli üret" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(vi.mocked(onCreated).mock.calls[0][0].default_bcs).toEqual([]);
  });
});
