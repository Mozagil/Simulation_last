"""FastAPI uygulama giriş noktası."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.geometry import TESSELLATION_DIR
from app.api.geometry import router as geometry_router
from app.api.health import router as health_router

app = FastAPI(
    title="CAE Analiz Otomasyon Platformu",
    version="0.0.1",
)

# Geliştirme ortamında frontend (Vite dev server) farklı bir origin'den
# (localhost:5173 ya da Codespaces forwarded URL) backend'e istek atıyor.
# CORS_ALLOW_ORIGINS ortam değişkeniyle prod'da daraltılabilir.
allow_origins_env = os.environ.get("CORS_ALLOW_ORIGINS")
if allow_origins_env:
    allow_origins = [origin.strip() for origin in allow_origins_env.split(",")]
else:
    # Varsayım (CLAUDE.md kural 6): geliştirme aşamasında origin listesini
    # kısıtlamıyoruz, prod'a geçerken CORS_ALLOW_ORIGINS ile daraltılmalı.
    allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(geometry_router)

# Üretilen tessellation (STL) dosyalarını frontend'in three.js viewer'ının
# okuyabileceği bir HTTP yolu üzerinden sun.
Path(TESSELLATION_DIR).mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/tessellations",
    StaticFiles(directory=str(TESSELLATION_DIR)),
    name="tessellations",
)
