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
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from app.ml.ood import bounds_from_matrix, is_out_of_domain
from app.ml.scalar_features import COMMON_KEYS, FEATURE_KEYS, TARGET_KEYS
from app.ml.scalar_rf import MIN_HOLDOUT_SAMPLES, MIN_SAMPLES, split_metrics

DEFAULT_LOGLIN_PATH = Path("uploads") / "models" / "scalar_loglinear.joblib"

#: ESKİ (kirişe sabitlenmiş) tasarım. `design_spec` taşımayan, bu değişiklikten
#: önce kaydedilmiş bundle'lar bununla okunur. Yeni eğitimde tasarım VERİDEN
#: kurulur (`design_spec_for`) — kiriş için bu kurallar aynı tasarımı üretir.
LOG_FEATURE_KEYS = (
    "length",
    "thickness",
    "width",
    "element_size",
    "youngs_modulus",
    "poisson_ratio",
)
ABS_LOG_FEATURE_KEYS = ("load_fy",)
DESIGN_KEYS = tuple(LOG_FEATURE_KEYS) + tuple(f"|{k}|" for k in ABS_LOG_FEATURE_KEYS)

LEGACY_SPEC: dict[str, Any] = {
    "feature_keys": list(FEATURE_KEYS),
    "log_keys": list(LOG_FEATURE_KEYS),
    "abs_log_keys": list(ABS_LOG_FEATURE_KEYS),
    "indicator_keys": [],
}

#: Logu alınan ortak (şablondan bağımsız) sütunlar.
_LOG_COMMON = ("element_size", "youngs_modulus", "poisson_ratio")
#: Yük sütunları: işaret atılır, büyüklüğün logu alınır — yalnız eğitim
#: verisinde SIFIRDAN FARKLI olanlar (sıfır sütunun logu anlamsız, sabit
#: bir sütun ekleyip üs tablosunu kirletirdi).
_LOAD_KEYS = ("load_fx", "load_fy", "load_fz", "pressure_mpa")

#: log(0) → −inf olmasın diye taban. Fiziksel büyüklükler bunun çok üstünde.
_FLOOR = 1e-12


def design_spec_for(feature_keys: list[str] | tuple[str, ...], X: np.ndarray) -> dict[str, Any]:
    """Özellik anahtarlarından ve veriden log tasarımını kurar.

    - şablon geometri alanları + eleman boyutu + E + ν → log
    - sıfırdan farklı yük bileşenleri → |x|'in logu
    - kategorik göstergeler (`ad=seçenek`) → olduğu gibi (çarpan etkisi)
    Kiriş için sonuç `LEGACY_SPEC` ile aynı sütunlar, aynı sıra.
    """
    keys = list(feature_keys)
    mat = np.asarray(X, dtype=np.float64).reshape(-1, len(keys))
    idx = {k: i for i, k in enumerate(keys)}
    geo = [k for k in keys if k not in COMMON_KEYS and "=" not in k]
    return {
        "feature_keys": keys,
        # Hibritin artık katmanına eklenen geometri ORANLARI (tüm ikililer).
        # Ölçüldü (plaka study 5): ham özelliklerle u %0.64 / σ %1.86;
        # oranlarla u %0.29 / σ %1.30 — şablona özgü elle özellik (d/W)
        # yazmadan aynı sonuç. Kirişte etkisiz (%0.17 / %1.92 → %1.86).
        "ratio_pairs": [[a, b] for i, a in enumerate(geo) for b in geo[i + 1:]],
        "log_keys": geo + [k for k in _LOG_COMMON if k in idx],
        "abs_log_keys": [
            k for k in _LOAD_KEYS if k in idx and bool(np.any(mat[:, idx[k]] != 0.0))
        ],
        "indicator_keys": [k for k in keys if "=" in k],
    }


def design_keys_of(spec: dict[str, Any]) -> list[str]:
    return (
        list(spec["log_keys"])
        + [f"|{k}|" for k in spec["abs_log_keys"]]
        + list(spec["indicator_keys"])
    )


def to_log_features(X: np.ndarray, spec: dict[str, Any] | None = None) -> np.ndarray:
    """Ham özellik matrisi → log tasarım matrisi."""
    spec = spec or LEGACY_SPEC
    keys = spec["feature_keys"]
    idx = {k: i for i, k in enumerate(keys)}
    mat = np.asarray(X, dtype=np.float64).reshape(-1, len(keys))
    cols = [np.log(np.maximum(mat[:, idx[k]], _FLOOR)) for k in spec["log_keys"]]
    cols += [np.log(np.maximum(np.abs(mat[:, idx[k]]), _FLOOR)) for k in spec["abs_log_keys"]]
    cols += [mat[:, idx[k]] for k in spec["indicator_keys"]]
    return np.column_stack(cols)


