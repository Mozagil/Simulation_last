"""Skaler Random Forest baseline (0.5.6).

Amaç: veri boru hattının ucuza doğrulanması. Skaler surrogate ürün hedefi
değildir — kontur buradan çizilmez.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from app.ml.ood import bounds_from_matrix, is_out_of_domain
from app.ml.scalar_features import FEATURE_KEYS, TARGET_KEYS

MIN_SAMPLES = 8
DEFAULT_MODEL_PATH = Path("uploads") / "models" / "scalar_rf.joblib"



#: Log dönüşümü için alt eşik — bu değerin altındaki girdi/hedefler
#: logaritmaya sokulamaz.
_LOG_EPS = 1e-12


def _logmask(M: np.ndarray) -> np.ndarray:
    """Hangi sütunlar log'lanabilir: işareti TUTARLI (hep + ya da hep −)
    ve sabit değil.

    ÖLÇTÜK, DÜZELTTİK: ilk sürüm yalnız pozitif sütunlara bakıyordu.
    `load_fy` ankastre kirişte hep NEGATİF (−y yönü) olduğu için maskeden
    düşüyor, log modelinde doğrusal terim olarak kalıyordu — ve doğrusal
    bir terim çarpımsal bağımlılığı yakalayamaz. Sonuç: yük üsteli +1
    yerine −0.006 öğreniliyordu, yani model yükün etkisini hiç
    görmüyordu. İşaret tutarlıysa |x|'in logu alınır; işaret zaten sabit
    olduğu için bilgi kaybı yok.

    Sabit sütunlar (tek malzemeli korpusta E, ν) log'lansa da bilgi
    taşımaz; işareti karışık ya da sıfır içeren sütunlar doğrusal kalır.
    """
    A = np.abs(M)
    consistent = ((M > _LOG_EPS).all(axis=0)) | ((M < -_LOG_EPS).all(axis=0))
    varies = A.max(axis=0) > A.min(axis=0)
    return consistent & varies


def _apply_log(M: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Maskeli sütunlarda log|x|. İşaret sütun içinde sabit olduğu için
    mutlak değer bilgi kaybettirmez."""
    out = M.astype(np.float64).copy()
    if mask.any():
        out[:, mask] = np.log(np.maximum(np.abs(out[:, mask]), _LOG_EPS))
    return out


