"""Kullanıcı oluşturur / anahtarını yeniler, düz metin anahtarı BİR KEZ yazar.

    python scripts/create_api_key.py "Mustafa"        → yeni kullanıcı + anahtar
    python scripts/create_api_key.py "Mustafa" --rotate  → mevcut kullanıcıya yeni anahtar
    python scripts/create_api_key.py --list

WeWeb'de: her isteğe `Authorization: Bearer <anahtar>` başlığı.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main  # noqa: E402,F401 — .env + model kayıtları
from app.auth import generate_key, hash_key  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        if a.list:
            for u in db.query(User).order_by(User.id):
                print(f"{u.id:4d}  {u.name:24s}  aktif={u.is_active}  {u.created_at:%Y-%m-%d}")
            return
        if not a.name:
            sys.exit("kullanıcı adı gerekli")
        user = db.query(User).filter(User.name == a.name).first()
        key = generate_key()
        if user is None:
            user = User(name=a.name, api_key_hash=hash_key(key))
            db.add(user)
            what = "oluşturuldu"
        elif a.rotate:
            user.api_key_hash = hash_key(key)
            what = "anahtarı yenilendi"
        else:
            sys.exit(f"'{a.name}' zaten var; yeni anahtar için --rotate")
        db.commit()
        print(f"{user.name} {what} (id={user.id})")
        print("ANAHTAR (bir daha gösterilmez):")
        print(key)
    finally:
        db.close()


if __name__ == "__main__":
    main()
