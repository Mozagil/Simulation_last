"""ccx `*ERROR` satırı hata mesajına taşınıyor mu (TODO 8.4).

NEDEN: koşu düştüğünde mesaj yalnız log DOSYA YOLUNU gösteriyordu —
"neden düştü" sorusunun cevabı arayüzde hiç görünmüyor, sunucudaki
dosyayı açmak gerekiyordu. Plaka DOE'sinde 200 koşudan 2'si böyle
düştü (ters jacobian) ve sebebi ancak elle log okuyarak bulundu.
"""

from __future__ import annotations

from app.solvers.calculix import CCX_ERROR_CHARS, _ccx_error_lines

# Gerçek log'dan (uploads/runs/809/run809.ccx.log) — devam satırı girintili
GERCEK = """ CalculiX Version 2.21

 The numbers below are estimated upper bounds

 number of:

  nodes:         7488

 *ERROR in e_c3d: nonpositive jacobian
          determinant in element          38

"""


def test_gercek_jacobian_hatasi_tek_satira_toplanir():
    out = _ccx_error_lines(GERCEK)
    assert out == "*ERROR in e_c3d: nonpositive jacobian determinant in element 38"


def test_hata_yoksa_bos_doner():
    assert _ccx_error_lines(" normal cikti\n  bitti\n") == ""
    assert _ccx_error_lines("") == ""


def test_uyari_hata_sayilmaz():
    """`*WARNING` koşuyu düşürmez; mesajı kirletmemeli."""
    assert _ccx_error_lines(" *WARNING in e_c3d: something\n   detay\n") == ""


def test_birden_fazla_hata_ayrilir():
    log = (
        " *ERROR in e_c3d: nonpositive jacobian\n"
        "      determinant in element 38\n"
        "\n"
        " *ERROR in nonlinear: too many iterations\n"
    )
    out = _ccx_error_lines(log)
    assert out.count("*ERROR") == 2
    assert " | " in out


def test_cok_uzun_mesaj_kisalir():
    log = " *ERROR in x: " + ("uzun " * 200) + "\n"
    out = _ccx_error_lines(log)
    assert len(out) <= CCX_ERROR_CHARS
    assert out.endswith("…")


def test_sonraki_karta_tasmaz():
    """Devam satırı toplanırken bir sonraki `*` bloğu yutulmamalı."""
    log = " *ERROR in e_c3d: kotu eleman\n   detay satiri\n *STEP bilgisi\n"
    out = _ccx_error_lines(log)
    assert "detay satiri" in out
    assert "*STEP" not in out


def test_ayni_hata_tekrar_edilmez():
    """Log stdout+stderr birleşimi; ccx aynı satırı ikisine de yazıyor
    (gerçek koşuda görüldü: run 809, 876)."""
    tek = " *ERROR in e_c3d: nonpositive jacobian\n      determinant in element 38\n"
    out = _ccx_error_lines(tek + "\n" + tek)
    assert out.count("*ERROR") == 1
    assert "|" not in out
