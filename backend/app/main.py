"""FastAPI uygulama giriş noktası."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.geometry import MESH_DIR, TESSELLATION_DIR
from app.api.geometry import router as geometry_router
from app.api.health import router as health_router
from app.api.components import router as components_router
from app.api.materials import router as materials_router
from app.api.dataset import router as dataset_router
from app.api.solve import RUNS_DIR
from app.api.solve import router as solve_router
from app.api.templates import router as templates_router
from app.api.doe import router as doe_router
from app.api.surrogate import router as surrogate_router
from app.api.crash import CRASH_DIR
from app.api.crash import router as crash_router
from app.api.crash_runs import router as crash_runs_router
from app.api.crash_scenario import router as crash_scenario_router
from app.api.crash_catalog import router as crash_catalog_router
from app.api.crash_doe import router as crash_doe_router
from app.api.crash_ml import router as crash_ml_router
from app.api.cfd import CFD_DIR
from app.api.cfd import router as cfd_router
from app.api.cfd_runs import router as cfd_runs_router
from app.api.cfd_mesh import router as cfd_mesh_router
from app.api.cfd_rocket import router as cfd_rocket_router
from app.api.cfd_sweep import router as cfd_sweep_router

# Uvicorn kendi logger'larını (uvicorn.*) yapılandırıyor ama uygulama
# modüllerimizin (app.*) logger.info çağrıları root logger WARNING
# seviyesinde olduğu için varsayılan olarak görünmez. INFO seviyesini açıyoruz.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

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

from app.auth import ApiKeyMiddleware  # noqa: E402

# API anahtarı (WeWeb). CORS'tan SONRA eklenir ki dışta CORS kalsın:
# 401 yanıtları da CORS başlığı taşısın, tarayıcı gerçek hatayı görsün.
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(geometry_router)
app.include_router(materials_router)
app.include_router(components_router)
app.include_router(solve_router)
app.include_router(dataset_router)
app.include_router(templates_router)
app.include_router(doe_router)
app.include_router(surrogate_router)
app.include_router(crash_doe_router)  # /crash/doe (1.19c)
app.include_router(crash_ml_router)  # /crash/ml (1.19e)
app.include_router(crash_runs_router)  # /crash/runs — /crash/jobs'tan önce değil, ayrı önek
app.include_router(crash_router)
app.include_router(crash_scenario_router)  # /crash/scenario (1.17a)
app.include_router(crash_catalog_router)  # /crash/catalog (K0)
app.include_router(cfd_runs_router)  # /cfd/runs (Faz 2.4)
app.include_router(cfd_mesh_router)  # /cfd/mesh (Faz 2.5)
app.include_router(cfd_rocket_router)  # /cfd/rocket (R2)
app.include_router(cfd_sweep_router)  # /cfd/rocket/sweep (R5)
app.include_router(cfd_router)  # /cfd (Faz 2.2)

# Üretilen tessellation (STL) ve FEA mesh (.msh) dosyalarını HTTP ile sun.
Path(TESSELLATION_DIR).mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/tessellations",
    StaticFiles(directory=str(TESSELLATION_DIR)),
    name="tessellations",
)
Path(MESH_DIR).mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/meshes",
    StaticFiles(directory=str(MESH_DIR)),
    name="meshes",
)
Path(RUNS_DIR).mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/runs",
    StaticFiles(directory=str(RUNS_DIR)),
    name="runs",
)
Path(CRASH_DIR).mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/crash",
    StaticFiles(directory=str(CRASH_DIR)),
    name="crash_files",
)
Path(CFD_DIR).mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/cfd",
    StaticFiles(directory=str(CFD_DIR)),
    name="cfd_files",
)
