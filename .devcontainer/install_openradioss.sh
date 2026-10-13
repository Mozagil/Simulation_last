#!/usr/bin/env bash
# OpenRadioss Linux ikilisi — lisans sunucusu yok (AGPL, bkz. docs/LICENSING.md).
#
# Kaynak DEPODAKİ arşiv: vendor/openradioss-latest-20260728-linux64-agpl.tar.gz
# (son açık sürüm, latest-20260728). Resmi GitHub deposu ve sürüm paketleri
# 29 Eyl – 1 Eki 2026 arasında kalktı; eski indirme adresi 404 verip Codespace
# imaj derlemesini düşürüyordu. Yerel Docker imajı
# (backend/docker/openradioss/Dockerfile) da aynı arşivden kurulur.
#
# Kullanım: install_openradioss.sh <arşiv.tar.gz> — idempotent.
set -euo pipefail

ARCHIVE="${1:-/tmp/openradioss.tar.gz}"
DEST="${OPENRADIOSS_HOME:-/opt/openradioss}"
SHA256="5ed4cad8e544a981f1b24f1b4e720570fdc4812051f259eebada4bd29f7cb3ce"

if [[ -x "${DEST}/exec/starter_linux64_gf" && -x "${DEST}/exec/engine_linux64_gf" ]]; then
  echo "OpenRadioss zaten kurulu: ${DEST}"
  exit 0
fi

if [[ ! -f "$ARCHIVE" ]]; then
  echo "HATA: arşiv yok: ${ARCHIVE} (vendor/openradioss-latest-20260728-linux64-agpl.tar.gz)"
  exit 1
fi
echo "${SHA256}  ${ARCHIVE}" | sha256sum -c -

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tar -xzf "$ARCHIVE" -C "$tmp"

starter="$(find "$tmp" -type f -name 'starter_linux64_gf' | head -n1 || true)"
if [[ -z "$starter" ]]; then
  echo "HATA: arşivde starter_linux64_gf yok"
  find "$tmp" -maxdepth 3 -type d
  exit 1
fi
root="$(cd "$(dirname "$starter")/.." && pwd)"

mkdir -p "$DEST"
cp -a "$root"/. "$DEST"
chmod +x "${DEST}/exec/"* || true

if [[ ! -x "${DEST}/exec/starter_linux64_gf" || ! -x "${DEST}/exec/engine_linux64_gf" ]]; then
  echo "HATA: OpenRadioss ikilileri ${DEST}/exec altında yok"
  ls -la "${DEST}/exec" || true
  exit 1
fi
echo "OpenRadioss kuruldu: ${DEST} (latest-20260728, depodaki arşiv)"
