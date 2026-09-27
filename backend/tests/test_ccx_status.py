"""Çözücü yakınsama kaydı (.sta) ve tamamlanmamış çözümün `solved` olmaması.

Fikstürler UYDURMA değil: `tests/fixtures/ccx_sta/` altındaki dosyalar
gerçek ccx koşularının çıktısı (NLGEOM ankastre kiriş, 6061-T6, L=500 T=8
W=40, 2026-09-19). Ölçülen davranış:

    vaka               exit   .frd       son adım zamanı
    normal              0     20 artım   1.0
    artım limiti (3)   201    3 artım    0.15   <- .frd KISMİ ama var
    yük ×200            0     29 artım   1.0    (2 cutback)
    ıraksama           201    1 blok     0.0    (tek 'U' satırı)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.solvers.base import InputArtifact, SolverError
from app.solvers.calculix import CalculiXAdapter, _ccx_executable, parse_ccx_sta

FIX = Path(__file__).parent / "fixtures" / "ccx_sta"

requires_ccx = pytest.mark.skipif(
    _ccx_executable() is None,
    reason="CalculiX (ccx) bulunamadı (CCX_PATH / PATH / vendor)",
)


# --- .sta okuma (gerçek çıktılar) ------------------------------------------


@pytest.mark.parametrize(
    "name, inc, cutbacks, final, converged",
    [
        ("linear.sta", 1, 0, 1.0, 1.0),
        ("nlgeom_ok.sta", 20, 0, 1.0, 1.0),
        ("nlgeom_cutbacks.sta", 29, 2, 1.0, 1.0),
        ("nlgeom_inc_limit.sta", 3, 0, 0.15, 0.0),
        ("nlgeom_diverged.sta", 0, 1, 0.0, 0.0),
    ],
)
def test_sta_ozeti(name, inc, cutbacks, final, converged):
    s = parse_ccx_sta(FIX / name)
    assert s is not None
    assert s["_n_increments"] == inc
    assert s["_n_cutbacks"] == cutbacks
    assert s["_final_step_time"] == pytest.approx(final)
    assert s["_solver_converged"] == converged


def test_sta_yoksa_none(tmp_path):
    assert parse_ccx_sta(tmp_path / "yok.sta") is None


def test_sta_satirsiz_none(tmp_path):
    p = tmp_path / "bos.sta"
    p.write_text("SUMMARY OF JOB INFORMATION\n  STEP INC ATT\n", encoding="utf-8")
    assert parse_ccx_sta(p) is None


# --- submit denetimi (ccx taklidi) -----------------------------------------


def _fake_run(sta_fixture: str | None, returncode: int = 0):
    def run(cmd, cwd, **_kw):
        if sta_fixture is not None:
            (Path(cwd) / f"{cmd[1]}.sta").write_text(
                (FIX / sta_fixture).read_text(encoding="utf-8"), encoding="utf-8"
            )
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr="")

    return run


def _deck(tmp_path: Path, step: str) -> InputArtifact:
    inp = tmp_path / "job.inp"
    inp.write_text(f"*NODE\n1,0,0,0\n{step}\n*END STEP\n", encoding="utf-8")
    return InputArtifact(path=inp, kind="file")


@pytest.fixture()
def fake_ccx(monkeypatch):
    monkeypatch.setattr("app.solvers.calculix._ccx_executable", lambda: "ccx")
    monkeypatch.setattr("app.solvers.calculix._ccx_run_env", lambda _c: {})

    def install(sta_fixture, returncode=0):
        monkeypatch.setattr(
            "app.solvers.calculix.subprocess.run", _fake_run(sta_fixture, returncode)
        )

    return install


def test_exit0_ama_statik_adim_tamamlanmadi_hata(tmp_path, fake_ccx):
    """Savunma katmanı: çıkış kodu temiz olsa bile adım 1.0'a ulaşmadıysa
    çözüm başarılı sayılmaz."""
    fake_ccx("nlgeom_inc_limit.sta", returncode=0)
    with pytest.raises(SolverError, match="tamamlamadı"):
        CalculiXAdapter().submit(_deck(tmp_path, "*STEP, NLGEOM\n*STATIC"))


def test_exit0_ve_tamamlandi_gecer(tmp_path, fake_ccx):
    fake_ccx("nlgeom_cutbacks.sta", returncode=0)
    handle = CalculiXAdapter().submit(_deck(tmp_path, "*STEP, NLGEOM\n*STATIC"))
    assert handle._sta_summary["_n_cutbacks"] == 2


def test_modal_adimda_denetim_uygulanmaz(tmp_path, fake_ccx):
    """*FREQUENCY artım yazmaz; statik tamamlanma kuralı ona uygulanmamalı."""
    fake_ccx("nlgeom_inc_limit.sta", returncode=0)
    CalculiXAdapter().submit(_deck(tmp_path, "*STEP\n*FREQUENCY\n10"))


def test_sifir_olmayan_cikis_mesajinda_sta_ozeti(tmp_path, fake_ccx):
    fake_ccx("nlgeom_diverged.sta", returncode=201)
    with pytest.raises(SolverError, match=r"Adım zamanı 0/1\.0, 0 artım, 1 cutback"):
        CalculiXAdapter().submit(_deck(tmp_path, "*STEP, NLGEOM\n*STATIC"))


# --- gerçek ccx: bilerek yakınsamayan vaka ----------------------------------

#: Tek C3D8 küp: x=0 yüzü ankastre, x=1 yüzüne -y yük. INC ve artım boyu
#: parametre — sabit 0.1'lik artımla 10 artım gerekiyor.
_CUBE = """*NODE
1, 0, 0, 0
2, 1, 0, 0
3, 1, 1, 0
4, 0, 1, 0
5, 0, 0, 1
6, 1, 0, 1
7, 1, 1, 1
8, 0, 1, 1
*ELEMENT, TYPE=C3D8, ELSET=E
1, 1, 2, 3, 4, 5, 6, 7, 8
*MATERIAL, NAME=M
*ELASTIC
210000, 0.3
*SOLID SECTION, ELSET=E, MATERIAL=M
*BOUNDARY
1, 1, 3
4, 1, 3
5, 1, 3
8, 1, 3
*STEP, NLGEOM, INC={inc}
*STATIC
0.1, 1.0, 0.1, 0.1
*CLOAD
2, 2, -10
3, 2, -10
6, 2, -10
7, 2, -10
*NODE FILE
U
*END STEP
"""


def _cube(tmp_path: Path, inc: int) -> InputArtifact:
    inp = tmp_path / "kup.inp"
    inp.write_text(_CUBE.format(inc=inc), encoding="utf-8")
    return InputArtifact(path=inp, kind="file")


@requires_ccx
def test_gercek_ccx_yakinsamayan_cozum_basarili_sayilmaz(tmp_path):
    """TODO madde 3'ün istediği regresyon: 10 artım gereken adım 2 artımla
    sınırlandı. Çözüm `solved` olmamalı, .frd kısmi de olsa."""
    with pytest.raises(SolverError) as exc:
        CalculiXAdapter().submit(_cube(tmp_path, inc=2))
    assert "Adım zamanı 0.2/1.0" in str(exc.value)
    assert (tmp_path / "kup.frd").exists(), "ccx kısmi .frd yazar — başarı göstergesi değil"


@requires_ccx
def test_gercek_ccx_yakinsayan_cozum_ozetlenir(tmp_path):
    handle = CalculiXAdapter().submit(_cube(tmp_path, inc=100))
    s = handle._sta_summary
    assert s["_solver_converged"] == 1.0
    assert s["_n_increments"] == 10
    assert s["_final_step_time"] == pytest.approx(1.0)
