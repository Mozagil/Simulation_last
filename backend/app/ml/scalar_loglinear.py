"""Log-log lineer skaler model (0.6.3).

NEDEN AYRI BİR TÜR: kiriş hedefleri çarpımsal güç yasalarıdır —

    u = F·L³/(3·E·I),  I = W·T³/12     →     u ∝ F·L³·E⁻¹·W⁻¹·T⁻³
    σ = 6·F·L/(W·T²)                   →     σ ∝ F·L·W⁻¹·T⁻²

Random Forest parçalı-SABİT bir ortalayıcıdır: güç yasasını temsil edemez,
eğitim aralığının dışına çıkamaz ve tahminleri eğitim değerleriyle sınırlıdır.
Logaritma alındığında aynı ilişki TAM LİNEER olur ve katsayılar doğrudan
üslere karşılık gelir.

Ölçüldü (200 örneklik ankastre kiriş korpusu, aynı 150/50 ayrımı):

    model                test R² (u)   test MAPE (u)   doğrulama MAPE (u)
    RF ham                 0.8950         %18.87            %16.15
    RF log hedef           0.8434         %17.05            %16.12
    log-log lineer         1.0000          %0.16             %0.09

Aynı korpusta öğrenilen üsler teoriyle örtüştü: L 2.9895 (3), T −2.9875 (−3),
W −1.0080 (−1), F 1.0004 (1), element_size 0.0085 (0).

RF KALDIRILMADI: güç yasası olmayan şablonlarda (gerilme yığılma katsayısı
taşıyan delikli plaka, çentikli çubuk) log-log tam isabet etmez; orada RF
kıyas tabanı olarak gerekli.

SINIR 1 — sabit sütunlar: bir özellik korpus boyunca sabitse (tek malzemede
`youngs_modulus`, `poisson_ratio`) o üs VERİDEN BELİRLENEMEZ. Model o
sütunlara anlamsız bir katsayı uydurur ve başka bir malzemeye genellemez.

SINIR 2 — eşdoğrusal sütunlar: DOE sabit bir eleman ORANIYLA koşulursa
`element_size = oran × T` olur, yani log uzayında T ile birebir bağımlıdır.
O zaman gerçek −3 üssü ikisi arasında KEYFİ bölünür (ölçüldü: sabit oranlı
sentetik sette thickness −1.92 / element_size −1.08, toplamları doğru).
Tahmin bundan zarar görmez — eşdoğrusallık kestirimi bozar, uyumu değil —
ama katsayıları "üs" diye okumak yanıltıcı olur.

Her iki durumda da ilgili sütunlar `exponents` içinde `identifiable: false`
ve bir `reason` ile döner. Araç burada karar vermez, neyin bilinemez
olduğunu söyler.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression

from app.ml.ood import bounds_from_matrix, is_out_of_domain
from app.ml.scalar_features import FEATURE_KEYS, TARGET_KEYS
from app.ml.scalar_rf import MIN_HOLDOUT_SAMPLES, MIN_SAMPLES, split_metrics

DEFAULT_LOGLIN_PATH = Path("uploads") / "models" / "scalar_loglinear.joblib"

#: Logu alınan özellikler. Kalanlar (`load_fx`, `load_fz`, `pressure_mpa`,
#: `dimension`) ya sıfır olabilir ya da sayım/bayrak; logaritmaları tanımsız
#: ya da anlamsız olurdu.
LOG_FEATURE_KEYS = (
    "length",
    "thickness",
    "width",
    "element_size",
    "youngs_modulus",
    "poisson_ratio",
)

#: İşareti atılıp büyüklüğünün logu alınan özellikler. Yük yönü bu şablonda
#: sabit (−y); büyüklük bilgiyi taşır.
ABS_LOG_FEATURE_KEYS = ("load_fy",)

#: Modelin gördüğü sütun adları (sıra `to_log_features` ile aynı).
DESIGN_KEYS = tuple(LOG_FEATURE_KEYS) + tuple(f"|{k}|" for k in ABS_LOG_FEATURE_KEYS)

_IDX = {key: i for i, key in enumerate(FEATURE_KEYS)}
#: log(0) → −inf olmasın diye taban. Fiziksel büyüklükler bunun çok üstünde.
_FLOOR = 1e-12


def to_log_features(X: np.ndarray) -> np.ndarray:
    """Ham özellik matrisi → log tasarım matrisi (n, len(DESIGN_KEYS))."""
    mat = np.asarray(X, dtype=np.float64).reshape(-1, len(FEATURE_KEYS))
    cols = [np.log(np.maximum(mat[:, _IDX[k]], _FLOOR)) for k in LOG_FEATURE_KEYS]
    cols += [
        np.log(np.maximum(np.abs(mat[:, _IDX[k]]), _FLOOR)) for k in ABS_LOG_FEATURE_KEYS
    ]
    return np.column_stack(cols)


def constant_columns(X: np.ndarray, *, rtol: float = 1e-4) -> list[str]:
    """Korpus boyunca değişmeyen tasarım sütunları — üsleri belirlenemez."""
    design = to_log_features(X)
    out: list[str] = []
    for i, name in enumerate(DESIGN_KEYS):
        col = design[:, i]
        if float(col.max() - col.min()) <= rtol:
            out.append(name)
    return out


def collinear_pairs(X: np.ndarray, *, threshold: float = 0.999) -> list[list[str]]:
    """Log uzayında birebir bağımlı sütun çiftleri.

    Sabit oranlı mesh (`es = oran × T`) bu durumu üretir: üs iki sütun
    arasında keyfi bölünür, ayrı ayrı okunamaz.
    """
    design = to_log_features(X)
    # Sabit sütunlarda korelasyon 0/0'dır; onlar zaten `constant_columns`
    # tarafından işaretleniyor, burada atlanır (yoksa numpy uyarı basar).
    varying = np.ptp(design, axis=0) > 1e-9
    out: list[list[str]] = []
    for i in range(design.shape[1]):
        if not varying[i]:
            continue
        for j in range(i + 1, design.shape[1]):
            if not varying[j]:
                continue
            r = float(np.corrcoef(design[:, i], design[:, j])[0, 1])
            if abs(r) >= threshold:
                out.append([DESIGN_KEYS[i], DESIGN_KEYS[j]])
    return out


def _exponents(
    models: dict[str, LinearRegression],
    constants: list[str],
    collinear: list[list[str]],
) -> dict[str, Any]:
    reason: dict[str, str] = {}
    for pair in collinear:
        for name in pair:
            other = pair[1] if name == pair[0] else pair[0]
            reason.setdefault(name, f"{other} ile eşdoğrusal")
    for name in constants:
        reason[name] = "korpus boyunca sabit"

    out: dict[str, Any] = {}
    for key, model in models.items():
        # Yeterli veri olmayan hedefin modeli None olur (bkz.
        # train_scalar_loglinear hedef-bazlı maskeleme).
        if model is None:
            out[key] = None
            continue
        out[key] = [
            {
                "feature": name,
                "exponent": float(coef),
                "identifiable": name not in reason,
                "reason": reason.get(name),
            }
            for name, coef in zip(DESIGN_KEYS, model.coef_)
        ]
    return out


def train_scalar_loglinear(
    X: np.ndarray,
    y: np.ndarray,
    *,
    seed: int = 2026,
    test_size: float = 0.25,
) -> dict[str, Any]:
    """Log uzayında en küçük kareler. Hedefler pozitif olmalı."""
    from sklearn.model_selection import train_test_split

    if X.shape[0] < MIN_SAMPLES:
        raise ValueError(f"En az {MIN_SAMPLES} çözülmüş örnek gerekir (var: {X.shape[0]}).")
    # Hedef sütun sayısı TARGET_KEYS ile uyuşmalı. Eksikse NaN ile
    # tamamlanır: çağıran yeni bir hedefi (ör. `max_von_mises_away`)
    # bilmiyorsa ya da o skaler henüz hesaplanmamışsa patlamak yerine o
    # hedef atlanır. Fazlaysa sessizce kırpmak veri kaybını gizler → hata.
    y = np.asarray(y, dtype=np.float64)
    if y.ndim != 2:
        raise ValueError(f"y 2 boyutlu olmalı (geldi: {y.shape}).")
    n_targets = len(TARGET_KEYS)
    if y.shape[1] > n_targets:
        raise ValueError(
            f"y {y.shape[1]} sütunlu ama {n_targets} hedef tanımlı "
            f"({', '.join(TARGET_KEYS)})."
        )
    if y.shape[1] < n_targets:
        pad = np.full((y.shape[0], n_targets - y.shape[1]), np.nan)
        y = np.hstack([y, pad])

    # Pozitiflik kontrolü yalnız DOLU sütunlar için — NaN sütun
    # "bu hedef yok" demek, "geçersiz veri" değil.
    filled = ~np.isnan(y)
    if not np.all(y[filled] > 0.0):
        raise ValueError(
            "Log-log model pozitif hedef ister; sette sıfır ya da negatif "
            "max_displacement/max_von_mises var."
        )

    has_holdout = X.shape[0] >= MIN_HOLDOUT_SAMPLES
    if has_holdout:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    else:
        X_tr, y_tr = X, y
        X_te = y_te = None

    A_tr = to_log_features(X_tr)
    A_te = to_log_features(X_te) if X_te is not None else None

    models: dict[str, LinearRegression] = {}
    pred_tr = np.zeros_like(y_tr)
    pred_te = np.zeros_like(y_te) if y_te is not None else None
    for i, key in enumerate(TARGET_KEYS):
        # Hedef bazında maskeleme: bir skaler bazı run'larda yoksa (NaN)
        # o run yalnız O hedef için atlanır, diğerleri kullanılmaya devam
        # eder. Aksi halde tek eksik skaler tüm satırı düşürürdü.
        ok = np.isfinite(y_tr[:, i])
        if int(ok.sum()) < MIN_SAMPLES:
            models[key] = None
            pred_tr[:, i] = np.nan
            if pred_te is not None:
                pred_te[:, i] = np.nan
            continue
        model = LinearRegression()
        model.fit(A_tr[ok], np.log(y_tr[ok, i]))
        models[key] = model
        # Tahmin LOG uzayında yapılır, metrikler ham birimde ölçülür —
        # RF ile kıyaslanabilir olması için (bkz. `split_metrics`).
        pred_tr[:, i] = np.where(ok, np.exp(model.predict(A_tr)), np.nan)
        if pred_te is not None and A_te is not None:
            ok_te = np.isfinite(y_te[:, i])
            pred_te[:, i] = np.where(ok_te, np.exp(model.predict(A_te)), np.nan)

    constants = constant_columns(X)
    collinear = collinear_pairs(X)
    return {
        "kind": "scalar_loglinear",
        "feature_keys": list(FEATURE_KEYS),
        "design_keys": list(DESIGN_KEYS),
        "target_keys": list(TARGET_KEYS),
        "models": models,
        "bounds": bounds_from_matrix(X),
        "n_samples": int(X.shape[0]),
        "n_train": int(X_tr.shape[0]),
        "n_test": int(X_te.shape[0]) if X_te is not None else 0,
        "has_holdout": has_holdout,
        "seed": seed,
        "constant_features": constants,
        "collinear_features": collinear,
        "exponents": _exponents(models, constants, collinear),
        "metrics": {
            "train": split_metrics(y_tr, pred_tr, TARGET_KEYS),
            "test": (
                split_metrics(y_te, pred_te, TARGET_KEYS)
                if has_holdout and y_te is not None and pred_te is not None
                else None
            ),
        },
    }


def save_scalar_loglinear(bundle: dict[str, Any], path: Path | None = None) -> Path:
    dest = path or DEFAULT_LOGLIN_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, dest)
    return dest


def load_scalar_loglinear(path: Path | None = None) -> dict[str, Any] | None:
    dest = path or DEFAULT_LOGLIN_PATH
    if not dest.is_file():
        return None
    return joblib.load(dest)


def predict_scalar_loglinear(bundle: dict[str, Any], x: np.ndarray) -> dict[str, Any]:
    """`predict_scalar` ile AYNI sözlük şeması — çağıran tür farkını bilmez."""
    vec = np.asarray(x, dtype=np.float64).reshape(1, -1)
    design = to_log_features(vec)
    preds: dict[str, float] = {}
    for key in bundle["target_keys"]:
        # Model yoksa uydurma sayı yerine None — arayüz "—" gösterir.
        m = (bundle.get("models") or {}).get(key)
        preds[key] = (
            float(np.exp(m.predict(design)[0])) if m is not None else None
        )
    return {
        "kind": "scalar",
        "predictions": preds,
        "out_of_domain": is_out_of_domain(vec.reshape(-1), bundle.get("bounds") or {}),
    }


def public_metrics_loglinear(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": bundle.get("kind"),
        "n_samples": bundle.get("n_samples"),
        "n_train": bundle.get("n_train"),
        "n_test": bundle.get("n_test"),
        "has_holdout": bool(bundle.get("has_holdout", False)),
        "metrics": bundle.get("metrics"),
        "feature_keys": bundle.get("feature_keys"),
        "design_keys": bundle.get("design_keys"),
        "target_keys": bundle.get("target_keys"),
        "bounds": bundle.get("bounds"),
        "corpus": bundle.get("corpus"),
        "exponents": bundle.get("exponents"),
        "constant_features": bundle.get("constant_features"),
        "collinear_features": bundle.get("collinear_features"),
    }
