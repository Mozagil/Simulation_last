"""Bağımsızlık testi: analitik kapı öğrenilen üstelleri etkiliyor mu?

SORU: Korpus kapısı `require_analytic_ok=True` ile çalışıyor, yani FEA'nın
analitikten çok saptığı run'lar eğitim setinden çıkarılıyor (kirişte 12
run). Bu, veriyi teoriyle uyumlulara doğru hafifçe filtreliyor.

"Model kiriş teorisini yeniden keşfetti" iddiamız bundan etkileniyor mu?

YÖNTEM: Aynı veriyi iki kez süz — kapı açık ve kapalı — iki model eğit,
öğrenilen üstelleri karşılaştır. Üsteller değişmiyorsa kapı sonucu
belirlemiyor demektir; sonuç bağımsızdır.

KULLANIM (backend klasöründen):
    python -m scripts.independence_check
    python -m scripts.independence_check --template plate_with_hole
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from app.db.session import SessionLocal
from app.ml.corpus import CorpusSpec, select_training_runs
from app.ml.scalar_features import FEATURE_KEYS, TARGET_KEYS, collect_scalar_table
from app.ml.scalar_rf import train_scalar_rf

#: Kapalı form üsteller — model bunlara yakınsa fiziği öğrenmiş demektir.
THEORY = {
    "cantilever_beam": {
        "max_displacement": {"length": 3, "thickness": -3, "width": -1, "load_fy": 1},
        "max_von_mises": {"length": 1, "thickness": -2, "width": -1, "load_fy": 1},
        # Maskeli gerilme AYNI fiziktir — yalnız ölçüm konumu farklı
        # (kısıttan 1×T uzakta). Teorik üsteller bu yüzden aynı.
        "max_von_mises_away": {
            "length": 1,
            "thickness": -2,
            "width": -1,
            "load_fy": 1,
        },
    },
    "plate_with_hole": {
        # σ = Kt(d/W) · F/((W−d)·T) — SAF KUVVET YASASI DEĞİL.
        # log(W−d) ne W'nin ne d'nin kuvveti; Kt de oranın doğrusal
        # olmayan fonksiyonu. Üstellerin teoriye oturması BEKLENMİYOR;
        # burada bakılacak şey MAPE ve RF artık katmanının katkısı.
        "max_von_mises": {"thickness": -1, "load_fx": 1},
    },
}


def _train(db, template_id: str, require_analytic_ok: bool, seed: int):
    corpus = select_training_runs(
        db,
        CorpusSpec(template_id=template_id, require_analytic_ok=require_analytic_ok),
    )
    X, y, ids = collect_scalar_table(db, corpus.run_ids)
    if X.shape[0] < 8:
        raise SystemExit(f"Yetersiz örnek: {X.shape[0]}")
    bundle = train_scalar_rf(X, y, seed=seed)
    return corpus, bundle


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="cantilever_beam")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        c_on, b_on = _train(db, args.template, True, args.seed)
        c_off, b_off = _train(db, args.template, False, args.seed)
    finally:
        db.close()

    print(f"\n=== {args.template} · analitik kapı etkisi ===\n")
    print(f"kapı AÇIK  : {c_on.n_kept:4d} örnek  (elenen: {c_on.dropped})")
    print(f"kapı KAPALI: {c_off.n_kept:4d} örnek  (elenen: {c_off.dropped})")
    fark = c_off.n_kept - c_on.n_kept
    print(f"kapının elediği: {fark} run\n")

    if fark == 0:
        print("Kapı hiçbir şey elemiyor — bu veride test anlamsız, sonuç")
        print("zaten bağımsız.\n")

    theory = THEORY.get(args.template, {})
    max_delta = 0.0

    for target in TARGET_KEYS:
        e_on = (b_on.get("exponents") or {}).get(target)
        e_off = (b_off.get("exponents") or {}).get(target)
        if not e_on or not e_off:
            continue
        m_on = b_on["metrics"]["test"].get(target) or {}
        m_off = b_off["metrics"]["test"].get(target) or {}
        print(f"--- {target}")
        print(
            f"    MAPE  kapı açık %{(m_on.get('mape') or 0) * 100:.2f}"
            f"   ·  kapalı %{(m_off.get('mape') or 0) * 100:.2f}"
        )
        th = theory.get(target, {})
        print(f"    {'özellik':16s} {'açık':>9s} {'kapalı':>9s} {'fark':>8s} {'teori':>7s}")
        for feat in sorted(set(e_on) | set(e_off)):
            a = e_on.get(feat)
            b = e_off.get(feat)
            if a is None or b is None:
                continue
            d = abs(a - b)
            max_delta = max(max_delta, d)
            t = th.get(feat)
            print(
                f"    {feat:16s} {a:+9.3f} {b:+9.3f} {d:8.3f}"
                f" {('%+d' % t) if t is not None else '—':>7s}"
            )
        print()

    print("=== SONUÇ ===")
    print(f"En büyük üstel farkı: {max_delta:.3f}")
    if max_delta < 0.10:
        print("Üsteller pratikte DEĞİŞMEDİ → analitik kapı sonucu belirlemiyor.")
        print("'Model fiziği bağımsız olarak öğrendi' iddiası sağlam.")
    elif max_delta < 0.30:
        print("Küçük kayma var. Kapı sonucu belirlemiyor ama etkisi sıfır değil;")
        print("raporlarken belirtmek gerekir.")
    else:
        print("BELİRGİN FARK. Üsteller kapıya bağlı — 'fiziği öğrendi' iddiası")
        print("bu haliyle savunulamaz, kapının ne elediğine bakmak gerekir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
