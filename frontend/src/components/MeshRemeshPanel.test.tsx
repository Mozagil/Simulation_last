import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import MeshRemeshPanel from "./MeshRemeshPanel";

function Harness({ selected, onRemesh }: { selected: number[]; onRemesh: (s: Record<number, number>) => void }) {
  const [sizes, setSizes] = useState<Record<number, number>>({});
  return (
    <MeshRemeshPanel
      selectedFaceIds={selected}
      faceSizes={sizes}
      onChange={setSizes}
      onRemesh={onRemesh}
      globalSize="8"
      hasMesh
    />
  );
}

describe("MeshRemeshPanel", () => {
  it("seçili yüzeylere yerel boyut uygular ve remesh çağırır; liste silinebilir", () => {
    const onRemesh = vi.fn();
    render(<Harness selected={[3, 5]} onRemesh={onRemesh} />);
    expect(screen.getByText("2 yüzey seçili")).toBeInTheDocument();
    const apply = screen.getByRole("button", { name: "Seçili yüzeylere uygula + remesh" });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Yerel eleman boyutu"), { target: { value: "3" } });
    fireEvent.click(apply);
    expect(onRemesh).toHaveBeenCalledWith({ 3: 3, 5: 3 });
    expect(screen.getByText("yüzey 5 · 3 mm")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yüzey 5 yerel boyutunu kaldır" }));
    expect(screen.queryByText("yüzey 5 · 3 mm")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tümünü yeniden mesh'le" }));
    expect(onRemesh).toHaveBeenLastCalledWith({ 3: 3 });
  });

  it("seçim yoksa uygulanamaz", () => {
    render(<Harness selected={[]} onRemesh={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Yerel eleman boyutu"), { target: { value: "3" } });
    expect(screen.getByRole("button", { name: "Seçili yüzeylere uygula + remesh" })).toBeDisabled();
    expect(screen.getByText("yüzey seçilmedi")).toBeInTheDocument();
  });
});

describe("MeshRemeshPanel — mesh sil", () => {
  it("mesh varken sil çağrılır; mesh yoksa pasif", () => {
    const onDelete = vi.fn();
    const { rerender } = render(
      <MeshRemeshPanel selectedFaceIds={[]} faceSizes={{}} onChange={() => undefined} onRemesh={() => undefined} globalSize="5" hasMesh onDelete={onDelete} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Mesh'i sil" }));
    expect(onDelete).toHaveBeenCalled();
    rerender(
      <MeshRemeshPanel selectedFaceIds={[]} faceSizes={{}} onChange={() => undefined} onRemesh={() => undefined} globalSize="5" hasMesh={false} onDelete={onDelete} />,
    );
    expect(screen.getByRole("button", { name: "Mesh'i sil" })).toBeDisabled();
  });
});
