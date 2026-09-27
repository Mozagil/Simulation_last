"""Bearer API anahtarı ile kimlik (WeWeb → backend).

Karar (2026-09-26): WeWeb tarayıcıdan doğrudan backend'e çağrı yapar; her
isteğe `Authorization: Bearer <anahtar>` ekler. Anahtar kullanıcı başına,
DB'de SHA-256 özeti (`users.api_key_hash`).

Kapı `AUTH_REQUIRED` ortam değişkeniyle açılır (varsayılan kapalı):
- kapalı: başlık yoksa anonim devam (bugünkü geliştirme/test akışı aynen);
  başlık VARSA doğrulanır — geçersiz anahtar yine 401 (sessizce anonim
  sayılmaz, yanlış anahtarla "çalışıyor" izlenimi verilmesin).
- açık: başlık yoksa 401. `/health` her zaman açık.

Veri kapsamı: geometri sahibine bağlıdır (`geometries.owner_id`); sahipli
geometriye başka kullanıcı 404 alır (varlığı da sızmasın). `owner_id` NULL
olan eski kayıtlar herkese açık kalır — geçiş verisi silinmez.
"""

from __future__ import annotations

import hashlib
import os
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User

import contextvars

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.db.session import SessionLocal

KEY_PREFIX = "cae_"

#: İstek boyunca geçerli kullanıcı. Middleware yazar; yardımcılar
#: (`_get_geometry_or_404`, `list_runs`) okur — 23 uç noktaya tek tek
#: bağımlılık eklemek yerine.
current_user_var: contextvars.ContextVar["User | None"] = contextvars.ContextVar("current_user", default=None)

#: Anahtarsız her zaman açık yollar.
PUBLIC_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Her istekte anahtarı çözer, `current_user_var` ve `request.state.user`'a yazar."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        token = _bearer(request)
        user = None
        if token is not None:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.api_key_hash == hash_key(token)).first()
            finally:
                db.close()
            if user is None or not user.is_active:
                return JSONResponse({"detail": "API anahtarı geçersiz."}, status_code=401)
        elif auth_required() and not path.startswith(PUBLIC_PATHS) and request.method != "OPTIONS":
            return JSONResponse(
                {"detail": "API anahtarı gerekli (Authorization: Bearer …)."}, status_code=401
            )
        request.state.user = user
        tok = current_user_var.set(user)
        try:
            return await call_next(request)
        finally:
            current_user_var.reset(tok)


def current_user() -> "User | None":
    return current_user_var.get()


def auth_required() -> bool:
    return os.environ.get("AUTH_REQUIRED", "0").strip().lower() in ("1", "true", "yes")


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_key() -> str:
    """Düz metin anahtar — yalnız üretim anında görülür."""
    return KEY_PREFIX + secrets.token_urlsafe(32)


def _bearer(request: Request) -> str | None:
    raw = request.headers.get("authorization") or ""
    scheme, _, token = raw.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Anahtar geçerliyse User; başlık yoksa ve kapı kapalıysa None."""
    token = _bearer(request)
    if token is None:
        if auth_required():
            raise HTTPException(status_code=401, detail="API anahtarı gerekli (Authorization: Bearer …).")
        return None
    user = db.query(User).filter(User.api_key_hash == hash_key(token)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="API anahtarı geçersiz.")
    return user


def owner_matches(owner_id: int | None, user: User | None) -> bool:
    """Sahipsiz kayıt herkese açık; sahipli kayıt yalnız sahibine."""
    return owner_id is None or (user is not None and user.id == owner_id)
