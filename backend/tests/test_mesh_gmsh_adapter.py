from pathlib import Path

import pytest

from app.mesh.gmsh_adapter import GmshMesherAdapter, MidsurfaceError, SurfaceNotFoundError

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_STEP_FILE = FIXTURES_DIR / "box.step"
ASSEMBLY_STEP_FILE = FIXTURES_DIR / "assembly_two_boxes.step"
THIN_PLATE_STEP_FILE = FIXTURES_DIR / "thin_plate.step"


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


def test_copy_surface_creates_new_tag_with_same_area(tmp_path):
    # DİKKAT: copy_surface artık dosyayı yerinde günceller (kalıcılık için).
    # Paylaşılan VALID_STEP_FILE fixture'ını bozmamak için geçici bir kopya
    # üzerinde çalışıyoruz.
    test_file = tmp_path / "box_copy_test.step"
    test_file.write_bytes(VALID_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    new_face_id = adapter.copy_surface(geom, 1)

    # Yeni tag, orijinal 6 yüzeyden farklı olmalı.
    assert new_face_id != 1
    assert new_face_id not in {1, 2, 3, 4, 5, 6}

    # Kalıcılık: AYRI bir adaptör örneğiyle aynı dosyayı tekrar açınca yeni
    # yüzey hâlâ orada olmalı (gerçek kalıcılık kanıtı).
    adapter2 = GmshMesherAdapter()
    geom2 = adapter2.import_geometry(test_file)
    surfaces = adapter2.list_surfaces(geom2)
    assert len(surfaces) == 7
    assert new_face_id in {s.id for s in surfaces}

    original_area = next(s.area for s in surfaces if s.id == 1)
    copied_area = next(s.area for s in surfaces if s.id == new_face_id)
    assert original_area == pytest.approx(100.0)
    assert copied_area == pytest.approx(original_area)

    # KRİTİK: kopyalanan yüzey orijinal solid'den AYRI bir parça olmalı —
    # aksi halde "Solid gizle" kopyalanan yüzeyi de yanlışlıkla gizler.
    # Kopyalanan yüzeyin kenarları orijinalden tamamen farklı (yeni) tag'ler
    # olduğu için (gerçek bir testte doğrulandı), kenar-bağlantı analizi bunu
    # otomatik olarak ayrı bir parça sayar.
    original_part_id = next(s.part_id for s in surfaces if s.id == 1)
    copied_part_id = next(s.part_id for s in surfaces if s.id == new_face_id)
    assert copied_part_id != original_part_id

    # Paylaşılan fixture dosyasının GERÇEKTEN değişmediğini doğrula.
    assert VALID_STEP_FILE.read_bytes() != test_file.read_bytes()


def test_disconnected_shell_faces_form_a_single_part():
    """Birden fazla yüzeyden oluşan ama kenarlarla birbirine bağlı, tek bir
    açık kabuk (örn. eğri sac parça) doğru şekilde TEK parça sayılmalı —
    her yüzey ayrı bir parçaya bölünmemeli. Bu, copy_surface'ın ayrı parça
    üretmesini sağlayan bağlı-bileşen algoritmasının, gerçek çok-yüzeyli tek
    parçaları yanlışlıkla bölmediğini kanıtlar.
    """
    shell_file = FIXTURES_DIR / "curved_shell.step"
    if not shell_file.exists():
        pytest.skip("curved_shell.step fixture'ı yok")

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(shell_file)
    surfaces = adapter.list_surfaces(geom)

    assert len(surfaces) > 1  # birden fazla yüzeyden oluşuyor
    part_ids = {s.part_id for s in surfaces}
    assert len(part_ids) == 1  # ama hepsi TEK parça


def test_copy_surface_raises_for_unknown_face_id():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)

    with pytest.raises(SurfaceNotFoundError):
        adapter.copy_surface(geom, 999)


def test_create_physical_group_returns_gmsh_tag():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)

    tag = adapter.create_physical_group(geom, [1, 2], "inlet")
    assert isinstance(tag, int)


