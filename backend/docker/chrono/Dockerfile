# Project Chrono worker (Faz 5) — PyChrono, conda ile. Yalnız MBD koşuları için;
# FastAPI imajından ayrı. Derleme (bağlam = depo kökü):
#   docker build -t simsurrogate-chrono:9.0 -f backend/docker/chrono/Dockerfile .
# Backend: CHRONO_DOCKER_IMAGE=simsurrogate-chrono:9.0
# Lisans: Chrono BSD-3 (docs/LICENSING.md'ye eklenecek, 5.1).
FROM continuumio/miniconda3:24.9.2-0

ARG CHRONO_VERSION=9.0.1
RUN conda create -y -n chrono -c projectchrono -c conda-forge python=3.11 "pychrono=${CHRONO_VERSION}" \
    && conda clean -afy
ENV PATH=/opt/conda/envs/chrono/bin:$PATH
WORKDIR /work
ENTRYPOINT []
CMD ["python", "-c", "import pychrono, sys; print('pychrono', getattr(pychrono, '__version__', '?'))"]
