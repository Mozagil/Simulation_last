"""0.6.4 — `*PLASTIC` malzeme kartı: eğri türetme, kart yazımı, artımlı adım, gerçek ccx.

Kütüphanede Re/Rm/A% var, eğri yok → iki noktalı izotropik pekleşme (gerçek
gerilme/şekil değiştirmeye çevrilmiş). Varsayılan KAPALI: plasticity=False ile
.inp eskisiyle birebir.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.api.solve import SolveRequest
from app.materials.plasticity import bilinear_plastic_curve, plastic_table_for_material
from app.solvers.calculix import CalculiXAdapter, _ccx_executable, _static_step_block

FIXTURES = Path(__file__).parent / "fixtures"
requires_ccx = pytest.mark.skipif(_ccx_executable() is None, reason="CalculiX (ccx) bulunamadı")


# --- eğri -------------------------------------------------------------------------


def test_s235_iki_nokta_gercek_gerilme():
    rows = bilinear_plastic_curve(235e6, 360e6, 26.0, 210e9)
    assert rows[0] == (235.0, 0.0)
    su_true, eps_p = rows[1]
    assert su_true == pytest.approx(360 * 1.26)                      # σ_true = σ(1+ε)
    assert eps_p == pytest.approx(math.log1p(0.26) - su_true / 210e3, rel=1e-9)
    assert 0.2 < eps_p < 0.24 and su_true > 235.0


def test_uzama_yoksa_mukemmel_plastik_ve_akma_yoksa_bos():
    assert bilinear_plastic_curve(235e6, 360e6, None, 210e9) == [(235.0, 0.0)]
    assert bilinear_plastic_curve(0.0, 360e6, 26.0, 210e9) == []


def test_acik_egri_oncelikli_ve_dogrulanir():
    m = {"yield_strength": 235e6, "ultimate_strength": 360e6, "elongation": 26.0,
         "youngs_modulus": 210e9, "plastic_curve": [[235, 0.0], [300, 0.05], [400, 0.2]]}
    assert plastic_table_for_material(m) == [(235.0, 0.0), (300.0, 0.05), (400.0, 0.2)]
    with pytest.raises(ValueError):
        plastic_table_for_material({**m, "plastic_curve": [[235, 0.01]]})


# --- adaptör ----------------------------------------------------------------------


@pytest.fixture()
def box_mesh(tmp_path):
    from app.mesh.base import MeshParams
    from app.mesh.gmsh_adapter import GmshMesherAdapter

    ad = GmshMesherAdapter()
    return ad.generate_mesh(ad.import_geometry(FIXTURES / "box.step"),
                            MeshParams(element_size=5.0, dimension=3, element_scheme="tet")).mesh_path


def _params(tmp_path, plastic, mesh_path):
    mat = {"part_id": 0, "name": "S235", "youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}
    if plastic:
        mat["plastic"] = [(235.0, 0.0), (453.6, 0.229)]
    return {
        "mesh_path": mesh_path, "dimension": 3, "output_dir": tmp_path,
        "job_name": "pl", "materials": [mat], "plastic": plastic,
        "bcs": [{"type": "fixed", "face_ids": [1]}, {"type": "cload", "face_ids": [2], "fx": 0, "fy": -10.0, "fz": 0}],
    }


def test_plastic_karti_ve_artimli_adim_yazilir(tmp_path, box_mesh):
    art = CalculiXAdapter().build_input(_params(tmp_path, True, box_mesh))
    text = art.path.read_text(encoding="utf-8")
    assert "*ELASTIC" in text and "*PLASTIC" in text
    i = text.index("*PLASTIC")
    assert "235, 0" in text[i:i + 60] and "453.6, 0.229" in text[i:i + 80]
    assert "*STEP, INC=" in text and "NLGEOM" not in text  # artımlı ama küçük deformasyon


def test_plasticity_kapaliyken_inp_degismez(tmp_path, box_mesh):
    text = CalculiXAdapter().build_input(_params(tmp_path, False, box_mesh)).path.read_text(encoding="utf-8")
    assert "*PLASTIC" not in text and "*STEP\n*STATIC" in text.replace("\r", "")


def test_step_block_plastic_ve_nlgeom_bagimsiz():
    p = _static_step_block("", 3, plastic=True, n_increments=10)
    assert p.startswith("*STEP, INC=") and "NLGEOM" not in p
    both = _static_step_block("", 3, nlgeom=True, plastic=True)
    assert both.startswith("*STEP, NLGEOM, INC=")
    assert SolveRequest(dimension=3, bcs=[]).plasticity is False


# --- gerçek ccx: akma sonrası gerilme eğriye yapışır ---------------------------------


@requires_ccx
def test_ccx_plastik_kiris_akmayi_asmaz(tmp_path):
    """500×10×50 S235, 650 N: lineer σ ≈ 390 MPa (> Re), sehim lineerden belirgin büyük.

    Yük seçimi (ölçüldü, es=8): ilk akma F_y = Re·W·T²/(6L) = 392 N;
    450 N'da fark yok (akma yalnız yüzeyde), 550 N +2%, 600 N +7%,
    **650 N +31%** sehim (40.6 vs 31.1 mm); 800 N'da 535 mm (rijit-plastik
    çökme 587 N'ı geçmiş, küçük deformasyon formülasyonu sınırsız uzatıyor);
    1500 N'da çözücü 0.888 yükte "increment size smaller than minimum" ile
    DURDU — limit yük aşıldı, yük kontrolü bulamaz (0.6.4 deplasman kontrolü
    maddesi). Gerilme: pekleşme dik (235→454 MPa, ε_p 0.23) olduğu için
    orta yüklerde lineere yakın kalır; düğüme dış değerleme tekil köşede
    tablonun son noktasını %5–20 aşabilir (ham tepe), %95 persentil doyar.
    """
    from app.mesh.base import MeshParams
    from app.mesh.gmsh_adapter import GmshMesherAdapter
    from app.templates import get_template
    from app.templates.base import build_template

    t = get_template("cantilever_beam")
    built = build_template(t, t.parse_params({}), tmp_path / "b.step")
    ad = GmshMesherAdapter()
    mesh = ad.generate_mesh(ad.import_geometry(built.step_path),
                            MeshParams(element_size=8.0, dimension=3, element_scheme="tet"))
    mat = {"part_id": 0, "name": "S235", "youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0,
           "plastic": bilinear_plastic_curve(235e6, 360e6, 26.0, 210e9)}
    ccx = CalculiXAdapter()
    job = ccx.submit(ccx.build_input({
        "mesh_path": mesh.mesh_path, "dimension": 3, "output_dir": tmp_path / "run", "job_name": "pl",
        "materials": [mat], "plastic": True, "n_increments": 20,
        "bcs": [{"type": "fixed", "face_ids": built.regions["ankastre_uc"]},
                {"type": "cload", "face_ids": built.regions["yuk_yuzeyi"], "fx": 0.0, "fy": -650.0, "fz": 0.0}],
    }))
    for _ in range(100000):
        st = ccx.poll_status(job)
        if st.state in ("done", "failed"):
            break
    assert st.state == "done", st
    s = ccx.parse_results(job).scalars
    assert s["_solver_converged"] == 1.0
    u_lin = 650.0 * 500.0**3 / (3.0 * 210e3 * (50.0 * 10.0**3 / 12.0))  # 31.0 mm
    assert s["max_displacement"] > 1.2 * u_lin          # plastik: ölçülen 40.6 (+31%)
    assert s["max_displacement"] < 3.0 * u_lin          # çökme değil
    assert 235.0 < s["max_von_mises"] < 454.0 * 1.10    # eğrinin üstüne çıkmaz (dış değerleme payı)
    assert s["_n_increments"] >= 20 and s.get("_n_cutbacks", 0) == 0


# --- 0.6.4 (2–3): tepki kuvveti, limit yük, PEEQ ------------------------------------

def _frd_line(nid: int, *vals: float) -> str:
    """Gerçek .frd sabit sütunları: ' -1' + 10 karakter id + 12 karakterlik değerler."""
    return f" -1{nid:>10d}" + "".join(f"{v:12.5E}" for v in vals)


def _frd_block(name: str, ncomp: int, time: float, rows: list[tuple]) -> str:
    return (
        f"  100CL  101 {time:.9E}       3                     0    1\n"
        f" -4  {name:<10s}{ncomp:5d}    1\n"
        + "".join(_frd_line(*r) + "\n" for r in rows)
        + " -3\n"
    )


_FRD_SNIPPET = (
    "    1C\n    2C                                                                  3\n"
    + _frd_line(1, 0.0, 0.0, 0.0) + "\n" + _frd_line(2, 1.0, 0.0, 0.0) + "\n"
    + _frd_line(3, 2.0, 0.0, 0.0) + "\n -3\n"
    + _frd_block("DISP", 4, 0.5, [(1, 0.0, 0.0, 0.0), (2, 0.5, 0.0, 0.0), (3, 1.0, 0.0, 0.0)])
    + _frd_block("FORC", 4, 0.5, [(1, -100.0, 0.0, 0.0), (3, 100.0, 0.0, 0.0)])
    + _frd_block("PE", 1, 0.5, [(2, 1e-3), (3, 3e-3)])
    + _frd_block("DISP", 4, 1.0, [(1, 0.0, 0.0, 0.0), (2, 1.0, 0.0, 0.0), (3, 2.0, 0.0, 0.0)])
    + _frd_block("FORC", 4, 1.0, [(1, -150.0, 0.0, 0.0), (3, 150.0, 0.0, 0.0)])
    + _frd_block("PE", 1, 1.0, [(2, 2e-3), (3, 8e-3)])
    + " 9999\n"
)


def test_frd_forc_pe_ve_zaman_okunur(tmp_path):
    from app.solvers.calculix import _parse_frd

    f = tmp_path / "x.frd"
    f.write_text(_FRD_SNIPPET, encoding="utf-8")
    d = _parse_frd(f)
    assert d["times"] == [0.5, 1.0]
    assert len(d["force_increments"]) == 2 and d["force_increments"][1][1] == (-150.0, 0.0, 0.0)
    assert d["peeq_increments"][-1] == {2: 0.002, 3: 0.008}
    assert d["displacement"][3] == (2.0, 0.0, 0.0)


def test_step_ciktilari_rf_ve_peeq():
    lin = _static_step_block("", 3)
    assert "U\n*EL FILE" in lin.replace("\r", "") and "RF" not in lin and "PEEQ" not in lin
    pl = _static_step_block("", 3, plastic=True)
    assert "U, RF" in pl and "S, PEEQ" in pl
    nl = _static_step_block("", 3, nlgeom=True)
    assert "U, RF" in nl and "PEEQ" not in nl
    forced = _static_step_block("", 3, reaction=True)
    assert "U, RF" in forced and "*STEP\n*STATIC" in forced.replace("\r", "")


def _beam_job(tmp_path, bcs, *, plastic, n_inc, reaction=None):
    from app.mesh.base import MeshParams
    from app.mesh.gmsh_adapter import GmshMesherAdapter
    from app.templates import get_template
    from app.templates.base import build_template

    t = get_template("cantilever_beam")
    built = build_template(t, t.parse_params({}), tmp_path / "b.step")
    ad = GmshMesherAdapter()
    mesh = ad.generate_mesh(ad.import_geometry(built.step_path),
                            MeshParams(element_size=8.0, dimension=3, element_scheme="tet"))
    mat = {"part_id": 0, "name": "S235", "youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}
    if plastic:
        mat["plastic"] = bilinear_plastic_curve(235e6, 360e6, 26.0, 210e9)
    ccx = CalculiXAdapter()
    job = ccx.submit(ccx.build_input({
        "mesh_path": mesh.mesh_path, "dimension": 3, "output_dir": tmp_path / "run", "job_name": "dc",
        "materials": [mat], "plastic": plastic, "n_increments": n_inc, "reaction": reaction,
        "bcs": [dict(b, face_ids=built.regions[b.pop("region")]) for b in bcs],
    }))
    for _ in range(100000):
        st = ccx.poll_status(job)
        if st.state in ("done", "failed"):
            break
    assert st.state == "done", st
    return ccx.parse_results(job)


@requires_ccx
def test_ccx_deplasman_kontrolu_tepki_kuvveti_teoriyle(tmp_path):
    """Lineer kiriş, uca −20 mm dayatılır: sabit uç tepkisi 3EIu/L³ = 420 N."""
    rs = _beam_job(tmp_path, [{"type": "fixed", "region": "ankastre_uc"},
                              {"type": "displacement", "region": "yuk_yuzeyi", "dofs": {"2": -20.0}}],
                   plastic=False, n_inc=1, reaction=True)
    assert rs.scalars["reaction_force_n"] == pytest.approx(420.0, rel=0.01)   # ölçüldü 418.1
    assert rs.scalars["reaction_fy"] == pytest.approx(420.0, rel=0.01)
    assert "max_peeq" not in rs.scalars


@requires_ccx
def test_ccx_plastik_deplasman_kontrolu_limit_yuk(tmp_path):
    """Plastik kiriş, uca −120 mm: tepki eğrisi plato yapar → limit yük.
    Ölçüldü: 704 N (rijit-plastik 587 N, pekleşmeyle üstü), ilk akma ~392 N."""
    rs = _beam_job(tmp_path, [{"type": "fixed", "region": "ankastre_uc"},
                              {"type": "displacement", "region": "yuk_yuzeyi", "dofs": {"2": -120.0}}],
                   plastic=True, n_inc=24)
    s = rs.scalars
    assert s["_solver_converged"] == 1.0
    assert 587.0 < s["limit_load_n"] < 800.0
    assert s["limit_load_factor"] > 1.3          # limit / ilk akma tepkisi
    assert s["max_peeq"] > 0.01
    hist = rs.curves["reaction_history"]
    assert len(hist) >= 20 and hist[-1]["reaction_n"] == pytest.approx(s["reaction_force_n"])
    # Plato: son çeyrekte tepki %5'ten az değişir (yük kontrolü burada ıraksardı).
    assert abs(hist[-1]["reaction_n"] - hist[-6]["reaction_n"]) / hist[-1]["reaction_n"] < 0.05


@requires_ccx
def test_ccx_dogbone_gerilme_malzeme_egrisiyle(tmp_path):
    """Dogbone, uca +0.3 mm çekme, plastik: ölçü kesiti nominal gerilmesi RF/(b·t)
    akma eğrisiyle uyuşmalı (ölçüldü 238.5 MPa; akma 235 + hafif pekleşme).
    Elastik çözüm aynı deplasmanda 538 MPa derdi — plastisite çalışıyor.
    NOT: bu test bölge etiketi hatasını da kilitler (dogbone yanlış yüzeylere
    bağlanıyordu, σ 39 GPa çıkıyordu)."""
    from app.mesh.base import MeshParams
    from app.mesh.gmsh_adapter import GmshMesherAdapter
    from app.templates import get_template
    from app.templates.base import build_template

    t = get_template("dogbone")
    p = t.parse_params({})
    built = build_template(t, p, tmp_path / "d.step")
    ad = GmshMesherAdapter()
    mesh = ad.generate_mesh(ad.import_geometry(built.step_path),
                            MeshParams(element_size=0.3 * min(p.gauge_width, p.fillet_radius),
                                       dimension=3, element_scheme="tet", high_order_optimize=True))
    mat = {"part_id": 0, "name": "S235", "youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0,
           "plastic": bilinear_plastic_curve(235e6, 360e6, 26.0, 210e9)}
    ccx = CalculiXAdapter()
    job = ccx.submit(ccx.build_input({
        "mesh_path": mesh.mesh_path, "dimension": 3, "output_dir": tmp_path / "run", "job_name": "db",
        "materials": [mat], "plastic": True, "n_increments": 20,
        "bcs": [{"type": "fixed", "face_ids": built.regions["tutulan_uc"]},
                {"type": "displacement", "face_ids": built.regions["yuk_cekme"], "dofs": {"1": 0.3}}],
    }))
    for _ in range(100000):
        st = ccx.poll_status(job)
        if st.state in ("done", "failed"):
            break
    assert st.state == "done", st
    s = ccx.parse_results(job).scalars
    sigma_nom = s["reaction_force_n"] / (p.gauge_width * p.thickness)
    assert 235.0 * 0.98 < sigma_nom < 260.0        # akma platosu + hafif pekleşme
    assert s["max_displacement"] == pytest.approx(0.3, rel=0.01)
    assert s["max_peeq"] > 0.0


def test_solve_request_plastic_curve_alani():
    body = SolveRequest(dimension=3, bcs=[], plasticity=True, plastic_curve=[[235, 0], [400, 0.2]])
    assert body.plastic_curve == [[235.0, 0.0], [400.0, 0.2]]
    assert SolveRequest(dimension=3, bcs=[]).plastic_curve is None
