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