def constant_columns(
    X: np.ndarray, *, spec: dict[str, Any] | None = None, rtol: float = 1e-4
) -> list[str]:
    """Korpus boyunca değişmeyen tasarım sütunları — üsleri belirlenemez."""
    spec = spec or LEGACY_SPEC
    design = to_log_features(X, spec)
    names = design_keys_of(spec)
    return [n for i, n in enumerate(names) if float(np.ptp(design[:, i])) <= rtol]


def collinear_pairs(
    X: np.ndarray, *, spec: dict[str, Any] | None = None, threshold: float = 0.999
) -> list[list[str]]:
    """Log uzayında birebir bağımlı sütun çiftleri.

    Sabit oranlı mesh (`es = oran × T`) bu durumu üretir: üs iki sütun
    arasında keyfi bölünür, ayrı ayrı okunamaz.
    """
    spec = spec or LEGACY_SPEC
    design = to_log_features(X, spec)
    names = design_keys_of(spec)
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
                out.append([names[i], names[j]])
    return out


def _exponents(
    models: dict[str, LinearRegression | None],
    constants: list[str],
    collinear: list[list[str]],
    design_keys: list[str],
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
        # Yeterli veri olmayan hedefin modeli None olur (hedef-bazlı maskeleme).
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
            for name, coef in zip(design_keys, model.coef_)
        ]
    return out


def residual_inputs(X: np.ndarray, spec: dict[str, Any]) -> np.ndarray:
    """Artık katmanının girdisi: ham özellikler + geometri oranları."""
    keys = spec["feature_keys"]
    idx = {k: i for i, k in enumerate(keys)}
    mat = np.asarray(X, dtype=np.float64).reshape(-1, len(keys))
    cols = [mat]
    for a, b in spec.get("ratio_pairs") or []:
        den = mat[:, idx[b]]
        cols.append(
            np.divide(mat[:, idx[a]], den, out=np.zeros_like(den), where=den != 0)[:, None]
        )
    return np.hstack(cols)


def _residual_rf(seed: int) -> RandomForestRegressor:
    return RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=seed)


