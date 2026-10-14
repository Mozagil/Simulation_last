"""Crash koşusu hata kodları (kullanıcı isteği 2026-10-14).

Iraksama bir uyarı değil, hatadır: koşu "failed" kaydedilir, diagnostics["error"]
= {"code", "title", "detail"}. Kodlar sabittir (arayüz ve belgeler "Hata #n" der);
yeni kod sona eklenir, mevcut numara değiştirilmez.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# kod → (başlık, açıklama)
CRASH_ERRORS: dict[int, tuple[str, str]] = {
    1: (
        "Çözüm ıraksadı",
        "Engine listing'inde enerji NaN oldu (sayısal kararsızlık). Bu andan sonraki "
        "sonuçlar geçersiz; eğri ve animasyon yalnız ıraksama anına kadar anlamlı.",
    ),
    2: (
        "Starter hatası",
        "Model kontrolü (starter) hata verdi; engine koşmadı. Starter .out'taki ERROR ID'lere bak.",
    ),
    3: (
        "Çözücü anormal sonlandı",
        "Engine sıfırdan farklı çıkış koduyla bitti (error termination). Log dosyasına bak.",
    ),
    4: ("Zaman aşımı", "Çözücü süre sınırında bitmedi ve durduruldu."),
    5: ("OpenRadioss bulunamadı", "Sunucuda çözücü ikilisi / Docker imajı yok; koşu başlamadı."),
    9: ("Sınıflanmamış hata", "Koşu bilinen bir sebeple eşleşmeyen bir hatayla bitti."),
}


def crash_error(code: int, detail: str = "") -> dict[str, Any]:
    title, desc = CRASH_ERRORS[code]
    return {"code": code, "title": title, "description": desc, "detail": detail}


def error_message(err: dict[str, Any]) -> str:
    """İş mesajı: "Hata #1 — Çözüm ıraksadı: t = 0.0143 ms"."""
    text = f"Hata #{err['code']} — {err['title']}"
    return f"{text}: {err['detail']}" if err.get("detail") else text


def diverged_error(t_ms: float) -> dict[str, Any]:
    return crash_error(1, f"t = {t_ms:.4g} ms'den sonra enerji NaN")


def classify_failure(message: str, work_dir: Path | None = None) -> dict[str, Any]:
    """Adaptör / çağıran hata metninden kod. Starter hatasında .out ERROR ID'leri eklenir."""
    low = message.lower()
    if "bulunamadı" in low and "openradioss" in low:
        return crash_error(5, message)
    if "zaman aşımı" in low:
        return crash_error(4, message)
    if "starter hata" in low:
        ids: list[str] = []
        if work_dir is not None:
            from app.postprocess.openradioss_th import parse_starter_messages

            for out in sorted(work_dir.glob("*_0000.out"))[:1]:
                ids = sorted(parse_starter_messages(out)["errors"], key=lambda s: int(s) if s.isdigit() else 0)
        return crash_error(2, f"ERROR ID {', '.join(ids)}" if ids else message)
    if re.search(r"hata \(exit=-?\d+\)", low):
        return crash_error(3, message)
    return crash_error(9, message)
