# OpenRadioss çalıştırma imajı — yalnız crash (Faz 1) için.
#
# Neden: OpenRadioss resmi dağıtımı Linux ikilisi; Windows geliştirme
# makinesinde Docker Desktop (WSL2) zaten var. Backend Windows'ta kalır,
# starter/engine'i `docker run` ile bu imajda koşturur (bkz.
# app/solvers/openradioss.py, OPENRADIOSS_DOCKER_IMAGE). Codespace'te aynı
# ikili /opt/openradioss altına doğrudan kurulur; iki yol da aynı betiği
# kullanır.
#
# Derleme:  docker build -t simsurrogate-openradioss:latest-20260728 \
#             -f backend/docker/openradioss/Dockerfile .
# (bağlam = depo kökü; betik .devcontainer/ altından kopyalanır)
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgfortran5 libgomp1 unzip ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

ARG OPENRADIOSS_RELEASE=latest-20260728
ENV OPENRADIOSS_HOME=/opt/openradioss \
    OPENRADIOSS_RELEASE=${OPENRADIOSS_RELEASE}
COPY .devcontainer/install_openradioss.sh /tmp/install_openradioss.sh
# Windows checkout'ta betik CRLF olabilir; bash satır sonundaki CR yüzünden
# "command not found" (127) verir. CR'ler çalıştırmadan önce silinir.
RUN tr -d '\r' < /tmp/install_openradioss.sh > /tmp/install_or.sh \
    && chmod +x /tmp/install_or.sh && /tmp/install_or.sh \
    && rm /tmp/install_openradioss.sh /tmp/install_or.sh \
    && test -x /opt/openradioss/exec/starter_linux64_gf \
    && test -x /opt/openradioss/exec/engine_linux64_gf

# Resmi INSTALL.md: cfg dosyaları ve hm_reader/h3d kütüphaneleri.
ENV RAD_CFG_PATH=/opt/openradioss/hm_cfg_files \
    RAD_H3D_PATH=/opt/openradioss/extlib/h3d/lib/linux64 \
    LD_LIBRARY_PATH=/opt/openradioss/extlib/hm_reader/linux64:/opt/openradioss/extlib/h3d/lib/linux64 \
    OMP_STACKSIZE=400m \
    OMP_NUM_THREADS=4 \
    PATH=/opt/openradioss/exec:${PATH}

WORKDIR /work
