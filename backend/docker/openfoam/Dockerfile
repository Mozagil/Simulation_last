# OpenFOAM (ESI v2412) + cfMesh — yalnız CFD (Faz 2.5b) için.
#
# Resmi imaj (opencfd/openfoam-default:2412) cfMesh (cartesianMesh) içermez;
# ESI cfMesh'i ayrı bir topluluk modülü olarak dağıtır (GPL v3):
#   https://develop.openfoam.com/Community/integration-cfmesh
# Son etiket v2406 (v2412 için ayrı etiket yok; v2312 ile aynı kod). Modül
# resmi imajın içinde derlenip OpenFOAM'un kendi bin/lib klasörlerine
# kurulur (-prefix=openfoam), böylece giriş noktası (/openfoam/run) ve
# backend'in `docker run` komutu değişmez. snappyHexMesh ve diğer her şey
# resmi imajla aynıdır.
#
# Kullanıcı kararı 2026-10-09: "ikisini de yap" — cfMesh, snappyHexMesh'e
# seçilebilir ikinci mesh'leyici (NLGEOM gibi). docs/LICENSING.md "OpenFOAM".
#
# Derleme (bağlam = depo kökü):
#   docker build -t simsurrogate-openfoam:2412-cfmesh -f backend/docker/openfoam/Dockerfile .
# Backend: OPENFOAM_DOCKER_IMAGE=simsurrogate-openfoam:2412-cfmesh
FROM opencfd/openfoam-default:2412

ARG CFMESH_TAG=v2406

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${CFMESH_TAG}" \
        https://develop.openfoam.com/Community/integration-cfmesh.git /opt/cfmesh-src \
    && bash -c 'source /usr/lib/openfoam/openfoam2412/etc/bashrc \
        && cd /opt/cfmesh-src \
        && ./Allwmake -j "$(nproc)" -prefix=openfoam > /opt/cfmesh-build.log 2>&1; \
        tail -20 /opt/cfmesh-build.log; \
        command -v cartesianMesh' \
    && test -n "$(bash -c 'source /usr/lib/openfoam/openfoam2412/etc/bashrc && command -v cartesianMesh')" \
    && rm -rf /opt/cfmesh-src/.git
