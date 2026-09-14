import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TemplatePanel from "./TemplatePanel";

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
      length: { type: "number", default: 500, exclusiveMinimum: 0, unit: "mm", title: "Length" },
      thickness: { type: "number", default: 10, exclusiveMinimum: 0, unit: "mm" },
      width: { type: "number", default: 50, exclusiveMinimum: 0, unit: "mm" },
    },
  },
  regions: [],
  has_analytic: true,
};

const CREATED = {
  geometry_id: 9,
  original_filename: "cantilever_beam.step",
  current_filename: "9.step",
  template_id: "cantilever_beam",
  template_params: { length: 500, thickness: 10, width: 50 },
  regions: {},
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
      <TemplatePanel geometryId={null} geometryFilename={null} busy={false} onCreated={onCreated} />,
    );

    expect(await screen.findByDisplayValue("500")).toBeInTheDocument();
    expect(screen.getByDisplayValue("10")).toBeInTheDocument();
    expect(screen.getByDisplayValue("50")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /ankastre kiriş/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "STEP indir" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Geometri üret" }));
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
      <TemplatePanel geometryId={null} geometryFilename={null} busy={false} onCreated={vi.fn()} />,
    );
    const length = await screen.findByDisplayValue("500");
    await userEvent.clear(length);
    await userEvent.type(length, "400");

    await userEvent.click(screen.getByRole("button", { name: "Geometri üret" }));
    await waitFor(() => expect(createGeometryFromTemplate).toHaveBeenCalledTimes(1));
    expect(createGeometryFromTemplate).toHaveBeenCalledWith("cantilever_beam", {
      length: 400,
      thickness: 10,
      width: 50,
    });
  });

  it("geçersiz sayıda üretmez ve hata gösterir", async () => {
    render(
      <TemplatePanel geometryId={null} geometryFilename={null} busy={false} onCreated={vi.fn()} />,
    );
    const length = await screen.findByDisplayValue("500");
    fireEvent.change(length, { target: { value: "abc" } });

    await userEvent.click(screen.getByRole("button", { name: "Geometri üret" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("length geçerli bir sayı olmalı.");
    expect(createGeometryFromTemplate).not.toHaveBeenCalled();
  });

  it("üretim API hatasını gösterir", async () => {
    vi.mocked(createGeometryFromTemplate).mockRejectedValue(new TemplateApiError("L ≥ 5T"));
    render(
      <TemplatePanel geometryId={null} geometryFilename={null} busy={false} onCreated={vi.fn()} />,
    );
    await screen.findByDisplayValue("500");
    await userEvent.click(screen.getByRole("button", { name: "Geometri üret" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("L ≥ 5T");
  });

  it("geometri varken STEP indir API'sini çağırır", async () => {
    render(
      <TemplatePanel
        geometryId={9}
        geometryFilename="9.step"
        busy={false}
        onCreated={vi.fn()}
      />,
    );
    await screen.findByDisplayValue("500");
    const download = screen.getByRole("button", { name: "STEP indir" });
    expect(download).toBeEnabled();
    await userEvent.click(download);
    await waitFor(() => expect(downloadGeometryStep).toHaveBeenCalledTimes(1));
    expect(downloadGeometryStep).toHaveBeenCalledWith(9, "9.step");
  });

  it("STEP indirme hatasını gösterir", async () => {
    vi.mocked(downloadGeometryStep).mockRejectedValue(new TemplateApiError("STEP indirilemedi (HTTP 404)."));
    render(
      <TemplatePanel geometryId={9} geometryFilename="9.step" busy={false} onCreated={vi.fn()} />,
    );
    await screen.findByDisplayValue("500");
    await userEvent.click(screen.getByRole("button", { name: "STEP indir" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("STEP indirilemedi (HTTP 404).");
  });

  it("şablon listesi alınamazsa hata gösterir", async () => {
    vi.mocked(fetchTemplates).mockRejectedValue(new Error("network"));
    render(
      <TemplatePanel geometryId={null} geometryFilename={null} busy={false} onCreated={vi.fn()} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("network");
  });
});
