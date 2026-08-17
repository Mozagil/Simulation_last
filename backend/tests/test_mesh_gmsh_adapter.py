from pathlib import Path

import pytest

from app.mesh.gmsh_adapter import GmshMesherAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_STEP_FILE = FIXTURES_DIR / "box.step"
ASSEMBLY_STEP_FILE = FIXTURES_DIR / "assembly_two_boxes.step"


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


def test_single_solid_has_one_part(tmp_path):
    """Tek katılı bir dosyada part_count=1 ve tüm üçgenler part 0'a ait olmalı."""
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)
    result = adapter.preview_tessellation(geom, tmp_path / "box.stl")

    assert result.part_count == 1
    assert set(result.triangle_to_part) == {0}


def test_assembly_distinguishes_separate_parts_spatially(tmp_path):
    """İki ayrı, birbirine değmeyen katıdan oluşan bir montajda, her parçanın
    üçgenlerinin gerçekten uzamsal olarak ayrık (kesişmeyen) bölgelerde
    olduğunu doğrular — sadece part_id'lerin farklı olması yetmez, doğru
    geometriye karşılık geldiğini de kanıtlar.
    """
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(ASSEMBLY_STEP_FILE)
    result = adapter.preview_tessellation(geom, tmp_path / "assembly.stl")

    assert result.part_count == 2

    stl_text = result.stl_path.read_text()
    lines = [line.strip() for line in stl_text.splitlines() if line.strip().startswith("vertex")]
    vertices = [tuple(float(v) for v in line.split()[1:4]) for line in lines]
    triangles = [vertices[i : i + 3] for i in range(0, len(vertices), 3)]
    assert len(triangles) == len(result.triangle_to_part)

    part_x_ranges: dict[int, list[float]] = {}
    for part_id, tri in zip(result.triangle_to_part, triangles):
        xs = [v[0] for v in tri]
        lo, hi = min(xs), max(xs)
        if part_id not in part_x_ranges:
            part_x_ranges[part_id] = [lo, hi]
        else:
            part_x_ranges[part_id][0] = min(part_x_ranges[part_id][0], lo)
            part_x_ranges[part_id][1] = max(part_x_ranges[part_id][1], hi)

    assert len(part_x_ranges) == 2
    (r0_lo, r0_hi), (r1_lo, r1_hi) = (
        part_x_ranges[0],
        part_x_ranges[1],
    )
    # Kutular X ekseninde ayrık: biri diğeri başlamadan bitmeli.
    assert r0_hi <= r1_lo or r1_hi <= r0_lo


def test_list_surfaces_returns_area_and_normal_for_each_face():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)
    surfaces = adapter.list_surfaces(geom)

    assert len(surfaces) == 6
    ids = {s.id for s in surfaces}
    assert ids == {1, 2, 3, 4, 5, 6}

    # 10x10x10 kutunun her yüzeyi 100 birim kare olmalı.
    for s in surfaces:
        assert s.area == pytest.approx(100.0)
        assert s.part_id == 0
        # Normal birim vektör olmalı.
        length = sum(n * n for n in s.normal) ** 0.5
        assert length == pytest.approx(1.0)

    total_area = sum(s.area for s in surfaces)
    assert total_area == pytest.approx(600.0)


def test_list_surfaces_assigns_correct_part_id_for_assembly():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(ASSEMBLY_STEP_FILE)
    surfaces = adapter.list_surfaces(geom)

    assert len(surfaces) == 12
    part_ids = {s.part_id for s in surfaces}
    assert part_ids == {0, 1}
    # Her parça 6 yüzeyden oluşmalı (2 kutu x 6 yüz).
    part_0_faces = [s for s in surfaces if s.part_id == 0]
    part_1_faces = [s for s in surfaces if s.part_id == 1]
    assert len(part_0_faces) == 6
    assert len(part_1_faces) == 6


def test_list_edges_returns_length_and_endpoints():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)
    edges = adapter.list_edges(geom)

    # Bir kübün 12 kenarı vardır.
    assert len(edges) == 12
    for e in edges:
        assert e.length == pytest.approx(10.0)
        assert e.part_id == 0
        assert e.start_point != 0
        assert e.end_point != 0

    total_length = sum(e.length for e in edges)
    assert total_length == pytest.approx(120.0)


def test_list_edges_assigns_correct_part_id_for_assembly():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(ASSEMBLY_STEP_FILE)
    edges = adapter.list_edges(geom)

    assert len(edges) == 24
    part_ids = {e.part_id for e in edges}
    assert part_ids == {0, 1}
    assert len([e for e in edges if e.part_id == 0]) == 12
    assert len([e for e in edges if e.part_id == 1]) == 12


def test_list_points_returns_coordinates():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)
    points = adapter.list_points(geom)

    # Bir kübün 8 köşesi vardır.
    assert len(points) == 8
    for p in points:
        assert p.part_id == 0
        # Her koordinat 0 ya da 10 olmalı (10x10x10 kutu köşeleri).
        for c in p.coordinate:
            assert c == pytest.approx(0.0) or c == pytest.approx(10.0)

    # Köşeler birbirinden farklı olmalı.
    unique_coords = {p.coordinate for p in points}
    assert len(unique_coords) == 8


def test_list_points_assigns_correct_part_id_for_assembly():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(ASSEMBLY_STEP_FILE)
    points = adapter.list_points(geom)

    assert len(points) == 16
    part_ids = {p.part_id for p in points}
    assert part_ids == {0, 1}
    assert len([p for p in points if p.part_id == 0]) == 8
    assert len([p for p in points if p.part_id == 1]) == 8