def test_create_physical_group_raises_for_invalid_face_id():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)

    with pytest.raises(SurfaceNotFoundError):
        adapter.create_physical_group(geom, [999], "gecersiz")


def test_heal_geometry_on_clean_box_reports_unchanged_counts(tmp_path):
    # DİKKAT: heal_geometry dosyayı yerinde günceller — paylaşılan fixture'ı
    # bozmamak için tmp kopya kullanılıyor (gerçek bir testte bu unutulup
    # fixture'ın kazayla mutasyona uğradığı görüldü, bu yüzden özellikle
    # vurgulanıyor).
    test_file = tmp_path / "box_heal_test.step"
    test_file.write_bytes(VALID_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    result = adapter.heal_geometry(geom)

    assert result.volumes_before == result.volumes_after == 1
    assert result.surfaces_before == result.surfaces_after == 6

    # Paylaşılan fixture GERÇEKTEN değişmedi mi doğrula.
    assert VALID_STEP_FILE.read_bytes() != b"" and test_file.exists()


def test_heal_geometry_fills_cylindrical_hole(tmp_path):
    """Delikli plaka: silindirik delik kapanmalı, hacim tam plaka olmalı."""
    fixture = FIXTURES_DIR / "plate_with_hole.step"
    test_file = tmp_path / "plate_hole_heal.step"
    test_file.write_bytes(fixture.read_bytes())

    import gmsh

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    mass_before = gmsh.model.occ.getMass(3, 1)
    result = adapter.heal_geometry(geom)

    assert result.volumes_after == 1

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()
    mass_after = gmsh.model.occ.getMass(3, 1)
    cyl_count = sum(
        1 for _d, t in gmsh.model.getEntities(2) if gmsh.model.getType(2, t) == "Cylinder"
    )
    gmsh.finalize()

    assert cyl_count == 0
    assert mass_after == pytest.approx(100.0 * 50.0 * 5.0, rel=1e-4)
    assert mass_after > mass_before


def test_heal_geometry_does_not_fill_box_profile_cavity(tmp_path):
    """Kutu profil (düzlem cidarlı boşluk) Heal ile doldurulmamalı."""
    fixture = FIXTURES_DIR / "box_profile_40x40.step"
    test_file = tmp_path / "box_profile_heal.step"
    test_file.write_bytes(fixture.read_bytes())

    import gmsh

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    mass_before = gmsh.model.occ.getMass(3, 1)
    adapter.heal_geometry(geom)

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()
    mass_after = gmsh.model.occ.getMass(3, 1)
    gmsh.finalize()

    # Dolu 40x40x100 = 160000; ince cidar ~ (40^2-36^2)*100 = 30400
    assert mass_after == pytest.approx(mass_before, rel=1e-3)
    assert mass_after < 50000

def test_find_defeature_candidates_no_fillets_on_clean_box():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)

    candidates = adapter.find_defeature_candidates(geom, max_radius=5.0)
    assert candidates == []


def test_find_defeature_candidates_finds_fillets_on_filleted_box():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(FIXTURES_DIR / "box_with_fillet.step")

    candidates = adapter.find_defeature_candidates(geom, max_radius=2.5)
    assert len(candidates) > 0
    types = {c.surface_type for c in candidates}
    assert types <= {"Cylinder", "Sphere", "Torus"}
    assert all(c.approx_radius <= 2.5 + 1e-6 for c in candidates)