class _PowerLawModel:
    """log-log doğrusal taban + artık üzerinde Random Forest.

    NEDEN: Bu ailedeki fizik bir KUVVET YASASI. Ankastre kirişte
    u = 4FL³/(E·W·T³) → log u = log4F + 3logL − logE − logW − 3logT,
    yani log uzayında tam DOĞRUSAL. Random Forest bu düz yüzeyi dik
    basamaklarla taklit etmeye çalışır ve 225 örnekle beceremez.

    ÖLÇTÜK (225 sentetik örnek, gerçek kutu, ölçülen gürültüyle):
        RF ham girdi + ham hedef : MAPE %42.9
        RF ham girdi + log hedef : MAPE %27.0
        log-log doğrusal         : MAPE  %0.8   ← gürültü tabanı %1
        log-log doğrusal + RF    : MAPE  %0.8

    Saf kuvvet yasası olmayan şablonlarda (delikli plakada gerilme
    yığılması gibi) doğrusal taban yetmez; artık RF onu yakalar.
    Sentetik Kt sapması eklendiğinde: yalnız doğrusal %1.13 → +RF %0.93.
    Yani RF saf durumda zarar vermiyor, sapmalı durumda kazandırıyor.

    Hedef ya da girdi pozitif değilse o eksende log atlanır; model yine
    çalışır, sadece o eksende doğrusal kalır.
    """

    def __init__(self, seed: int, n_estimators: int) -> None:
        self.seed = seed
        self.n_estimators = n_estimators
        self.feat_mask: np.ndarray | None = None
        self.log_target = False
        self.lin: LinearRegression | None = None
        self.rf: RandomForestRegressor | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_PowerLawModel":
        self.feat_mask = _logmask(X)
        Xl = _apply_log(X, self.feat_mask)
        self.log_target = bool((y > _LOG_EPS).all())
        t = np.log(y) if self.log_target else y.astype(np.float64)

        self.lin = LinearRegression().fit(Xl, t)
        residual = t - self.lin.predict(Xl)
        # min_samples_leaf=2: artık çoğunlukla gürültüdür, tek örneklik
        # yapraklar onu ezberler.
        self.rf = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.seed,
            min_samples_leaf=2,
        ).fit(Xl, residual)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self.lin is not None and self.rf is not None and self.feat_mask is not None
        Xl = _apply_log(X, self.feat_mask)
        t = self.lin.predict(Xl) + self.rf.predict(Xl)
        return np.exp(t) if self.log_target else t

    def exponents(self, feature_keys: tuple[str, ...]) -> dict[str, float] | None:
        """Doğrusal tabanın üstelleri — fizikle karşılaştırmak için.

        YALNIZ log'lanan özellikler raporlanır. Sabit sütunlar (tek
        malzemeli korpusta E, ν, dimension) log'lanmaz ve doğrusal modelde
        kesişimi emerler; katsayıları büyük görünür ama üstel DEĞİLDİR,
        raporda yanıltıcı olur.

        Kirişte deplasman için beklenen: L +3, T −3, W −1, F +1.
        Model bunlara yakın çıkıyorsa ezberlemiyor, fiziği öğreniyor
        demektir — R²'den çok daha güçlü bir doğrulama.
        """
        if self.lin is None or self.feat_mask is None:
            return None
        return {
            key: float(c)
            for key, c, m in zip(feature_keys, self.lin.coef_, self.feat_mask)
            if m
        }


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, keys: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i, key in enumerate(keys):
        yt = y_true[:, i]
        yp = y_pred[:, i]
        finite = np.isfinite(yt) & np.isfinite(yp)
        if not finite.any():
            out[key] = None
            continue
        yt = yt[finite]
        yp = yp[finite]
        mae = float(mean_absolute_error(yt, yp))
        denom = np.maximum(np.abs(yt), 1e-12)
        mape = float(np.mean(np.abs(yt - yp) / denom))
        out[key] = {
            "mae": mae,
            "mape": mape,
            "r2": float(r2_score(yt, yp)) if len(yt) >= 2 else None,
        }
    return out


