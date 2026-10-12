import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CompositeRosettePanel from "./CompositeRosettePanel";

vi.mock("../../api/composite", () => ({
  fetchCompositeOrientations: vi.fn(),
  putCompositeOrientation: vi.fn(),
}));

import { fetchCompositeOrientations, putCompositeOrientation } from "../../api/composite";

const SAVED = {
  id: 2,
  geometry_id: 7,
  part_id: 0,
  kind: "parallel",
  dir0: [1, 0, 0],
  origin: [0, 0, 0],
  target: "part",
  face_ids: [],
};

describe("CompositeRosettePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchCompositeOrientations).mockReset();
    vi.mocked(putCompositeOrientation).mockReset();
    vi.mocked(fetchCompositeOrientations).mockResolvedValue([SAVED]);
    vi.mocked(putCompositeOrientation).mockResolvedValue(SAVED);
  });

  it("geometri yokken kaydetmez", () => {
    render(
      <CompositeRosettePanel
        geometryId={null}
        partIds={[0]}
        selectedPartId={null}
        selectedFaceIds={[]}
      />,
    );
    expect(screen.getByText(/Geometri yükle/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rozet kaydet" })).toBeNull();
  });

  it("varsayılan global X yükler ve Kaydet PUT eder", async () => {
    const user = userEvent.setup();
    const onFiberZero = vi.fn();
    render(
      <CompositeRosettePanel
        geometryId={7}
        partIds={[0]}
        selectedPartId={0}
        selectedFaceIds={[]}
        onFiberZero={onFiberZero}
      />,
    );
    expect(await screen.findByLabelText("dir0 x")).toHaveValue("1");
    expect(screen.getByLabelText("dir0 y")).toHaveValue("0");
    expect(screen.getByText(/tür · paralel/)).toBeInTheDocument();
    await waitFor(() => {
      expect(onFiberZero).toHaveBeenCalledWith({
        origin: [0, 0, 0],
        dir: [1, 0, 0],
      });
    });
    await user.click(screen.getByRole("button", { name: "Rozet kaydet" }));
    await waitFor(() => {
      expect(putCompositeOrientation).toHaveBeenCalledTimes(1);
    });
    expect(vi.mocked(putCompositeOrientation).mock.calls[0][0]).toMatchObject({
      geometry_id: 7,
      part_id: 0,
      kind: "parallel",
      dir0: [1, 0, 0],
      target: "part",
    });
  });

  it("seçili yüzeyleri OSS'ye alır", async () => {
    const user = userEvent.setup();
    render(
      <CompositeRosettePanel
        geometryId={7}
        partIds={[0]}
        selectedPartId={0}
        selectedFaceIds={[4, 8]}
      />,
    );
    await screen.findByLabelText("OSS hedef");
    await user.selectOptions(screen.getByLabelText("OSS hedef"), "faces");
    await user.click(screen.getByRole("button", { name: "Seçimi al" }));
    expect(screen.getByText(/yüzey: 4, 8/)).toBeInTheDocument();
  });
});