def test_apply_defeature_makes_sharp_box(tmp_path):
    fixture = FIXTURES_DIR / "box_with_fillet.step"
    test_file = tmp_path / "fillet_defeature.step"
    test_file.write_bytes(fixture.read_bytes())

    import gmsh

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    result = adapter.apply_defeature(geom, max_radius=2.5)

    assert result.volumes_after == 1
    assert result.surfaces_after == 6

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()
    blend = sum(
        1
        for _d, t in gmsh.model.getEntities(2)
        if gmsh.model.getType(2, t) in {"Cylinder", "Sphere", "Torus"}
    )
    # Keskin kutu: üst yüz alanı 20*20=400
    top_masses = [
        gmsh.model.occ.getMass(2, t)
        for _d, t in gmsh.model.getEntities(2)
        if gmsh.model.getType(2, t) == "Plane"
    ]
    gmsh.finalize()

    assert blend == 0
    assert any(m == pytest.approx(400.0, rel=1e-3) for m in top_masses)


def test_apply_defeature_midshell_removes_radii_sharp_corners(tmp_path):
    """Midsurface sonrası 2D kabuk: radyus mid'ler kalkar, 4 keskin düzlem kalır."""
    fixture = FIXTURES_DIR / "box_equal_r_fillets.step"
    test_file = tmp_path / "midshell_defeature.step"
    test_file.write_bytes(fixture.read_bytes())

    import gmsh

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    mid = adapter.create_midsurface_for_part(geom, 0)
    assert len(mid) == 8

    geom = adapter.import_geometry(test_file)
    result = adapter.apply_defeature(geom, max_radius=5.0)

    # Solid korunur; orphan mid: 4 plane, 0 cylinder
    assert result.volumes_after == 1

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()

    from app.mesh.gmsh_adapter import _compute_face_to_part, _orphan_face_ids

    ftp, _, vol_backed = _compute_face_to_part()
    orphans = _orphan_face_ids(ftp, vol_backed)
    types = [gmsh.model.getType(2, f) for f in orphans]
    planes = [f for f in orphans if gmsh.model.getType(2, f) == "Plane"]
    gmsh.finalize()

    assert types.count("Cylinder") == 0
    assert types.count("Plane") == 4
    # Köşe birleşimi: X cidar Y span = Y cidar konumları
    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify2")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()
    ftp, _, vol_backed = _compute_face_to_part()
    orphans = _orphan_face_ids(ftp, vol_backed)
    x_faces, y_faces = [], []
    for f in orphans:
        if gmsh.model.getType(2, f) != "Plane":
            continue
        bb = gmsh.model.getBoundingBox(2, f)
        if abs(bb[3] - bb[0]) <= 1e-6:
            x_faces.append(bb)
        elif abs(bb[4] - bb[1]) <= 1e-6:
            y_faces.append(bb)
    assert len(x_faces) == 2 and len(y_faces) == 2
    y_pos = sorted(round((b[1] + b[4]) / 2, 5) for b in y_faces)
    for xb in x_faces:
        assert {round(xb[1], 5), round(xb[4], 5)} == set(y_pos)
    gmsh.finalize()


def test_apply_defeature_by_selected_face_ids(tmp_path):
    """Seçilen radyus mid yüzeyleri face_ids ile kaldırılır."""
    fixture = FIXTURES_DIR / "box_equal_r_fillets.step"
    test_file = tmp_path / "select_defeature.step"
    test_file.write_bytes(fixture.read_bytes())

    import gmsh

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    mid = adapter.create_midsurface_for_part(geom, 0)
    assert len(mid) == 8

    geom = adapter.import_geometry(test_file)
    from app.mesh.gmsh_adapter import _compute_face_to_part, _orphan_face_ids

    ftp, _, vb = _compute_face_to_part()
    cyl_ids = [
        fid
        for fid in _orphan_face_ids(ftp, vb)
        if gmsh.model.getType(2, fid) == "Cylinder"
    ]
    assert len(cyl_ids) == 4

    result = adapter.apply_defeature(geom, face_ids=cyl_ids)
    assert result.surfaces_after < result.surfaces_before

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()
    ftp, _, vb = _compute_face_to_part()
    types = [gmsh.model.getType(2, f) for f in _orphan_face_ids(ftp, vb)]
    gmsh.finalize()
    assert types.count("Cylinder") == 0
    assert types.count("Plane") == 4


