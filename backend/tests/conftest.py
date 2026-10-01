"""Testler geliştirme veritabanına (cae_dev) DEĞİL, `cae_test`'e gider (TODO 8.2).

NEDEN: birçok test `SessionLocal()` / `TestClient(app)` ile gerçek bağlantıyı
kullanıyor ve her tam koşu cae_dev'e ~13 şablonsuz run, 16 `TestCustomSteel_*`
malzemesi bırakıyordu (ölçüldü: 44 malzeme, 458 box.step run'ı birikmişti).
Rollback yaklaşımı `TestClient` üzerinden giden isteklerde çalışmaz — her
istek kendi session'ını açıp commit eder. Ayrı veritabanı tek sağlam yol.

NASIL: `app.db.session` motoru import anında DATABASE_URL'den kurar ve
`.env`'i `override=False` ile yükler — yani burada ortam değişkenini
`app` import edilmeden ÖNCE vermek yeter. pytest `conftest.py`'yi test
modüllerinden önce yükler. Veritabanı yoksa `postgres` bakım veritabanı
üzerinden yaratılır; şema `Base.metadata.create_all` ile kurulur.

Kapatmak: `CAE_TESTS_USE_DEV_DB=1` (yalnız bilinçli bakım işleri için).
Sunucuya ulaşılamıyorsa hiçbir şey değişmez — DB isteyen testler zaten
kendi `skip` mantığıyla atlanıyor.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

_ENV = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
_DEFAULT = "postgresql+psycopg2://postgres:postgres@localhost:5432/cae_dev"
TEST_DB = "cae_test"


def _test_url(url: str) -> str:
    head, _, name = url.rpartition("/")
    return f"{head}/{TEST_DB}" if name else url


def _ensure_database(url: str) -> bool:
    """`cae_test` yoksa yaratır. Sunucu yoksa False."""
    try:
        import psycopg2
        from sqlalchemy.engine import make_url

        u = make_url(url)
        conn = psycopg2.connect(
            host=u.host or "localhost", port=u.port or 5432, user=u.username,
            password=u.password, dbname="postgres", connect_timeout=3,
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{TEST_DB}"')
        conn.close()
        return True
    except Exception:  # noqa: BLE001 — sunucu yok/izin yok: dokunma
        return False


if os.environ.get("CAE_TESTS_USE_DEV_DB") != "1":
    _current = os.environ.get("DATABASE_URL") or _ENV.get("DATABASE_URL") or _DEFAULT
    if TEST_DB not in _current and _current.startswith("postgresql"):
        _url = _test_url(_current)
        if _ensure_database(_url):
            os.environ["DATABASE_URL"] = _url


@pytest.fixture(scope="session", autouse=True)
def _test_schema():
    """Şemayı test veritabanında kur (tüm modeller `app.main` ile kaydolur)."""
    if TEST_DB not in os.environ.get("DATABASE_URL", ""):
        yield
        return
    # `create_all` DEĞİL alembic: modeller Postgres'e özgü `server_default`
    # taşıyor (`analysis_runs.excluded` boolean, varsayılan tam sayı) ve
    # create_all bunda patlıyor; migration zinciri gerçek şemayı verir.
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=root, check=True, capture_output=True, timeout=300,
            env={**os.environ, "PYTHONPATH": str(root)},
        )
    except Exception as exc:  # noqa: BLE001 — bağlantı yoksa testler kendileri atlar
        print(f"[conftest] cae_test şeması kurulamadı: {exc}", file=sys.stderr)
        yield
        return
    # `uploads/` süreç genelinde TEK klasör: test run'ı id=306 ile dev'in
    # `uploads/runs/306` klasörüne, test geometrisi `uploads/306.step`
    # dosyasına yazardı. Test kimlikleri dev'in asla ulaşmayacağı bir
    # aralıktan başlar; TRUNCATE sayaçları sıfırlamadığı için bir kez yeter.
    try:
        from sqlalchemy import text

        from app.db.session import engine

        with engine.begin() as conn:
            for seq in ("analysis_runs_id_seq", "geometries_id_seq", "materials_id_seq"):
                conn.execute(text(
                    f"SELECT setval('{seq}', GREATEST((SELECT last_value FROM {seq}), 10000000))"
                ))
    except Exception as exc:  # noqa: BLE001
        print(f"[conftest] sayaç ofseti uygulanamadı: {exc}", file=sys.stderr)
    yield


@pytest.fixture(autouse=True)
def _no_openradioss_docker_env(monkeypatch):
    """Geliştirici .env'i OPENRADIOSS_DOCKER_IMAGE tanımlar (app.main yükler);
    crash testleri 'ikili yok' / yerel yol senaryolarını sınar. Docker'ı
    isteyen test kendi monkeypatch'iyle açar."""
    monkeypatch.delenv("OPENRADIOSS_DOCKER_IMAGE", raising=False)
    monkeypatch.delenv("OPENRADIOSS_DOCKER_HOME", raising=False)
