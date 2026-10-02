# OpenRadioss çalıştırma imajı — yalnız crash (Faz 1) için.
#
# DURUM (2026-10-02): OpenRadioss'un resmi GitHub deposu ve sürüm paketleri
# 29 Eylül – 1 Ekim 2026 arasında yayından kalktı (Siemens, Radioss'u
# "Simcenter Radioss R&D Program" adlı shared-source programa taşıdı).
# Resmi indirme (.devcontainer/install_openradioss.sh) artık 404 verir.
#
# Kaynak: vendor/openradioss-latest-20260728-linux64-agpl.tar.gz — son açık
# sürümün (latest-20260728) Linux ikilileri, kart tanımları ve AGPL v3
# bildirimi (COPYRIGHT.md). Docker Hub'daki dheiny/openradioss-solver:1.0.37
# imajından çıkarıldı, sha256 vendor/README.md'de. AGPL geri alınamaz; bu
# kopya bu lisansla kullanılabilir. Yama ve yeni sürüm GELMEYECEK —
# docs/LICENSING.md "OpenRadioss".
#
# Backend bu imajı `docker run` ile çağırır (OPENRADIOSS_DOCKER_IMAGE,
# OPENRADIOSS_DOCKER_HOME; bkz. app/solvers/openradioss.py). Kurulum kökü
# /opt/OpenRadioss/OpenRadioss (arşivdeki klasör adı korunur).
#
# Derleme (bağlam = depo kökü):
#   docker build -t simsurrogate-openradioss:1.0.37 -f backend/docker/openradioss/Dockerfile .
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgfortran5 libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY vendor/openradioss-latest-20260728-linux64-agpl.tar.gz /tmp/openradioss.tar.gz
RUN mkdir -p /opt/OpenRadioss \
    && tar -xzf /tmp/openradioss.tar.gz -C /opt/OpenRadioss \
    && rm /tmp/openradioss.tar.gz \
    && chmod +x /opt/OpenRadioss/OpenRadioss/exec/* \
    && test -x /opt/OpenRadioss/OpenRadioss/exec/starter_linux64_gf \
    && test -x /opt/OpenRadioss/OpenRadioss/exec/engine_linux64_gf \
    && test -x /opt/OpenRadioss/OpenRadioss/exec/th_to_csv_linux64_gf \
    && grep -q "Affero" /opt/OpenRadioss/OpenRadioss/COPYRIGHT.md

# Resmi INSTALL.md ortamı (adaptör docker run'a da -e ile geçer).
ENV OPENRADIOSS_HOME=/opt/OpenRadioss/OpenRadioss \
    RAD_CFG_PATH=/opt/OpenRadioss/OpenRadioss/hm_cfg_files \
    RAD_H3D_PATH=/opt/OpenRadioss/OpenRadioss/extlib/h3d/lib/linux64 \
    LD_LIBRARY_PATH=/opt/OpenRadioss/OpenRadioss/extlib/hm_reader/linux64:/opt/OpenRadioss/OpenRadioss/extlib/h3d/lib/linux64 \
    OMP_STACKSIZE=400m \
    OMP_NUM_THREADS=4 \
    PATH=/opt/OpenRadioss/OpenRadioss/exec:${PATH}

WORKDIR /work