def train_scalar_rf(
    X: np.ndarray,
    y: np.ndarray,
    *,
    seed: int = 2026,
    n_estimators: int = 80,
    test_size: float = 0.25,
) -> dict[str, Any]:
    if X.shape[0] < MIN_SAMPLES:
        raise ValueError(f"En az {MIN_SAMPLES} çözülmüş örnek gerekir (var: {X.shape[0]}).")

    # ÖLÇTÜK, DÜZELTTİK: eski kod 12'den az örnekte `X_te = X_tr` atıyordu,
    # yani `metrics.test` aslında EĞİTİM metriğiydi ve arayüzde "test R²"
    # diye gösteriliyordu. 8 örneklik modelde "test R² 0.739" görünüyordu;
    # gerçekte hiç test edilmemişti. Sessiz yanlış bir sayı, hiç sayı
    # olmamasından kötüdür — artık holdout yapılamıyorsa test metriği
    # None döner ve bunun sebebi `holdout` alanında yazılır.
    # Hedef sütun sayısı TARGET_KEYS ile uyuşmalı. Eksikse NaN ile
    # tamamlanır: çağıran yeni bir hedefi (ör. max_von_mises_away)
    # bilmiyorsa ya da o skaler henüz hesaplanmamışsa patlamak yerine
    # o hedef atlanır — hedef bazlı maskeleme zaten bunu destekliyor.
    # Fazlaysa sessizce kırpmak veri kaybını gizler, o yüzden hata.
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

    n = int(X.shape[0])
    #: Holdout için gereken en az örnek: test tarafında en az 2 satır
    #: olmalı ki R² tanımlı olsun (tek satırda varyans sıfır).
    min_for_holdout = max(8, int(np.ceil(2 / max(test_size, 1e-9))))
    has_holdout = n >= min_for_holdout
    if has_holdout:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    else:
        X_tr, y_tr = X, y
        X_te = y_te = None

    models: dict[str, _PowerLawModel] = {}
    exponents: dict[str, dict[str, float] | None] = {}
    pred_tr = np.zeros_like(y_tr)
    pred_te = np.zeros_like(y_te) if y_te is not None else None
    for i, key in enumerate(TARGET_KEYS):
        # Hedef bazında maskeleme: bir skaler bazı run'larda yoksa (NaN)
        # o run yalnız O hedef için atlanır, diğer hedefler kullanılmaya
        # devam eder. Aksi halde tek eksik skaler tüm satırı düşürürdü.
        ok = np.isfinite(y_tr[:, i])
        if ok.sum() < MIN_SAMPLES:
            models[key] = None
            exponents[key] = None
            pred_tr[:, i] = np.nan
            if pred_te is not None:
                pred_te[:, i] = np.nan
            continue
        m = _PowerLawModel(seed=seed, n_estimators=n_estimators).fit(
            X_tr[ok], y_tr[ok, i]
        )
        models[key] = m
        exponents[key] = m.exponents(tuple(FEATURE_KEYS))
        pred_tr[:, i] = np.where(ok, m.predict(X_tr), np.nan)
        if X_te is not None and pred_te is not None:
            ok_te = np.isfinite(y_te[:, i])
            pred_te[:, i] = np.where(ok_te, m.predict(X_te), np.nan)

    bundle = {
        "kind": "scalar_rf",
        "feature_keys": list(FEATURE_KEYS),
        "target_keys": list(TARGET_KEYS),
        "models": models,
        "exponents": exponents,
        "bounds": bounds_from_matrix(X),
        "n_samples": int(X.shape[0]),
        "n_train": int(X_tr.shape[0]),
        "n_test": int(X_te.shape[0]) if X_te is not None else 0,
        "seed": seed,
        "holdout": (
            {"ok": True, "test_size": test_size}
            if has_holdout
            else {
                "ok": False,
                "reason": (
                    f"Holdout için en az {min_for_holdout} örnek gerekir "
                    f"(var: {n}). Test metriği hesaplanmadı."
                ),
            }
        ),
        "metrics": {
            "train": _metrics(y_tr, pred_tr, TARGET_KEYS),
            "test": (
                _metrics(y_te, pred_te, TARGET_KEYS)
                if (y_te is not None and pred_te is not None)
                else None
            ),
        },
    }
    return bundle


def save_scalar_rf(bundle: dict[str, Any], path: Path | None = None) -> Path:
    dest = path or DEFAULT_MODEL_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, dest)
    return dest


def load_scalar_rf(path: Path | None = None) -> dict[str, Any] | None:
    dest = path or DEFAULT_MODEL_PATH
    if not dest.is_file():
        return None
    return joblib.load(dest)


def predict_scalar(
    bundle: dict[str, Any],
    x: np.ndarray,
) -> dict[str, Any]:
    vec = np.asarray(x, dtype=np.float64).reshape(1, -1)
    preds: dict[str, float | None] = {}
    for key in bundle["target_keys"]:
        # Hedef için yeterli veri yoksa model None olur (bkz. train_scalar_rf).
        # Uydurma sayı yerine None döner; arayüz "—" gösterir.
        model = (bundle.get("models") or {}).get(key)
        preds[key] = float(model.predict(vec)[0]) if model is not None else None
    ood = is_out_of_domain(vec.reshape(-1), bundle.get("bounds") or {})
    return {
        "kind": "scalar",
        "predictions": preds,
        "out_of_domain": ood,
    }


def public_metrics(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": bundle.get("kind"),
        "n_samples": bundle.get("n_samples"),
        "n_train": bundle.get("n_train"),
        "n_test": bundle.get("n_test"),
        "holdout": bundle.get("holdout"),
        "exponents": bundle.get("exponents"),
        "metrics": bundle.get("metrics"),
        "feature_keys": bundle.get("feature_keys"),
        "target_keys": bundle.get("target_keys"),
        "bounds": bundle.get("bounds"),
        "corpus": bundle.get("corpus"),
    }
