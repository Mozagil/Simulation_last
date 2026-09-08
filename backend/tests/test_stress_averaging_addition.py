"""KRİTİK REGRESYON TESTİ — .frd STRESS parse'ında nodal averaging.

Bug: `*EL FILE, S` çıktısı elemana özgüdür (integration point'ten node'a
extrapole edilmiş) — bir node çevresindeki her elemandan AYRI bir STRESS
kaydıyla birden fazla kez `.frd`'ye yazılır. Eski kod bu kayıtları düz bir
dict'e atıyordu (`stress[nid] = ...`) — son gelen kayıt öncekinin üzerine
yazılıyor, node'a bağlı komşu elemanların gerilmesi rastgele "kazanan"
oluyordu. Bu da viewer'da benekli/kaotik bir kontur olarak görünüyordu.

Doğru davranış: aynı node için gelen tüm STRESS kayıtlarının componentwise
ORTALAMASI alınmalı (cgx/Abaqus'un yaptığı "nodal averaging").
"""

import pytest

from app.solvers.calculix import _parse_frd


def test_parse_frd_averages_stress_from_multiple_elements_sharing_a_node(tmp_path):
    """Node 10'a iki farklı elemandan (SXX=100 ve SXX=200) gelen kayıtların
    ortalamasının (150) döndüğünü doğrular.
    """
    content = """    1C
    2C                             1                                     1
 -1        10 0.00000E+00 0.00000E+00 0.00000E+00
 -3
    1PSTEP                         1           1           1
  100CL  101 1.000000000           1                     0    1           1
 -4  STRESS      6    1
 -5  SXX         1    4    1    1
 -5  SYY         1    4    2    2
 -5  SZZ         1    4    3    3
 -5  SXY         1    4    1    2
 -5  SYZ         1    4    2    3
 -5  SZX         1    4    3    1
 -1        10 1.00000E+02 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
 -1        10 2.00000E+02 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
 -3
 9999
"""
    frd_path = tmp_path / "shared_node.frd"
    frd_path.write_text(content, encoding="utf-8")

    result = _parse_frd(frd_path)

    # Eski (bug'lı) davranışta bu 200.0 (son kayıt) çıkardı.
    # Doğru davranışta (100+200)/2 = 150.0 çıkmalı.
    assert result["stress"][10][0] == pytest.approx(150.0)
