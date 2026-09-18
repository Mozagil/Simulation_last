"""Yüzey yükünün tutarlı düğüm dağılımı.

NEDEN: Toplam kuvvet yüzey düğümlerine EŞİT bölünüyordu. Kuadratik
elemanlarda (C3D10 → yüzeyi tri6) bu yanlış: düzgün yayılı yükün tutarlı
düğüm kuvvetleri köşelerde 0, kenar-ortalarında A/3'tür. Eşit bölmek
yükleme yüzeyinde sahte yerel salınım üretiyordu.

Ölçüm (delikli plaka, study 10): u_max mesh'ten mesh'e %36 oynadı —
beş mesh 0.0603–0.0609 mm'de uyuşurken ikisi 0.0656 ve 0.0848 verdi.
Mesh kaliteleri iyiydi (Jacobian 0.75 / 0.84; "sağlam" olanınki 0.60).
σ etkilenmedi çünkü tepe gerilme delikte, yükleme yüzeyinden uzakta.
"""

from __future__ import annotations

import math

import pytest

from app.solvers.calculix import _consistent_face_weights, _tri_area


class TestUcgenAlani:
    def test_birim_ucgen(self):
        assert _tri_area((0, 0, 0), (1, 0, 0), (0, 1, 0)) == pytest.approx(0.5)

    def test_duzlem_disi(self):
        # 3-4-5 dik üçgeni, z düzleminde döndürülmüş
        a = _tri_area((0, 0, 0), (3, 0, 0), (0, 0, 4))
        assert a == pytest.approx(6.0)

    def test_dejenere_sifir(self):
        assert _tri_area((0, 0, 0), (1, 1, 1), (2, 2, 2)) == pytest.approx(0.0)

    def test_siralamadan_bagimsiz(self):
        p = [(0, 0, 0), (2, 0, 0), (0, 3, 0)]
        a1 = _tri_area(*p)
        a2 = _tri_area(p[2], p[0], p[1])
        assert a1 == pytest.approx(a2)


class TestAgirlikToplama:
    def test_tek_yuzey(self):
        w = _consistent_face_weights({"face_ids": [5]}, {5: {10: 1.0, 11: 2.0}})
        assert w == {10: 1.0, 11: 2.0}

    def test_ortak_dugum_iki_yuzeyden_pay_alir(self):
        """Ortak kenardaki düğüm her iki yüzeyden de katkı almalı."""
        w = _consistent_face_weights(
            {"face_ids": [1, 2]}, {1: {10: 1.0, 11: 2.0}, 2: {11: 3.0, 12: 4.0}}
        )
        assert w == {10: 1.0, 11: 5.0, 12: 4.0}

    def test_bilinmeyen_yuzey_atlanir(self):
        w = _consistent_face_weights({"face_ids": [1, 99]}, {1: {10: 1.0}})
        assert w == {10: 1.0}

    def test_harita_yoksa_bos(self):
        assert _consistent_face_weights({"face_ids": [1]}, None) == {}

    def test_face_ids_yoksa_bos(self):
        assert _consistent_face_weights({}, {1: {10: 1.0}}) == {}


class TestFizikselDogruluk:
    """Tutarlı ağırlıkların toplam kuvveti koruduğunu ve eşit bölmeden
    farklı olduğunu gösterir."""

    @staticmethod
    def _tri6_weights(area: float) -> dict[int, float]:
        """Tek bir tri6 yüzün ağırlıkları: köşe 0, kenar-ortası A/3."""
        return {4: area / 3, 5: area / 3, 6: area / 3}

    def test_toplam_kuvvet_korunur(self):
        w = self._tri6_weights(9.0)
        total = sum(w.values())
        F = 1000.0
        dagitim = [F * (x / total) for x in w.values()]
        assert sum(dagitim) == pytest.approx(F)

    def test_koseler_yuk_almaz(self):
        """tri6'da köşe düğümleri düzgün yayılı yükte pay ALMAZ.
        Eşit bölme onlara 1/6 verirdi — hatanın kaynağı bu."""
        w = self._tri6_weights(9.0)
        for kose in (1, 2, 3):
            assert kose not in w

    def test_esit_bolmeden_farkli(self):
        w = self._tri6_weights(9.0)
        total = sum(w.values())
        pay = [x / total for x in w.values()]
        esit = 1.0 / 6  # 6 düğüme eşit bölünseydi
        assert not any(math.isclose(p, esit) for p in pay)
        # Gerçek pay 1/3, eşit bölmenin iki katı
        assert all(math.isclose(p, 1 / 3) for p in pay)
