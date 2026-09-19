"""NLGEOM (büyük deformasyon) testleri."""

from __future__ import annotations

from app.solvers.calculix import _static_step_block


class TestStepKarti:
    def test_lineer_varsayilan(self):
        out = _static_step_block("", 3)
        assert "*STEP\n" in out
        assert "NLGEOM" not in out
        # Lineer çözümde artım satırı olmamalı
        assert "*STATIC\n*NODE FILE" in out.replace("\r", "")

    def test_nlgeom_karti(self):
        out = _static_step_block("", 3, nlgeom=True)
        assert "*STEP, NLGEOM" in out
        assert "*STATIC" in out
        # Artımlı yükleme: *STATIC'ten sonra dört alanlı satır gelmeli
        lines = [l for l in out.splitlines() if l.strip()]
        i = lines.index("*STATIC")
        assert len(lines[i + 1].split(",")) == 4

    def test_artim_sayisi_karta_yansiyor(self):
        az = _static_step_block("", 3, nlgeom=True, n_increments=4)
        cok = _static_step_block("", 3, nlgeom=True, n_increments=100)
        # Daha çok artım → daha küçük ilk artım
        ilk = lambda s: float(
            [l for l in s.splitlines() if l.strip()][
                [l for l in s.splitlines() if l.strip()].index("*STATIC") + 1
            ].split(",")[0]
        )
        assert ilk(cok) < ilk(az)

    def test_bc_satirlari_korunur(self):
        out = _static_step_block("*BOUNDARY\nNSET1,1,3\n", 3, nlgeom=True)
        assert "*BOUNDARY" in out
        assert "NSET1,1,3" in out

    def test_cikti_kartlari_her_iki_modda(self):
        for kw in ({}, {"nlgeom": True}):
            out = _static_step_block("", 3, **kw)
            assert "*NODE FILE" in out and "U" in out
            assert "*EL FILE" in out and "S" in out
            assert out.rstrip().endswith("*END STEP")


class TestKorpusAyrimi:
    """Lineer ve NLGEOM run'lar aynı modele girmemeli — farklı fizik."""

    def test_spec_varsayilani_lineer(self):
        from app.ml.corpus import CorpusSpec

        assert CorpusSpec().nlgeom is False

    def test_nlgeom_spec_kurulabilir(self):
        from app.ml.corpus import CorpusSpec

        spec = CorpusSpec(template_id="cantilever_beam", nlgeom=True)
        assert spec.nlgeom is True
        assert spec.template_id == "cantilever_beam"


# --- NLGEOM SONUCU doğru okunuyor mu (gerçek ccx) ---------------------------
#
# Yukarıdaki testler yalnız kartı sınıyor. Sonuç okuma hatası bu yüzden
# kaçtı (ölçüldü 2026-09-19, 6061-T6 kiriş L500 T8 W40, 20 artım):
#   - deplasman İLK artımdan okunuyordu: 2.669 mm (gerçek 52.893, 20x)
#   - gerilme artımlar boyunca ORTALANIYORDU: 103.5 MPa (~0.525 x tam yük)
#   - çok artım "modal" sanılıyor, eğitim örneği modal şemayla yazılıyordu
# Aşağıdaki test aynı desteyi lineer ve küçük yüklü NLGEOM çözer: küçük
# deformasyonda ikisi uyuşmalı. Eski kodda NLGEOM u = lineerin %10'u olurdu.

import pytest  # noqa: E402

from app.solvers.base import InputArtifact  # noqa: E402
from app.solvers.calculix import CalculiXAdapter, _ccx_executable  # noqa: E402

_requires_ccx = pytest.mark.skipif(
    _ccx_executable() is None, reason="CalculiX (ccx) bulunamadı"
)

_CUBE = """*NODE
1, 0, 0, 0
2, 10, 0, 0
3, 10, 10, 0
4, 0, 10, 0
5, 0, 0, 10
6, 10, 0, 10
7, 10, 10, 10
8, 0, 10, 10
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
{step}
*CLOAD
2, 2, -50
3, 2, -50
6, 2, -50
7, 2, -50
*NODE FILE
U
*EL FILE
S
*END STEP
"""


def _solve(tmp_path, name: str, step: str):
    d = tmp_path / name
    d.mkdir()
    inp = d / "kup.inp"
    inp.write_text(_CUBE.format(step=step), encoding="utf-8")
    ad = CalculiXAdapter()
    job = ad.submit(InputArtifact(path=inp, kind="file"))
    return ad.parse_results(job), d


@_requires_ccx
def test_nlgeom_sonucu_tam_yukten_okunur(tmp_path):
    lin, _ = _solve(tmp_path, "lineer", "*STEP\n*STATIC")
    nl, d = _solve(
        tmp_path, "nlgeom", "*STEP, NLGEOM, INC=100\n*STATIC\n0.1, 1.0, 0.001, 0.1"
    )
    assert nl.scalars["_n_increments"] == 10, "deney gerçekten çok artımlı olmalı"

    u_lin, u_nl = lin.scalars["max_displacement"], nl.scalars["max_displacement"]
    s_lin, s_nl = lin.scalars["max_von_mises"], nl.scalars["max_von_mises"]
    # Küçük deformasyon: lineer ~ NLGEOM. Eski kodda oran 0.10 (u) ve ~0.55 (σ).
    assert u_nl == pytest.approx(u_lin, rel=0.02)
    assert s_nl == pytest.approx(s_lin, rel=0.02)


@_requires_ccx
def test_nlgeom_statik_sayilir_modal_degil(tmp_path):
    """Çok artım modal sanılmamalı: görüntüleyiciye tek 'mod' (son artım)
    gider, eğitim örneği statik şemayla (gerilmeli) yazılır."""
    import json

    nl, d = _solve(
        tmp_path, "nlgeom", "*STEP, NLGEOM, INC=100\n*STATIC\n0.1, 1.0, 0.001, 0.1"
    )
    preview = json.loads((d / "kup.results.json").read_text(encoding="utf-8"))
    assert len(preview["modes"]) == 1
    assert preview["modes"][0]["frequency_hz"] is None
    assert preview["max_displacement"] == pytest.approx(nl.scalars["max_displacement"])
    assert max(preview["von_mises"]) > 0.0
