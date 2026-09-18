"""Tekillikten uzakta gerilme ölçümü (Faz 0.6).

NEDEN: Ankastre kirişte `max_von_mises` mesh'ten mesh'e ±%5.6 oynuyor.
Ölçtük (study_id=8, S235, L500/T10/W50, uçtan 500 N):

    es (mm)   15     12     10      8      6      5      4      3
    σ (MPa)  345.9  315.5  330.0  330.7  339.8  337.0  321.3  328.5

Dizi bir yere oturmuyor; en ince 4 çözümün yayılımı %5.58. Sebep fizik
değil: max σ düğüm bazında alınıyor ve ankastre köşeye en yakın düğümün
konumu her mesh'te değişiyor. Köşe idealize problemde tekil bir nokta —
orada σ mesh inceldikçe sınırsız büyür, "yakınsamış değer" yoktur.

Sonuç: `max_von_mises`'ı surrogate hedefi yaparsak modelin doğruluk
tavanı ~%5.6 olur. Ne kadar veri toplanırsa toplansın bunun altına
inilemez, çünkü HEDEFİN KENDİSİ o kadar oynuyor.

ÇÖZÜM: Gerilmeyi kısıttan sabit bir FİZİKSEL mesafe uzakta ölç.
"Bir sonraki eleman" demek yetmez — o mesh'e bağlı bir mesafedir
(es=15'te 15 mm, es=3'te 3 mm), yani gürültü kaybolmaz, şekil değiştirir.
Sabit mesafe ise her mesh'te aynı fiziksel konumdan ölçer.

MALİYETİ: St. Venant ilkesi — kısıtın yerel etkisi kesit boyutu
mertebesinde bir mesafede söner. Kirişte 1×T uzaklaşmanın teorik bedeli
yalnız %2 (300 → 294 MPa), 2×T için %4. Karşılığında ±%5.6'lık mesh
gürültüsünden kurtuluyoruz. Üstelik o konumdaki teorik değer kapalı
formda hesaplanabildiği için doğrulanabilir.

GERİYE DÖNÜK ÇALIŞIR: `.train.npz` dosyaları düğüm başına koordinat,
fixed bayrakları ve von Mises içeriyor. Hiçbir çözümü tekrarlamadan
mevcut run'lar üzerinde yeniden hesaplanabilir.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from app.dataset.training_data import NODE_INPUT_CHANNELS, NODE_OUTPUT_CHANNELS

logger = logging.getLogger(__name__)

#: Kısıttan uzaklık, karakteristik uzunluğun katı olarak. 1.0 = 1×T.
#: Teorik bedeli %2; daha büyük seçilirse ölçüm tekillikten daha güvenli
#: uzaklaşır ama gerçek maksimumdan da uzaklaşır.
DEFAULT_STANDOFF_RATIO = 1.0

_IDX = {name: i for i, name in enumerate(NODE_INPUT_CHANNELS)}
_OUT = {name: i for i, name in enumerate(NODE_OUTPUT_CHANNELS)}


def constrained_mask(node_inputs: np.ndarray) -> np.ndarray:
    """Herhangi bir DOF'u sabitlenmiş düğümler."""
    cols = [_IDX["fixed_ux"], _IDX["fixed_uy"], _IDX["fixed_uz"], _IDX["fixed_rot"]]
    return (node_inputs[:, cols] > 0.5).any(axis=1)


def distance_to_constraint(node_inputs: np.ndarray) -> np.ndarray:
    """Her düğümün en yakın kısıtlı düğüme uzaklığı (mm).

    Kısıt yoksa hepsi +inf döner — maskeleme etkisiz kalır, çağıran taraf
    bunu "ölçüm yapılamadı" diye değil "kısıt yok, maskeye gerek yok"
    diye yorumlamalı.
    """
    xyz = node_inputs[:, [_IDX["x"], _IDX["y"], _IDX["z"]]].astype(np.float64)
    mask = constrained_mask(node_inputs)
    if not mask.any():
        return np.full(len(xyz), np.inf)

    anchors = xyz[mask]
    try:
        from scipy.spatial import cKDTree  # type: ignore

        dist, _ = cKDTree(anchors).query(xyz, k=1)
        return np.asarray(dist, dtype=np.float64)
    except ImportError:
        # scipy yoksa parça parça brute-force: 80k × 500 matrisi tek seferde
        # kurmak belleği şişirir, 4k'lık bloklara bölüyoruz.
        out = np.empty(len(xyz), dtype=np.float64)
        step = 4096
        for i in range(0, len(xyz), step):
            block = xyz[i : i + step]
            d = np.linalg.norm(block[:, None, :] - anchors[None, :, :], axis=2)
            out[i : i + step] = d.min(axis=1)
        return out


def stress_away_from_constraint(
    node_inputs: np.ndarray,
    node_outputs: np.ndarray,
    standoff_mm: float,
) -> dict[str, Any]:
    """Kısıttan `standoff_mm` uzaktaki düğümler üzerinden max von Mises.

    Döndürür: değer, kaç düğümün hesaba girdiği, maskenin payı. Maske
    çok agresifse (düğümlerin neredeyse tamamı elenmişse) sonuç anlamsız
    olur; çağıran taraf `n_nodes_used` ile bunu görebilsin diye
    döndürüyoruz.
    """
    vm = node_outputs[:, _OUT["von_mises_mpa"]].astype(np.float64)
    dist = distance_to_constraint(node_inputs)
    keep = dist >= standoff_mm
    n_used = int(keep.sum())

    if n_used == 0:
        return {
            "max_von_mises_away": None,
            "n_nodes_used": 0,
            "fraction_used": 0.0,
            "standoff_mm": standoff_mm,
            "warning": (
                "Hiçbir düğüm maskeyi geçmedi — standoff modele göre çok "
                "büyük. Daha küçük bir oran deneyin."
            ),
        }

    return {
        "max_von_mises_away": float(vm[keep].max()),
        "max_von_mises_all": float(vm.max()) if vm.size else None,
        "n_nodes_used": n_used,
        "fraction_used": float(n_used / len(vm)),
        "standoff_mm": standoff_mm,
    }


def recompute_from_sample(
    train_npz: Path,
    characteristic_length: float,
    standoff_ratio: float = DEFAULT_STANDOFF_RATIO,
) -> dict[str, Any] | None:
    """Kaydedilmiş bir eğitim örneğinden maskeli gerilmeyi hesaplar.

    Çözümü tekrarlamaz — yalnız diskteki `.train.npz`'yi okur, yani mevcut
    run'lara geriye dönük uygulanabilir.
    """
    if not train_npz.is_file():
        return None
    try:
        with np.load(train_npz) as z:
            if "node_inputs" not in z or "node_outputs" not in z:
                logger.warning("Eksik kanal: %s", train_npz)
                return None
            X = z["node_inputs"]
            Y = z["node_outputs"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Örnek okunamadı %s: %s", train_npz, exc)
        return None

    if X.ndim != 2 or Y.ndim != 2 or len(X) != len(Y):
        logger.warning("Tutarsız boyut: %s", train_npz)
        return None

    standoff = float(characteristic_length) * float(standoff_ratio)
    out = stress_away_from_constraint(X, Y, standoff)
    out["standoff_ratio"] = standoff_ratio
    out["characteristic_length"] = characteristic_length
    return out
