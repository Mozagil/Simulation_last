"""GNN girdi/çıktı ölçekleme (TODO 1.2).

NEDEN: ham kanallar aynı katmana giriyordu — koordinat 0…700, E 210000,
yoğunluk 7.85e−9, sınır koşulu bayrakları 0/1. Ölçek modelle SAKLANMAZSA
tahmin sessizce saçmalar, bu yüzden npz gidiş-dönüşü de sınanır.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.dataset.training_data import (
    NODE_INPUT_CHANNELS,
    NODE_INPUT_GROUPS,
    NODE_OUTPUT_CHANNELS,
    NODE_OUTPUT_GROUPS,
    channel_group_indices,
)
from app.ml.normalization import ChannelScaler

X = np.array([[0.0, 10.0, 5.0], [2.0, 10.0, 7.0], [4.0, 10.0, 9.0]])


# --- temel davranış -----------------------------------------------------------


def test_ortalama_sifir_std_bir():
    s = ChannelScaler.fit([X])
    Z = s.transform(X)
    assert Z[:, 0].mean() == pytest.approx(0.0, abs=1e-12)
    assert Z[:, 0].std() == pytest.approx(1.0)


def test_gidis_donus_aynisini_verir():
    s = ChannelScaler.fit([X])
    assert s.inverse_transform(s.transform(X)) == pytest.approx(X)


def test_akiskan_fit_tek_parcayla_ayni():
    """Grafları tek diziye yığmadan hesaplıyoruz; sonuç değişmemeli."""
    bir = ChannelScaler.fit([X])
    parcali = ChannelScaler.fit([X[:1], X[1:]])
    assert parcali.mean == pytest.approx(bir.mean)
    assert parcali.scale == pytest.approx(bir.scale)


def test_bos_veri_reddedilir():
    with pytest.raises(ValueError):
        ChannelScaler.fit([])
    with pytest.raises(ValueError):
        ChannelScaler.fit([np.zeros((0, 3))])


def test_kanal_sayisi_tutarsizligi_hata():
    with pytest.raises(ValueError, match="Kanal sayısı"):
        ChannelScaler.fit([X, np.zeros((2, 5))])


# --- sabit kanallar -----------------------------------------------------------


def test_sabit_kanal_sifira_bolunmez():
    s = ChannelScaler.fit([X])
    assert s.scale[1] == 1.0
    assert s.constant_channels == [1]
    assert np.all(s.transform(X)[:, 1] == 0.0), "sabit kanal bilgi taşımaz"


def test_float32_gurultusu_sabit_sayilir():
    """ÖLÇÜLDÜ: poisson_ratio fiziksel olarak 0.3 ama float32 saklamadan
    std = 9.1e−8 geliyordu. Buna bölmek saf yuvarlama gürültüsünü ±1
    mertebesinde bir girdiye çeviriyor."""
    poisson = np.full((1000, 1), 0.3, dtype=np.float32).astype(np.float64)
    poisson += np.random.default_rng(0).normal(0, 1e-8, poisson.shape)

    s = ChannelScaler.fit([poisson])

    assert s.scale[0] == 1.0
    assert s.constant_channels == [0]
    assert np.abs(s.transform(poisson)).max() < 1e-6


def test_gercekten_degisen_kanal_sabit_sayilmaz():
    kalinlik = np.array([[5.0], [8.0], [12.0]])
    s = ChannelScaler.fit([kalinlik])
    assert s.constant_channels == []
    assert s.scale[0] > 1.0


# --- gruplu ölçek -------------------------------------------------------------


def test_grup_ortak_olcek_alir():
    s = ChannelScaler.fit([X], groups=((0, 2),))
    assert s.scale[0] == pytest.approx(s.scale[2])


def test_narinlik_korunur():
    """Asıl gerekçe: x/y/z ayrı ölçeklenince narin kiriş küpe dönüyor."""
    rng = np.random.default_rng(1)
    kiris = np.column_stack([
        rng.uniform(0, 500, 400),   # uzunluk
        rng.uniform(0, 10, 400),    # kalınlık
        rng.uniform(0, 50, 400),    # genişlik
    ])
    oran = np.ptp(kiris, axis=0)[0] / np.ptp(kiris, axis=0)[1]

    ayri = ChannelScaler.fit([kiris]).transform(kiris)
    grup = ChannelScaler.fit([kiris], groups=((0, 1, 2),)).transform(kiris)

    assert np.ptp(ayri, axis=0)[0] / np.ptp(ayri, axis=0)[1] == pytest.approx(1.0, rel=0.1)
    assert np.ptp(grup, axis=0)[0] / np.ptp(grup, axis=0)[1] == pytest.approx(oran, rel=1e-6)


def test_grup_sifir_varyansli_uye_tasinir():
    """u_z gibi fiziksel olarak sıfır bileşen, grup ölçeğiyle sıfır kalır."""
    Y = np.column_stack([
        np.linspace(-1, 1, 50),          # u_x
        np.linspace(-20, 20, 50),        # u_y
        np.full(50, 1e-7),               # u_z ≈ 0
    ])
    s = ChannelScaler.fit([Y], groups=((0, 1, 2),))
    Z = s.transform(Y)
    assert np.abs(Z[:, 2]).max() < 1e-6, "sıfır bileşen yükseltilmemeli"
    assert Z[:, 1].std() > Z[:, 0].std(), "asıl bileşen baskın kalmalı"


def test_grup_indeksleri_adlardan_cozulur():
    idx = channel_group_indices(NODE_INPUT_CHANNELS, NODE_INPUT_GROUPS)
    assert (0, 1, 2) in idx, "x/y/z"
    assert any(NODE_INPUT_CHANNELS[i] == "load_fx" for g in idx for i in g)
    cikti = channel_group_indices(NODE_OUTPUT_CHANNELS, NODE_OUTPUT_GROUPS)
    assert cikti == ((0, 1, 2),), "von Mises deplasman grubuna girmez"


def test_bilinmeyen_kanal_adi_atlanir():
    assert channel_group_indices(("a", "b"), (("a", "yok"),)) == ()
    assert channel_group_indices(("a", "b"), (("a", "b"),)) == ((0, 1),)


# --- saklama ------------------------------------------------------------------


def test_npz_gidis_donus():
    s = ChannelScaler.fit([X], groups=((0, 2),))
    d = s.to_npz("x")
    geri = ChannelScaler.from_npz(d, "x", 3)
    assert geri.mean == pytest.approx(s.mean)
    assert geri.scale == pytest.approx(s.scale)
    assert geri.constant_channels == s.constant_channels


def test_olcek_yoksa_birim_olcek():
    """Ölçeksiz eğitilmiş eski model dosyaları okunabilir kalmalı."""
    s = ChannelScaler.from_npz({}, "x", 4)
    assert s.transform(np.ones((2, 4))) == pytest.approx(np.ones((2, 4)))


def test_ozet_sabitleri_isaretler():
    ozet = ChannelScaler.fit([X]).summary(("a", "b", "c"))
    assert ozet["b"]["constant"] is True
    assert ozet["a"]["constant"] is False
    assert ozet["a"]["scale"] > 0
