"""FastAPI uygulama giriş noktası.

Faz 0 / Adım 0: boş iskelet + tek /health endpoint'i.
"""

from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(
    title="CAE Analiz Otomasyon Platformu",
    version="0.0.1",
)

app.include_router(health_router)
