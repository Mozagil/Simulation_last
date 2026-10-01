# OpenRadioss çalıştırma imajı — yalnız crash (Faz 1) için.
#
# DURUM (2026-10-02): OpenRadioss'un resmi GitHub deposu ve sürüm paketleri
# 29 Eylül – 1 Ekim 2026 arasında yayından kalktı (Siemens, Radioss'u
# "Simcenter Radioss R&D Program" adlı kapalı/shared-source programa taşıdı).
# Resmi indirme (.devcontainer/install_openradioss.sh) artık 404 verir.
#
# Elimizdeki kaynak: topluluk imajı dheiny/openradioss-solver:1.0.37
# (Ağustos 2026). İçinde AGPL v3 ile dağıtılmış son açık ikililer var
# (COPYRIGHT.md: "Copyright (C) 1986-2026 Altair Engineering Inc., GNU AGPL").
# AGPL geri alınamaz; bu kopya sonsuza dek bu lisansla kullanılabilir. Yama
# ve yeni sürüm GELMEYECEK — bkz. docs/LICENSING.md "OpenRadioss donmuş sürüm".
#
# Backend bu imajı `docker run` ile çağırır (OPENRADIOSS_DOCKER_IMAGE,
# OPENRADIOSS_DOCKER_HOME; bkz. app/solvers/openradioss.py). Kurulum kökü bu
# imajda /opt/OpenRadioss/OpenRadioss.
#
# Derleme:  docker build -t simsurrogate-openradioss:1.0.37 \
#             -f backend/docker/openradioss/Dockerfile .
# Yedek:    docker save simsurrogate-openradioss:1.0.37 | gzip > vendor/openradioss-1.0.37.tar.gz
#           (üçüncü kişi imajı Docker Hub'dan kalkarsa diye; vendor/ git'e girmez)
FROM dheiny/openradioss-solver:1.0.37

ENV OPENRADIOSS_HOME=/opt/OpenRadioss/OpenRadioss \
    RAD_CFG_PATH=/opt/OpenRadioss/OpenRadioss/hm_cfg_files \
    RAD_H3D_PATH=/opt/OpenRadioss/OpenRadioss/extlib/h3d/lib/linux64 \
    LD_LIBRARY_PATH=/opt/OpenRadioss/OpenRadioss/extlib/hm_reader/linux64:/opt/OpenRadioss/OpenRadioss/extlib/h3d/lib/linux64 \
    OMP_STACKSIZE=400m \
    OMP_NUM_THREADS=4

# Kurulum ve lisans bildirimi imajda mı? Eksikse build patlasın.
RUN test -x /opt/OpenRadioss/OpenRadioss/exec/starter_linux64_gf \
    && test -x /opt/OpenRadioss/OpenRadioss/exec/engine_linux64_gf \
    && grep -q "Affero" /opt/OpenRadioss/OpenRadioss/COPYRIGHT.md

ENTRYPOINT []
WORKDIR /work
