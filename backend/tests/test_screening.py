"""Fiziksel ön eleme testleri."""

from __future__ import annotations

from app.doe.screening import screen_sample

S235_E = 210e9
S235_YIELD = 235e6
AL6061_E = 68.9e9
AL6061_YIELD = 276e6

BEAM = {"length": 500.0, "thickness": 10.0, "width": 50.0}


def _screen(params=None, force=500.0, E=S235_E, yield_pa=S235_YIELD, **kw):
    return screen_sample(
        "cantilever_beam",
        params or dict(BEAM),
        force_n=force,
        youngs_modulus_pa=E,
        yield_strength_pa=yield_pa,
        **kw,
    )


class TestReferansVaka:
    def test_celikle_gecer(self):
        """L500/T10/W50, 500 N, S235 → u/L=0.048, σ=300... σ akmayı aşıyor."""
        r = _screen()
        # σ = 300 MPa > 0.8×235 = 188 → elenmeli
        assert r.ok is False
        assert "akma" in r.reason

    def test_celikle_dusuk_yukte_gecer(self):
        r = _screen(force=250.0)
        assert r.ok is True
        assert r.u_over_l < 0.06
        assert r.sigma_mpa < 188

    def test_aluminyumla_buyuk_deformasyon(self):
        """Eski kalite setinin sorunu: aynı vaka alüminyumda u/L=0.146."""
        r = _screen(E=AL6061_E, yield_pa=AL6061_YIELD, force=500.0)
        assert r.ok is False
        # Alüminyumda önce deformasyon kapısına takılır
        assert "deformasyon" in r.reason or "akma" in r.reason
        assert r.u_over_l > 0.10


class TestSinirlar:
    def test_uzun_ince_kiris_elenir(self):
        r = _screen({"length": 700.0, "thickness": 8.0, "width": 30.0}, force=300.0)
        assert r.ok is False

    def test_kisa_kalin_kiris_gecer(self):
        r = _screen({"length": 450.0, "thickness": 20.0, "width": 80.0}, force=300.0)
        assert r.ok is True

    def test_geometrik_kisit_ihlali_elenir(self):
        # L < 5T → şablonun kendi doğrulaması reddeder
        r = _screen({"length": 40.0, "thickness": 20.0, "width": 50.0}, force=10.0)
        assert r.ok is False
        assert "geometrik" in r.reason

    def test_esikler_ayarlanabilir(self):
        sikí = _screen(force=250.0, max_u_over_l=0.001)
        assert sikí.ok is False
        gevsek = _screen(force=250.0, max_u_over_l=0.5, yield_utilisation=5.0)
        assert gevsek.ok is True


class TestGuvenliVarsayilanlar:
    def test_bilinmeyen_sablon_elenmez(self):
        r = screen_sample(
            "yok_boyle_bir_sablon",
            {"a": 1},
            force_n=100,
            youngs_modulus_pa=S235_E,
            yield_strength_pa=S235_YIELD,
        )
        assert r.ok is True

    def test_akma_bilinmiyorsa_sadece_deformasyona_bakilir(self):
        r = _screen(force=500.0, yield_pa=None)
        # σ kontrolü atlanır, u/L=0.048 < 0.06 → geçer
        assert r.ok is True

    def test_metrikler_raporlanir(self):
        r = _screen(force=250.0)
        assert r.u_mm > 0
        assert r.sigma_mpa > 0
        assert r.to_dict()["ok"] is True
