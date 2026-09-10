"""Kabuk sonuçlarının çıktı biçimi.

`*NODE FILE, OUTPUT=2D` bir süre kullanıldı ve GERİ ALINDI: düğüm
hizalamasını çözüyordu ama gerilmeyi kabuğun ORTA DÜZLEMİNDE veriyordu.
Eğilmede gerilme kalınlık boyunca lineerdir — yüzeyde ±sigma_max, orta
düzlemde SIFIR. Gerçek bir testte 300 MPa olması gereken kabuk gerilmesi
79.8 MPa'ya düştü (kalan kısım ankastre köşedeki yerel etkiler ve kayma),
deplasman ise 23.6 mm'de kaldı çünkü deplasman kalınlık boyunca değişmez.

Hizalama artık post-process'te `_collapse_shell_expansion` ile çözülüyor
(bkz. test_shell_collapse.py). Bu dosya, OUTPUT=2D'nin geri gelmediğini
koruyan bir regresyon testidir.
"""

from app.solvers.calculix import _frequency_step_block, _static_step_block


def test_static_step_never_uses_output_2d():
    """REGRESYON: OUTPUT=2D geri gelirse kabuk gerilmesi kat kat düşük
    çıkar ve bu SESSİZCE olur — deplasman doğru kaldığı için hata
    gözden kaçar."""
    assert "OUTPUT=2D" not in _static_step_block("", dimension=2)
    assert "OUTPUT=2D" not in _static_step_block("", dimension=3)


def test_frequency_step_never_uses_output_2d():
    assert "OUTPUT=2D" not in _frequency_step_block(n_modes=6, dimension=2)
    assert "OUTPUT=2D" not in _frequency_step_block(n_modes=6, dimension=3)


def test_static_step_still_requests_displacement_and_stress():
    text = _static_step_block("", dimension=2)
    assert "*NODE FILE" in text
    assert "*EL FILE" in text
    assert "\nU\n" in text
    assert "\nS\n" in text


def test_static_step_still_embeds_bc_lines():
    text = _static_step_block("*CLOAD\n5, 2, -100\n", dimension=2)
    assert "*CLOAD" in text
    assert text.index("*CLOAD") < text.index("*NODE FILE")
