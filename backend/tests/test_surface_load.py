"""Yüzey yükünün tutarlı düğüm dağılımı.

NEDEN: Toplam kuvvet yüzey düğümlerine EŞİT bölünüyordu. Kuadratik
elemanlarda (C3D10 → yüzeyi tri6) bu yanlış: düzgün yayılı yükün tutarlı
düğüm kuvvetleri köşelerde 0, kenar-ortalarında A/3'tür. Eşit bölmek
yükleme yüzeyinde sahte yerel salınım üretiyordu.

Kontrollü A/B ile ölçüldü (delikli plaka, aynı 5 mesh, tek fark yük
dağıtımı): u_max yayılması eşit bölmede %39.9 (0.0606–0.0848 mm),
tutarlı ağırlıkta %0.11 (0.05985–0.05991 mm). σ iki kolda aynı, çünkü
tepe gerilme delikte, yükleme yüzeyinden uzakta.
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


# --- _bcs_inp_block'un GERÇEKTE yazdığı yük --------------------------------
#
# Yukarıdaki "toplam kuvvet korunur" testi toplamı ağırlıkların kendisinden
# hesaplıyor; .inp'e ne yazıldığına bakmıyor. Bu yüzden şu hata kaçtı:
# tutarlı-ağırlık bloğu eklendi ama eski eşit-bölme yüz döngüsü yerinde
# kaldı, yük İKİ KEZ yazıldı. Delikli plakada ölçüldü: iki *CLOAD bloğu,
# her biri 30 000 N, toplam 60 000 N; u_max ve σ tam iki katına çıktı.


def _applied(step_block: str, dof: int) -> tuple[float, int]:
    """*CLOAD satırlarından verilen dof'taki toplam kuvvet ve blok sayısı."""
    from app.solvers.calculix import _bcs_inp_block  # noqa: F401

    total = 0.0
    blocks = 0
    in_cload = False
    for raw in step_block.splitlines():
        s = raw.strip()
        if s.startswith("*"):
            in_cload = s.upper().startswith("*CLOAD")
            blocks += int(in_cload)
            continue
        if in_cload and s:
            nid, d, v = (x.strip() for x in s.split(","))
            if int(d) == dof:
                total += float(v)
    return total, blocks


class TestYazilanYuk:
    F = 30000.0
    NSETS = {"FACE_6": list(range(1, 10))}

    def _step(self, face_weights):
        from app.solvers.calculix import _bcs_inp_block

        _model, step = _bcs_inp_block(
            [{"type": "cload", "face_ids": [6], "fx": self.F, "fy": 0.0, "fz": 0.0}],
            dict(self.NSETS),
            {},
            3,
            face_weights,
        )
        return step

    def test_tutarli_yol_yuku_bir_kez_yazar(self):
        step = self._step({6: {4: 2.0, 5: 2.0, 6: 1.0}})
        total, blocks = _applied(step, dof=1)
        assert total == pytest.approx(self.F, rel=1e-5)
        assert blocks == 1

    def test_agirlik_yoksa_esit_bolme_bir_kez_yazar(self):
        step = self._step(None)
        total, blocks = _applied(step, dof=1)
        assert total == pytest.approx(self.F, rel=1e-5)
        assert blocks == 1


class TestToplamKuvvetSozlesmesi:
    """fx/fy/fz, seçimin TAMAMINA uygulanan toplam kuvvettir.

    Eskiden her yüze/kenara ayrı ayrı tam F yazılıyordu (2 yüz → 2F), ama
    tutarlı-ağırlık yolu toplam F veriyordu: aynı BC, yüz tri6 mı quad mı
    olduğuna göre F ya da n·F uyguluyordu.
    """

    F = 1000.0

    def _total(self, bc, nsets, face_weights=None):
        from app.solvers.calculix import _bcs_inp_block

        _m, step = _bcs_inp_block([bc], nsets, {}, 3, face_weights)
        return _applied(step, dof=1)

    def test_iki_agirliksiz_yuz_toplam_f(self):
        total, blocks = self._total(
            {"type": "cload", "face_ids": [6, 7], "fx": self.F},
            {"FACE_6": [1, 2, 3], "FACE_7": [4, 5, 6]},
        )
        assert total == pytest.approx(self.F, rel=1e-5)
        assert blocks == 1

    def test_iki_agirlikli_yuz_toplam_f(self):
        total, blocks = self._total(
            {"type": "cload", "face_ids": [6, 7], "fx": self.F},
            {"FACE_6": [1, 2, 3], "FACE_7": [4, 5, 6]},
            {6: {2: 1.0}, 7: {5: 3.0}},
        )
        assert total == pytest.approx(self.F, rel=1e-5)
        assert blocks == 1

    def test_mesh_tipi_toplam_kuvveti_degistirmez(self):
        """Aynı seçim: ağırlıklı (tri6) ve ağırlıksız (quad) aynı toplamı verir."""
        bc = {"type": "cload", "face_ids": [6, 7], "fx": self.F}
        nsets = {"FACE_6": [1, 2, 3], "FACE_7": [4, 5, 6]}
        weighted, _ = self._total(bc, nsets, {6: {2: 1.0}, 7: {5: 1.0}})
        plain, _ = self._total(bc, nsets, None)
        assert weighted == pytest.approx(plain, rel=1e-5)

    def test_karisik_agirlik_esit_bolmeye_duser_toplam_f(self):
        total, blocks = self._total(
            {"type": "cload", "face_ids": [6, 7], "fx": self.F},
            {"FACE_6": [1, 2, 3], "FACE_7": [4, 5, 6]},
            {6: {2: 1.0}},  # 7'nin ağırlığı yok
        )
        assert total == pytest.approx(self.F, rel=1e-5)
        assert blocks == 1

    def test_iki_kenar_toplam_f(self):
        total, blocks = self._total(
            {"type": "cload", "edge_ids": [1, 2], "fx": self.F},
            {"EDGE_1": [1, 2, 3], "EDGE_2": [3, 4]},
        )
        assert total == pytest.approx(self.F, rel=1e-5)
        assert blocks == 1

    def test_yuz_arti_nokta_toplam_f(self):
        total, _ = self._total(
            {"type": "cload", "face_ids": [6], "node_ids": [9], "fx": self.F},
            {"FACE_6": [1, 2, 3], "POINT_9": [8]},
            {6: {2: 1.0}},
        )
        assert total == pytest.approx(self.F, rel=1e-5)

    def test_ortak_dugum_esit_bolmede_bir_kez_sayilir(self):
        """İki yüzün ortak kenarındaki düğüm iki kez yük almamalı."""
        from app.solvers.calculix import _bcs_inp_block

        _m, step = _bcs_inp_block(
            [{"type": "cload", "face_ids": [6, 7], "fx": self.F}],
            {"FACE_6": [1, 2, 3], "FACE_7": [3, 4, 5]},
            {},
            3,
            None,
        )
        lines = [ln for ln in step.splitlines() if ln.strip().startswith("3,")]
        assert len(lines) == 1
        total, _ = _applied(step, dof=1)
        assert total == pytest.approx(self.F, rel=1e-5)

    def test_tek_agirliksiz_yuz_davranisi_degismedi(self):
        total, _ = self._total(
            {"type": "cload", "face_ids": [6], "fx": self.F},
            {"FACE_6": [1, 2, 3, 4]},
        )
        assert total == pytest.approx(self.F, rel=1e-5)
