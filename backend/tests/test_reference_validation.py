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

import shutil
from pathlib import Path

import pytest

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
#: İlk üç doğal frekans (Hz) — E=210 GPa
EXPECTED_FREQS_HZ = (33.27, 165.49, 208.11)

TOLERANCE = 0.05


requires_ccx = pytest.mark.skipif(
    shutil.which("ccx") is None,
    reason="CalculiX (ccx) kurulu değil — bu test gerçek çözüm gerektirir",
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
    """Modal: ilk üç doğal frekans.

    Bu test aynı zamanda `*DENSITY` yolunu doğruluyor — statik çözümde
    yoğunluk hiç kullanılmaz, yani kg/m^3 -> tonne/mm^3 dönüşümündeki bir
    hata YALNIZ burada görünür. Frekans sqrt(E/rho) ile ölçeklendiği için
    1e-12 çarpanındaki bir hata anında binlerce kat sapma verir.
    """
    s = _solve_reference_case(tmp_path, modal=True)

    freqs = [s.get(f"freq_{i}") for i in range(1, 4)]
    assert all(f is not None for f in freqs), f"frekanslar eksik: {s}"

    for i, (got, expected) in enumerate(zip(freqs, EXPECTED_FREQS_HZ), start=1):
        assert got == pytest.approx(expected, rel=TOLERANCE), (
            f"Mod {i}: {got:.2f} Hz, beklenen {expected} Hz"
        )


@requires_ccx
def test_reference_modal_mode_order_is_stable(tmp_path):
    """Mod SIRASI da korunmalı.

    Mod 1 zayıf eksen eğilme, mod 2 güçlü eksen eğilme, mod 3 zayıf eksen
    2. eğilme. Frekanslar doğru ama sıra değiştiyse özdeğer çözücüsü mod
    atlamış demektir — Lanczos'ta bu her zaman garanti değildir ve
    frekansları tek tek kontrol etmek bunu yakalamaz.
    """
    s = _solve_reference_case(tmp_path, modal=True)
    freqs = [s[f"freq_{i}"] for i in range(1, 4)]
    assert freqs == sorted(freqs), f"frekanslar artan sırada değil: {freqs}"
    # Mod 2 / Mod 1 oranı ~5 (kesit atalet momentlerinin karekökü: sqrt(25))
    assert freqs[1] / freqs[0] == pytest.approx(5.0, rel=0.15)
