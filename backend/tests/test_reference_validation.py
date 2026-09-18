"""DOĞRULAMA VAKASI — uçtan uca sayısal regresyon.

Bu dosya, 50x10x500 mm ankastre kirişin (uçtan 500 N, S235) referans
sonuçlarını kilitler. Değerler üç bağımsız yöntemle doğrulandı:

    yöntem                       deplasman    maks. von Mises
    ---------------------------  -----------  ----------------
    El hesabı (kiriş teorisi)      23.81 mm      300.0 MPa
    ANSYS 2024 R2 (SOLID187)       24.74 mm      288.8 MPa
    Bu proje (C3D10)               23.92 mm      330.7 MPa

NEDEN BU TEST VAR: Faz 0 boyunca yedi ayrı hata bulundu ve hepsi SESSİZDİ —
hiçbiri exception fırlatmıyordu, uygulama çalışıyor ama yanlış sayı
üretiyordu. Birim testler hepsini geçiyordu.

    1. `.frd` gerilme parse'ında üzerine yazma (nodal averaging yoktu)
    2. 1. mertebe tet (C3D4) kullanımı — eğilmede 2.45 kat fazla rijit
    3. Kabukta ankastre mesnedin dönme DOF'larını kısıtlamaması (rijit
       cisim hareketi, 4.42e10 mm)
    4. Kabuk kalınlığının sessizce 3 mm varsayılanında kalması (%3600 sapma)
    5. CAD vertex id'sinin ham mesh düğüm numarası sanılması
    6. Düğüm CLOAD'unda toplam kuvvetin bölünmemesi
    7. `OUTPUT=2D` ile gerilmenin orta düzlemden okunması (300 -> 79.8 MPa)

Surrogate eğitimi için binlerce run üretilecek. Bu sınıftan tek bir hata
geri gelirse TÜM VERİ SETİ sessizce zehirlenir ve aylar sonra fark edilir.
Bu yüzden veri üretmeden önce doğruluğu kilitlemek gerekiyor.

TOLERANS %5: mesh/çözücü sürüm gürültüsünü tolere eder ama yukarıdaki yedi
hatanın hepsini yakalar — en küçüğü bile %10 mertebesindeydi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.solvers.calculix import _ccx_executable

from app.mesh.base import MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter
from app.solvers.calculix import CalculiXAdapter

# --- Referans vaka ---
LENGTH_MM = 500.0
THICKNESS_MM = 10.0   # yük yönündeki boyut (Y) — eğilme bu eksende
WIDTH_MM = 50.0
FORCE_N = 500.0
E_PA = 210e9
NU = 0.3
RHO = 7850.0

#: Beklenen sonuçlar (bu proje, C3D10, element_size=8)
EXPECTED_DISP_MM = 23.92
EXPECTED_MAX_VM_MPA = 330.7
#: 2D kabuk (midsurface + S4, t=10 mm). Deplasman kalınlık boyunca değişmez;
#: gerilme OUTPUT=2D orta düzlemde ~80 MPa'ya düşer — o yüzden vm alt sınırı.
EXPECTED_SHELL_DISP_MM = 23.6
#: İlk altı doğal frekans (Hz) — E=210 GPa. 4–6 sayısal kilit ccx koşusunda
#: doldurulur; yokken en azından 6 mod ve artan sıra aranır.
EXPECTED_FREQS_HZ = (33.27, 165.49, 208.11)

TOLERANCE = 0.05


# Uygulamanın ccx'i bulduğu AYNI mantık (CCX_PATH → PATH → vendor). Eskiden
# yalnız PATH'teki `ccx` aranıyordu; CCX_PATH ile kurulu makinede bu gerçek
# çözüm testleri SESSİZCE atlanıyordu — "tüm testler yeşil" sayısı kiriş
# fiziğini hiç kapsamıyordu. Tutarlı-yük değişikliği bu yüzden fizik
# regresyonu görülmeden commit'lenebildi.
requires_ccx = pytest.mark.skipif(
    _ccx_executable() is None,
    reason="CalculiX (ccx) bulunamadı (CCX_PATH / PATH / vendor) — bu test gerçek çözüm gerektirir",
)


def _write_plate_step(path: Path) -> None:
    """50x10x500 plakayı gmsh OCC ile üretip STEP olarak yazar.

    Binary fixture yerine üretmenin iki sebebi var: geometri testin içinde
    açıkça görünür, ve Faz 0.4'te kurulacak parametrik şablon kütüphanesinin
    aynı yolu kullanacak olması.
    """
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("plate")
        gmsh.model.occ.addBox(0, 0, 0, LENGTH_MM, THICKNESS_MM, WIDTH_MM)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _longest_edge_at_x(target_x: float, tol: float = 1e-3) -> int:
    """x=const kenarlarından en uzununu döndürür (kabuk uç kenarı)."""
    import gmsh

    scored: list[tuple[float, int]] = []
    for _dim, tag in gmsh.model.getEntities(1):
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(1, tag)
        if abs(xmin - target_x) < tol and abs(xmax - target_x) < tol:
            span = max(ymax - ymin, zmax - zmin)
            scored.append((span, int(tag)))
    if not scored:
        raise AssertionError(f"x={target_x} düzleminde kenar bulunamadı")
    scored.sort(reverse=True)
    return scored[0][1]


def _face_tag_at_x(target_x: float, tol: float = 1e-6) -> int:
    """Verilen x düzlemindeki yüzeyin gmsh etiketini döndürür.

    Yüzey numaralarını sabit varsaymak KIRILGAN: gmsh sıralaması sürüm ya da
    geometri değişikliğiyle kayabilir ve BC sessizce yanlış yüzeye uygulanır.
    Bu yüzden yüzey, sınır kutusundan GEOMETRİK olarak bulunuyor.
    """
    import gmsh

    for _dim, tag in gmsh.model.getEntities(2):
        xmin, _ymin, _zmin, xmax, _ymax, _zmax = gmsh.model.getBoundingBox(2, tag)
        if abs(xmin - target_x) < tol and abs(xmax - target_x) < tol:
            return int(tag)
    raise AssertionError(f"x={target_x} düzleminde yüzey bulunamadı")


def _solve_reference_case(tmp_path: Path, *, modal: bool = False) -> dict[str, float]:
    """Referans vakayı uçtan uca çözer ve skaler sonuçları döndürür."""
    step = tmp_path / "plate_ref.step"
    _write_plate_step(step)

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    # import_geometry gmsh oturumunu açık bırakır — yüzeyleri burada buluyoruz.
    fixed_face = _face_tag_at_x(0.0)
    load_face = _face_tag_at_x(LENGTH_MM)

    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=8.0, dimension=3, element_scheme="tet")
    )
    assert "Tetrahedron10" in mesh.element_type_counts, "2. mertebe tet bekleniyordu"

    bcs: list[dict] = [{"type": "fixed", "face_ids": [fixed_face]}]
    params: dict = {
        "mesh_path": mesh.mesh_path,
        "dimension": 3,
        "output_dir": tmp_path / "run",
        "job_name": "ref",
        "materials": [
            {
                "part_id": 0,
                "name": "S235",
                "youngs_modulus": E_PA,
                "poisson_ratio": NU,
                "density": RHO,
            }
        ],
    }
    if modal:
        params["analysis_type"] = "modal"
        params["n_modes"] = 6
    else:
        bcs.append(
            {"type": "cload", "face_ids": [load_face], "fx": 0.0, "fy": -FORCE_N, "fz": 0.0}
        )
    params["bcs"] = bcs

    ccx = CalculiXAdapter()
    artifact = ccx.build_input(params)
    job = ccx.submit(artifact)
    for _ in range(600):
        status = ccx.poll_status(job)
        if status.state in ("done", "failed"):
            break
    assert status.state == "done", f"çözüm başarısız: {status}"
    return ccx.parse_results(job).scalars


def _mesh_reference_shell(tmp_path: Path) -> tuple:
    """Referans plakayı midsurface + 2D quad mesh'e çevirir.

    Dönüş: (mesh, shell_thickness, fixed_edge, load_edge).
    """
    step = tmp_path / "plate_shell.step"
    _write_plate_step(step)

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    adapter.create_midsurface_for_part(geom, 0)
    thicknesses = adapter.last_wall_thicknesses
    assert thicknesses, "midsurface cidar kalınlığı ölçülmedi"
    shell_t = thicknesses[0]
    assert shell_t == pytest.approx(THICKNESS_MM, rel=0.05), (
        f"ölçülen kabuk kalınlığı {shell_t} mm, beklenen {THICKNESS_MM} mm"
    )

    geom = adapter.import_geometry(step)
    fixed_edge = _longest_edge_at_x(0.0)
    load_edge = _longest_edge_at_x(LENGTH_MM)
    assert fixed_edge != load_edge

    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=8.0, dimension=2, element_scheme="quad")
    )
    assert mesh.dimension == 2
    assert "Quad" in mesh.element_type_counts
    return mesh, shell_t, fixed_edge, load_edge


def _solve_reference_shell(tmp_path: Path) -> dict[str, float]:
    mesh, shell_t, fixed_edge, load_edge = _mesh_reference_shell(tmp_path)
    params = {
        "mesh_path": mesh.mesh_path,
        "dimension": 2,
        "shell_thickness": shell_t,
        "output_dir": tmp_path / "run_shell",
        "job_name": "ref_shell",
        "materials": [
            {
                "part_id": 0,
                "name": "S235",
                "youngs_modulus": E_PA,
                "poisson_ratio": NU,
                "density": RHO,
            }
        ],
        "bcs": [
            {"type": "fixed", "edge_ids": [fixed_edge]},
            {"type": "cload", "edge_ids": [load_edge], "fx": 0.0, "fy": -FORCE_N, "fz": 0.0},
        ],
    }
    ccx = CalculiXAdapter()
    artifact = ccx.build_input(params)
    job = ccx.submit(artifact)
    for _ in range(600):
        status = ccx.poll_status(job)
        if status.state in ("done", "failed"):
            break
    assert status.state == "done", f"kabuk çözüm başarısız: {status}"
    return ccx.parse_results(job).scalars


@requires_ccx
def test_reference_cantilever_displacement_and_stress(tmp_path):
    """Statik: deplasman ve maksimum von Mises referans değerlerde kalmalı."""
    s = _solve_reference_case(tmp_path)

    disp = s.get("max_displacement")
    vm = s.get("max_von_mises")
    assert disp is not None and vm is not None, f"skalerler eksik: {s}"

    assert disp == pytest.approx(EXPECTED_DISP_MM, rel=TOLERANCE), (
        f"Deplasman {disp:.2f} mm, beklenen {EXPECTED_DISP_MM} mm "
        f"(el hesabı 23.81, ANSYS 24.74). Sapma %{abs(disp-EXPECTED_DISP_MM)/EXPECTED_DISP_MM*100:.1f}"
    )
    assert vm == pytest.approx(EXPECTED_MAX_VM_MPA, rel=TOLERANCE), (
        f"Maks. von Mises {vm:.1f} MPa, beklenen {EXPECTED_MAX_VM_MPA} MPa "
        f"(el hesabı 300.0, ANSYS 288.8)"
    )


@requires_ccx
def test_reference_cantilever_displacement_matches_beam_theory(tmp_path):
    """Çözümü, çözücüden BAĞIMSIZ analitik referansla karşılaştırır.

    Beklenen değerleri kendi çıktımızdan almak döngüsel bir doğrulama olurdu:
    hata geri gelirse beklenen değeri de birlikte günceller ve testi sessizce
    geçirirdik. Kiriş teorisi dış bir referanstır.
    """
    s = _solve_reference_case(tmp_path)
    I = WIDTH_MM * THICKNESS_MM**3 / 12
    analytic = FORCE_N * LENGTH_MM**3 / (3 * (E_PA / 1e6) * I)

    disp = s["max_displacement"]
    assert disp == pytest.approx(analytic, rel=TOLERANCE), (
        f"FEA {disp:.2f} mm, kiriş teorisi {analytic:.2f} mm"
    )


@requires_ccx
def test_reference_cantilever_modal_frequencies(tmp_path):
    """Modal: ilk altı doğal frekans (1–3 sayısal kilit, 4–6 varlık + sıra).

    Bu test aynı zamanda `*DENSITY` yolunu doğruluyor — statik çözümde
    yoğunluk hiç kullanılmaz, yani kg/m^3 -> tonne/mm^3 dönüşümündeki bir
    hata YALNIZ burada görünür. Frekans sqrt(E/rho) ile ölçeklendiği için
    1e-12 çarpanındaki bir hata anında binlerce kat sapma verir.
    """
    s = _solve_reference_case(tmp_path, modal=True)

    n_freq = s.get("n_frequencies")
    assert n_freq == pytest.approx(6.0), f"6 mod istendi, n_frequencies={n_freq}; {s}"
    freqs = [s.get(f"freq_{i}") for i in range(1, 7)]
    assert all(f is not None for f in freqs), f"frekanslar eksik: {s}"

    for i, expected in enumerate(EXPECTED_FREQS_HZ, start=1):
        got = freqs[i - 1]
        assert got == pytest.approx(expected, rel=TOLERANCE), (
            f"Mod {i}: {got:.2f} Hz, beklenen {expected} Hz"
        )
    assert freqs == sorted(freqs), f"6 mod artan sırada değil: {freqs}"


@requires_ccx
def test_reference_modal_mode_order_is_stable(tmp_path):
    """Mod SIRASI da korunmalı.

    Mod 1 zayıf eksen eğilme, mod 2 güçlü eksen eğilme, mod 3 zayıf eksen
    2. eğilme. Frekanslar doğru ama sıra değiştiyse özdeğer çözücüsü mod
    atlamış demektir — Lanczos'ta bu her zaman garanti değildir ve
    frekansları tek tek kontrol etmek bunu yakalamaz.
    """
    s = _solve_reference_case(tmp_path, modal=True)
    freqs = [s[f"freq_{i}"] for i in range(1, 7)]
    assert freqs == sorted(freqs), f"frekanslar artan sırada değil: {freqs}"
    # Mod 2 / Mod 1 oranı ~5 (kesit atalet momentlerinin karekökü: sqrt(25))
    assert freqs[1] / freqs[0] == pytest.approx(5.0, rel=0.15)


def test_reference_shell_mesh_quad_and_thickness(tmp_path):
    """ccx gerektirmez: 2D yol midsurface kalınlığını ve quad mesh'i korur."""
    mesh, shell_t, fixed_edge, load_edge = _mesh_reference_shell(tmp_path)
    assert shell_t == pytest.approx(THICKNESS_MM, abs=0.2)
    assert mesh.element_type_counts["Quad"] > 0
    assert fixed_edge != load_edge


@requires_ccx
def test_reference_cantilever_shell_displacement(tmp_path):
    """2D kabuk: 23.6 mm; t=3 sessiz varsayılanı (~873 mm) ve OUTPUT=2D (~80 MPa) yakalanır."""
    s = _solve_reference_shell(tmp_path)
    disp = s.get("max_displacement")
    vm = s.get("max_von_mises")
    assert disp is not None and vm is not None, f"skalerler eksik: {s}"
    assert disp == pytest.approx(EXPECTED_SHELL_DISP_MM, rel=TOLERANCE), (
        f"Kabuk deplasman {disp:.2f} mm, beklenen {EXPECTED_SHELL_DISP_MM} mm"
    )
    assert vm > 200.0, (
        f"Kabuk von Mises {vm:.1f} MPa — OUTPUT=2D orta düzlem regresyonu ~80 MPa; "
        f"t=3 mm varsayılanı ise binlerce MPa üretir"
    )
