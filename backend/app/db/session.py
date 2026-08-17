"""SQLAlchemy engine ve session yönetimi.

DATABASE_URL ortam değişkeninden okunur (.env / .env.example'a bak).
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/cae_dev",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: her request için bir DB session verir, sonunda kapatır."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
