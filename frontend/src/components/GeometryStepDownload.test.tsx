import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GeometryStepDownload from "./GeometryStepDownload";

vi.mock("../api/templates", () => ({
  TemplateApiError: class TemplateApiError extends Error {},
  downloadGeometryStep: vi.fn(),
}));

import { downloadGeometryStep, TemplateApiError } from "../api/templates";

describe("GeometryStepDownload (TODO 11.6)", () => {
  beforeEach(() => {
    vi.mocked(downloadGeometryStep).mockReset().mockResolvedValue(undefined);
  });

  it("yüklü geometrinin STEP'ini indirir", async () => {
    render(<GeometryStepDownload geometryId={9} filename="cantilever_beam.step" />);
    const btn = screen.getByRole("button", { name: "STEP indir" });
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    await waitFor(() => expect(downloadGeometryStep).toHaveBeenCalledWith(9, "cantilever_beam.step"));
  });

  it("dosya adı yoksa geometry-<id>.step", async () => {
    render(<GeometryStepDownload geometryId={12} filename={null} />);
    await userEvent.click(screen.getByRole("button", { name: "STEP indir" }));
    await waitFor(() => expect(downloadGeometryStep).toHaveBeenCalledWith(12, "geometry-12.step"));
  });

  it("hata mesajını gösterir; meşgulken kapalı", async () => {
    vi.mocked(downloadGeometryStep).mockRejectedValue(new TemplateApiError("STEP indirilemedi (HTTP 404)."));
    const { rerender } = render(<GeometryStepDownload geometryId={9} filename="9.step" />);
    await userEvent.click(screen.getByRole("button", { name: "STEP indir" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("STEP indirilemedi (HTTP 404).");
    rerender(<GeometryStepDownload geometryId={9} filename="9.step" disabled />);
    expect(screen.getByRole("button", { name: "STEP indir" })).toBeDisabled();
  });
});