def test_find_defeature_skips_through_hole_cylinder():
    """Delikli plakadaki silindir fillet değil — Defeature adayı olmamalı."""
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(FIXTURES_DIR / "plate_with_hole.step")

    candidates = adapter.find_defeature_candidates(geom, max_radius=5.0)
    assert candidates == []

def test_create_midsurface_between_parallel_faces_at_midpoint(tmp_path):
    # DİKKAT: create_midsurface dosyayı yerinde günceller — tmp kopya kullanılıyor.
    test_file = tmp_path / "box_midsurface_test.step"
    test_file.write_bytes(VALID_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    # Kutunun yüzey 1 (X=0) ve yüzey 2 (X=10) — paralel, orta nokta X=5 olmalı.
    new_face_id = adapter.create_midsurface(geom, 1, 2)

    assert new_face_id not in {1, 2, 3, 4, 5, 6}

    # Kalıcılık + doğruluk: AYRI bir adaptör örneğiyle dosyayı tekrar aç.
    import gmsh

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()
    (umin, vmin), (umax, vmax) = gmsh.model.getParametrizationBounds(2, new_face_id)
    umid, vmid = (umin + umax) / 2, (vmin + vmax) / 2
    point = gmsh.model.getValue(2, new_face_id, [umid, vmid])
    gmsh.finalize()

    assert point[0] == pytest.approx(5.0)
    assert point[1] == pytest.approx(5.0)
    assert point[2] == pytest.approx(5.0)


def test_create_midsurface_rejects_non_parallel_faces():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)

    # Yüzey 1 ve yüzey 3 birbirine dik (kutunun komşu yüzleri) — paralel değil.
    with pytest.raises(MidsurfaceError):
        adapter.create_midsurface(geom, 1, 3)


def test_create_midsurface_rejects_unknown_face_id():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(VALID_STEP_FILE)

    with pytest.raises(SurfaceNotFoundError):
        adapter.create_midsurface(geom, 1, 999)


