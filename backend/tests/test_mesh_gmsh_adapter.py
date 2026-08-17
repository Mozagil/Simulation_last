from pathlib import Path

from app.mesh.gmsh_adapter import GmshMesherAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_STEP_FILE = FIXTURES_DIR / "box.step"


def test_preview_tessellation_maps_each_triangle_to_a_face(tmp_path):
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)
    result = adapter.preview_tessellation(geom, tmp_path / "box.stl")

    assert result.stl_path.exists()
    assert len(result.triangle_to_face) > 0

    # Kutu 6 yüzeyden oluşur, her üçgen bu 6 yüzeyden birine atanmalı.
    unique_faces = set(result.triangle_to_face)
    assert unique_faces == {1, 2, 3, 4, 5, 6}


def test_preview_tessellation_face_groups_are_planar(tmp_path):
    """Her yüzey grubundaki tüm üçgenlerin aynı düzlemde (küpün bir yüzü)
    olduğunu doğrular — triangle_to_face eşlemesinin geometrik doğruluğu.
    """
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)
    result = adapter.preview_tessellation(geom, tmp_path / "box.stl")

    stl_text = result.stl_path.read_text()
    lines = [line.strip() for line in stl_text.splitlines() if line.strip().startswith("vertex")]
    vertices = [tuple(float(v) for v in line.split()[1:4]) for line in lines]

    triangles = [vertices[i : i + 3] for i in range(0, len(vertices), 3)]
    assert len(triangles) == len(result.triangle_to_face)

    faces: dict[int, list[tuple[float, float, float]]] = {}
    for face_tag, tri in zip(result.triangle_to_face, triangles):
        faces.setdefault(face_tag, []).extend(tri)

    for face_tag, points in faces.items():
        xs = {round(p[0], 2) for p in points}
        ys = {round(p[1], 2) for p in points}
        zs = {round(p[2], 2) for p in points}
        is_planar = len(xs) == 1 or len(ys) == 1 or len(zs) == 1
        assert is_planar, f"Yüzey {face_tag} düzlemsel değil"