def train_scalar_loglinear(
    X: np.ndarray,
    y: np.ndarray,
    *,
    feature_keys: list[str] | tuple[str, ...] | None = None,
    residual_rf: bool = False,
    seed: int = 2026,
    test_size: float = 0.25,
) -> dict[str, Any]:
    """Log uzayında en küçük kareler. Hedefler pozitif olmalı.

    `feature_keys`: X'in sütun adları (şablona özgü; yoksa eski kiriş
    anahtarları). `residual_rf=True` → HİBRİT tür: lineer modelin log
    artıkları ham özelliklerde bir Random Forest ile öğrenilir.

    NEDEN HİBRİT — ölçüldü (delikli plaka study 5, 198 örnek, 148/50):
    σ_max = Kt(d/W)·F/((W−d)·T) saf kuvvet yasası değil (Kt, d/W'nin
    doğrusal olmayan fonksiyonu; log(W−d) ne W'nin ne d'nin kuvveti).
    u MAPE: log-log %1.53 → hibrit %0.60; σ: %2.22 → %1.32. Log-log iskelet
    ekstrapolasyonu ve üsleri taşır, RF yalnız küçük düzeltmeyi öğrenir.
    """
    from sklearn.model_selection import train_test_split

    if X.shape[0] < MIN_SAMPLES:
        raise ValueError(f"En az {MIN_SAMPLES} çözülmüş örnek gerekir (var: {X.shape[0]}).")
    feature_keys = list(feature_keys) if feature_keys is not None else list(FEATURE_KEYS)
    if X.shape[1] != len(feature_keys):
        raise ValueError(
            f"X {X.shape[1]} sütunlu ama {len(feature_keys)} özellik anahtarı verildi."
        )
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

    spec = design_spec_for(feature_keys, X)
    design_keys = design_keys_of(spec)

    has_holdout = X.shape[0] >= MIN_HOLDOUT_SAMPLES
    if has_holdout:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    else:
        X_tr, y_tr = X, y
        X_te = y_te = None

    A_tr = to_log_features(X_tr, spec)
    A_te = to_log_features(X_te, spec) if X_te is not None else None
    Z_tr = residual_inputs(X_tr, spec) if residual_rf else None
    Z_te = residual_inputs(X_te, spec) if residual_rf and X_te is not None else None

    models: dict[str, LinearRegression | None] = {}
    residuals: dict[str, RandomForestRegressor | None] = {}
    pred_tr = np.zeros_like(y_tr)
    pred_te = np.zeros_like(y_te) if y_te is not None else None
    for i, key in enumerate(TARGET_KEYS):
        # Hedef bazında maskeleme: bir skaler bazı run'larda yoksa (NaN)
        # o run yalnız O hedef için atlanır, diğerleri kullanılmaya devam
        # eder. Aksi halde tek eksik skaler tüm satırı düşürürdü.
        ok = np.isfinite(y_tr[:, i])
        if int(ok.sum()) < MIN_SAMPLES:
            models[key] = None
            residuals[key] = None
            pred_tr[:, i] = np.nan
            if pred_te is not None:
                pred_te[:, i] = np.nan
            continue
        model = LinearRegression()
        target = np.log(y_tr[ok, i])
        model.fit(A_tr[ok], target)
        models[key] = model
        log_tr = model.predict(A_tr)
        rf = None
        if residual_rf:
            rf = _residual_rf(seed)
            rf.fit(Z_tr[ok], target - log_tr[ok])
            log_tr = log_tr + rf.predict(Z_tr)
        residuals[key] = rf
        # Tahmin LOG uzayında yapılır, metrikler ham birimde ölçülür —
        # RF ile kıyaslanabilir olması için (bkz. `split_metrics`).
        pred_tr[:, i] = np.where(ok, np.exp(log_tr), np.nan)
        if pred_te is not None and A_te is not None:
            log_te = model.predict(A_te)
            if rf is not None:
                log_te = log_te + rf.predict(Z_te)
            ok_te = np.isfinite(y_te[:, i])
            pred_te[:, i] = np.where(ok_te, np.exp(log_te), np.nan)

    constants = constant_columns(X, spec=spec)
    collinear = collinear_pairs(X, spec=spec)
    return {
        "kind": "scalar_hybrid" if residual_rf else "scalar_loglinear",
        "feature_keys": feature_keys,
        "design_spec": spec,
        "design_keys": design_keys,
        "target_keys": list(TARGET_KEYS),
        "models": models,
        "residual_models": residuals if residual_rf else None,
        "bounds": bounds_from_matrix(X),
        "n_samples": int(X.shape[0]),
        "n_train": int(X_tr.shape[0]),
        "n_test": int(X_te.shape[0]) if X_te is not None else 0,
        "has_holdout": has_holdout,
        "seed": seed,
        "constant_features": constants,
        "collinear_features": collinear,
        # Hibritte üsler LİNEER iskeletin katsayılarıdır; RF düzeltmesi
        # bunlara dahil değildir.
        "exponents": _exponents(models, constants, collinear, design_keys),
        "metrics": {
            "train": split_metrics(y_tr, pred_tr, TARGET_KEYS),
            "test": (
                split_metrics(y_te, pred_te, TARGET_KEYS)
                if has_holdout and y_te is not None and pred_te is not None
                else None
            ),
        },
    }


def train_scalar_hybrid(X: np.ndarray, y: np.ndarray, **kw: Any) -> dict[str, Any]:
    """Log-log iskelet + RF artık katmanı (bkz. `train_scalar_loglinear`)."""
    return train_scalar_loglinear(X, y, residual_rf=True, **kw)


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
    """`predict_scalar` ile AYNI sözlük şeması — çağıran tür farkını bilmez.

    Log-log ve hibrit ikisi de buradan tahmin eder. `design_spec` taşımayan
    eski bundle'lar eski kiriş tasarımıyla okunur.
    """
    vec = np.asarray(x, dtype=np.float64).reshape(1, -1)
    spec = bundle.get("design_spec") or LEGACY_SPEC
    design = to_log_features(vec, spec)
    residuals = bundle.get("residual_models") or {}
    z = residual_inputs(vec, spec) if residuals else None
    preds: dict[str, float | None] = {}
    for key in bundle["target_keys"]:
        # Model yoksa uydurma sayı yerine None — arayüz "—" gösterir.
        m = (bundle.get("models") or {}).get(key)
        if m is None:
            preds[key] = None
            continue
        log_pred = float(m.predict(design)[0])
        rf = residuals.get(key)
        if rf is not None:
            log_pred += float(rf.predict(z)[0])
        preds[key] = float(np.exp(log_pred))
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