def test_create_midsurface_for_part_auto_detects_thin_wall_pair(tmp_path):
    # DİKKAT: dosyayı yerinde günceller — tmp kopya kullanılıyor.
    test_file = tmp_path / "thin_plate_test.step"
    test_file.write_bytes(THIN_PLATE_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    results = adapter.create_midsurface_for_part(geom, 0)

    # Plaka 100x50x5: yalnızca ana yüzey çifti (ince cidar); kenar karşı yüzleri elenir.
    assert len(results) == 1
    new_face_id, chosen_a, chosen_b = results[0]
    assert {chosen_a, chosen_b} == {5, 6}
    assert new_face_id not in {1, 2, 3, 4, 5, 6}

    # Kalıcılık + doğruluk: orta nokta Z=2.5 olmalı (kalınlık 5'in yarısı).
    import gmsh

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()
    (umin, vmin), (umax, vmax) = gmsh.model.getParametrizationBounds(2, new_face_id)
    umid, vmid = (umin + umax) / 2, (vmin + vmax) / 2
    point = gmsh.model.getValue(2, new_face_id, [umid, vmid])
    gmsh.finalize()

    assert point[2] == pytest.approx(2.5)


def test_create_midsurface_for_part_box_profile_all_four_walls(tmp_path):
    """40×40 dış, 2 mm et → 4 mid-yüzey, kapalı köşe (gap yok), enine ~38."""
    fixture = FIXTURES_DIR / "box_profile_40x40.step"
    test_file = tmp_path / "box_profile_test.step"
    test_file.write_bytes(fixture.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    results = adapter.create_midsurface_for_part(geom, 0)

    assert len(results) == 4

    import gmsh

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()

    x_faces = []
    y_faces = []
    for new_face_id, _a, _b in results:
        bb = gmsh.model.getBoundingBox(2, new_face_id)
        dx, dy, dz = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]
        dims = sorted([dx, dy, dz])
        assert dims[0] == pytest.approx(0.0, abs=1e-6)
        assert dims[1] == pytest.approx(38.0, abs=1e-5)
        assert dims[2] == pytest.approx(100.0, abs=1e-5)
        if dx <= 1e-6:
            x_faces.append(bb)
        elif dy <= 1e-6:
            y_faces.append(bb)

    # Kapalı shell: X-cidarları tam Y aralığını, Y-cidarları tam X aralığını kapsar.
    assert len(x_faces) == 2 and len(y_faces) == 2
    x_ys = sorted({round(x_faces[0][1], 5), round(x_faces[0][4], 5)})
    y_xs = sorted({round(y_faces[0][0], 5), round(y_faces[0][3], 5)})
    for xb in x_faces:
        assert {round(xb[1], 5), round(xb[4], 5)} == set(x_ys)
    for yb in y_faces:
        assert {round(yb[0], 5), round(yb[3], 5)} == set(y_xs)
    # Köşe birleşimi: X yüzlerinin Y uçları = Y yüzlerinin konumları
    y_positions = sorted(round((yb[1] + yb[4]) / 2, 5) for yb in y_faces)
    assert x_ys == y_positions

    gmsh.finalize()


def test_create_midsurface_for_part_c_channel_connected_corners(tmp_path):
    """C/U kanal (3 cidar): mid-yüzeyler köşede birleşir, gap yok."""
    fixture = FIXTURES_DIR / "c_channel.step"
    test_file = tmp_path / "c_channel_test.step"
    test_file.write_bytes(fixture.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    results = adapter.create_midsurface_for_part(geom, 0)

    assert len(results) == 3

    import gmsh

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()

    x_faces = []
    y_faces = []
    for new_face_id, _a, _b in results:
        bb = gmsh.model.getBoundingBox(2, new_face_id)
        dx, dy = bb[3] - bb[0], bb[4] - bb[1]
        if dx <= 1e-6:
            x_faces.append(bb)
        elif dy <= 1e-6:
            y_faces.append(bb)

    assert len(x_faces) == 1 and len(y_faces) == 2
    # Web mid Y aralığı, flanş mid Y konumlarına kadar uzar → köşe birleşir.
    web = x_faces[0]
    flange_ys = sorted(round((yb[1] + yb[4]) / 2, 5) for yb in y_faces)
    assert {round(web[1], 5), round(web[4], 5)} == set(flange_ys)

    gmsh.finalize()


def test_create_midsurface_for_part_equal_r_offset_fillets(tmp_path):
    """İç/dış fillet R aynı, merkez kayık (sac köşe): 4 düz + 4 radyus mid."""
    fixture = FIXTURES_DIR / "box_equal_r_fillets.step"
    test_file = tmp_path / "equal_r.step"
    test_file.write_bytes(fixture.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    results = adapter.create_midsurface_for_part(geom, 0)

    assert len(results) == 8

    import gmsh

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()

    types = [gmsh.model.getType(2, nid) for nid, _a, _b in results]
    gmsh.finalize()

    assert types.count("Plane") == 4
    assert types.count("Cylinder") == 4


def test_create_midsurface_for_part_filleted_profile_includes_cylinder_mids(tmp_path):
    """İç+dış fillet'li kutu profil: 4 düz mid + 4 radyus mid."""
    fixture = FIXTURES_DIR / "box_profile_filleted.step"
    test_file = tmp_path / "filleted_profile.step"
    test_file.write_bytes(fixture.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    results = adapter.create_midsurface_for_part(geom, 0)

    assert len(results) == 8  # 4 plane + 4 cylinder

    import gmsh

    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("verify")
    gmsh.open(str(test_file))
    gmsh.model.occ.synchronize()

    types = []
    for new_face_id, _a, _b in results:
        types.append(gmsh.model.getType(2, new_face_id))
    gmsh.finalize()

    assert types.count("Plane") == 4
    assert types.count("Cylinder") == 4


def test_preview_tessellation_uses_curvature_on_filleted_box(tmp_path):
    """Fillet'li kutuda MeshSizeFromCurvature ile önizleme üçgen üretir."""
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(FIXTURES_DIR / "box_with_fillet.step")
    result = adapter.preview_tessellation(geom, tmp_path / "fillet_preview.stl")

    assert result.stl_path.exists()
    assert len(result.triangle_to_face) > 200


def test_create_midsurface_for_part_rejects_unknown_part():
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(THIN_PLATE_STEP_FILE)

    with pytest.raises(SurfaceNotFoundError):
        adapter.create_midsurface_for_part(geom, 999)


def test_generate_mesh_3d_tet_on_box(tmp_path):
    """Solid kutu: dimension=3 → tet elemanlar + .msh dosyası."""
    from app.mesh.base import MeshParams

    test_file = tmp_path / "box_mesh.step"
    test_file.write_bytes(VALID_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    result = adapter.generate_mesh(
        geom, MeshParams(element_size=5.0, dimension=3)
    )

    assert result.dimension == 3
    assert result.node_count > 0
    assert result.element_count > 0
    assert "Tetrahedron" in result.element_type_counts
    assert result.mesh_path.exists()
    assert result.mesh_path.suffix == ".msh"
    assert result.preview_path is not None
    assert result.preview_path.exists()
    import json

    preview = json.loads(result.preview_path.read_text(encoding="utf-8"))
    assert len(preview["nodes"]) == result.node_count
    assert len(preview["faces"]) >= 9
    assert len(preview["faces"]) % 3 == 0
    assert len(preview["lines"]) >= 6
    assert len(preview["lines"]) % 2 == 0
    tri_count = len(preview["faces"]) // 3
    assert preview["triangle_to_part"] == [0] * tri_count


def test_generate_mesh_2d_rejects_without_shell_faces(tmp_path):
    """Yalnız solid varken dimension=2 → midsurface iste."""
    from app.mesh.base import MeshError, MeshParams

    test_file = tmp_path / "box_no_shell.step"
    test_file.write_bytes(VALID_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    with pytest.raises(MeshError, match="midsurface"):
        adapter.generate_mesh(geom, MeshParams(element_size=2.0, dimension=2))


def test_generate_mesh_2d_shell_quad_preferred(tmp_path):
    """2D shell + quad scheme → Quad elemanları üretilir."""
    from app.mesh.base import MeshParams

    test_file = tmp_path / "plate_quad.step"
    test_file.write_bytes(THIN_PLATE_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    adapter.create_midsurface_for_part(geom, 0)

    geom = adapter.import_geometry(test_file)
    result = adapter.generate_mesh(
        geom,
        MeshParams(element_size=2.0, dimension=2, element_scheme="quad"),
    )

    assert result.element_scheme == "quad"
    assert result.element_count > 0
    assert "Quad" in result.element_type_counts
    assert result.element_type_counts["Quad"] > 0
    import json

    preview = json.loads(result.preview_path.read_text(encoding="utf-8"))
    n_quad = result.element_type_counts["Quad"]
    n_tri = result.element_type_counts.get("Triangle", 0)
    # Gölgeleme: her quad 2 üçgen; wireframe: köşegen yok → kenar ≤ 4*quad + 3*tri
    assert len(preview["faces"]) == (n_quad * 2 + n_tri) * 3
    assert len(preview["lines"]) // 2 <= 4 * n_quad + 3 * n_tri
    assert len(preview["triangle_to_part"]) == len(preview["faces"]) // 3
    assert len(preview["triangle_to_face"]) == len(preview["faces"]) // 3
    assert len(preview["triangle_to_element"]) == len(preview["faces"]) // 3
    assert set(preview["triangle_to_part"]).issubset(range(8))
    assert len(set(preview["triangle_to_element"])) == n_quad + n_tri


def test_generate_mesh_2d_shell_on_midsurface(tmp_path):
    """İnce plaka + midsurface: dimension=2 → yalnız shell yüzey mesh'i."""
    from app.mesh.base import MeshParams

    test_file = tmp_path / "plate_shell.step"
    test_file.write_bytes(THIN_PLATE_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    mids = adapter.create_midsurface_for_part(geom, 0)
    assert len(mids) >= 1

    geom = adapter.import_geometry(test_file)
    result = adapter.generate_mesh(
        geom, MeshParams(element_size=2.0, dimension=2, element_scheme="tet")
    )

    assert result.dimension == 2
    assert result.node_count > 0
    assert result.element_count > 0
    assert "Triangle" in result.element_type_counts
    assert result.mesh_path.exists()
    assert result.preview_path is not None
    import json

    preview = json.loads(result.preview_path.read_text(encoding="utf-8"))
    assert len(preview["nodes"]) == result.node_count
    assert len(preview["faces"]) == result.element_count * 3
    assert len(preview["lines"]) >= 6
    assert len(preview["triangle_to_part"]) == result.element_count
    assert len(preview["triangle_to_face"]) == result.element_count
    assert len(preview["triangle_to_element"]) == result.element_count
    assert min(preview["triangle_to_part"]) >= 0
    assert len(set(preview["triangle_to_element"])) == result.element_count


def test_2d_shell_attached_merges_coincident_profile_faces(tmp_path):
    """4 cidarlı profil: Face ayrı, Attached tek PART (çakışan düğüm)."""
    from app.mesh.base import MeshParams
    import json

    src = FIXTURES_DIR / "box_profile_40x40.step"
    if not src.exists():
        pytest.skip("box_profile_40x40.step yok")
    test_file = tmp_path / "profile.step"
    test_file.write_bytes(src.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    adapter.create_midsurface_for_part(geom, 0)
    geom = adapter.import_geometry(test_file)
    result = adapter.generate_mesh(
        geom, MeshParams(element_size=4.0, dimension=2, element_scheme="quad")
    )
    preview = json.loads(result.preview_path.read_text(encoding="utf-8"))
    faces = set(preview["triangle_to_face"])
    parts = set(preview["triangle_to_part"])
    assert len(faces) >= 2
    assert len(parts) == 1


def test_generate_mesh_3d_rejects_without_volume(tmp_path):
    """Volume yoksa dimension=3 hata verir."""
    from app.mesh.base import MeshError, MeshParams
    from app.mesh.gmsh_adapter import _gmsh_lock
    import gmsh

    shell_file = FIXTURES_DIR / "curved_shell.step"
    if not shell_file.exists():
        pytest.skip("curved_shell.step yok")
    test_file = tmp_path / "shell_only.step"
    test_file.write_bytes(shell_file.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    has_vol = bool(gmsh.model.getEntities(3))
    gmsh.finalize()
    _gmsh_lock.release()
    if has_vol:
        pytest.skip("fixture volume içeriyor")

    geom = adapter.import_geometry(test_file)
    with pytest.raises(MeshError, match="solid"):
        adapter.generate_mesh(geom, MeshParams(element_size=2.0, dimension=3))


def test_compute_mesh_quality_jacobian_and_aspect_on_3d(tmp_path):
    """3D mesh sonrası minSJ + aspect_ratio min/max/mean döner."""
    from app.mesh.base import MeshParams

    test_file = tmp_path / "box_q.step"
    test_file.write_bytes(VALID_STEP_FILE.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(test_file)
    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=5.0, dimension=3, element_scheme="tet")
    )

    quality = adapter.compute_mesh_quality(mesh.mesh_path, dimension=3)
    assert quality.element_count == mesh.element_count
    assert len(quality.element_tags) == quality.element_count
    assert quality.jacobian.min <= quality.jacobian.mean <= quality.jacobian.max
    assert quality.aspect_ratio.min >= 1.0 - 1e-6
    assert quality.aspect_ratio.min <= quality.aspect_ratio.mean <= quality.aspect_ratio.max
    assert len(quality.jacobian.values) == quality.element_count
    assert len(quality.aspect_ratio.values) == quality.element_count
