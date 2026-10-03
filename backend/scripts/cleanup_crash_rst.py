r"""Eski crash işlerinin Radioss restart (*.rst) dosyalarını siler (1.17g).

Varsayılan KURU koşu: yalnız listeler ve toplam boyutu yazar. Silmek için
`--apply`. Restart desteği yok; .rst dosyaları hiçbir yerde okunmuyor.
1.17g'den sonra çözülen işlerde zaten tutulmuyor (CRASH_KEEP_RST=1 hariç).

Kullanım (backend kökünden):
    .\.venv\Scripts\python.exe scripts/cleanup_crash_rst.py           # kuru
    .\.venv\Scripts\python.exe scripts/cleanup_crash_rst.py --apply   # sil
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    apply = "--apply" in sys.argv
    files = sorted((ROOT / "uploads" / "crash").glob("*/*.rst"))
    total = sum(f.stat().st_size for f in files)
    for f in files:
        if apply:
            f.unlink()
    print(f"{'silindi' if apply else 'silinecek (kuru koşu)'}: {len(files)} dosya, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
