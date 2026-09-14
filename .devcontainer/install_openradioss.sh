#!/usr/bin/env bash
# OpenRadioss resmi Linux ikilisi — lisans sunucusu yok (AGPL, bkz. docs/LICENSING.md).
# Kaynak derlenmez. Idempotent: starter+engine varsa indirmez.
set -euo pipefail

DEST="${OPENRADIOSS_HOME:-/opt/openradioss}"
RELEASE="${OPENRADIOSS_RELEASE:-latest-20260728}"
URL="https://github.com/OpenRadioss/OpenRadioss/releases/download/${RELEASE}/OpenRadioss_linux64.zip"

if [[ -x "${DEST}/exec/starter_linux64_gf" && -x "${DEST}/exec/engine_linux64_gf" ]]; then
  echo "OpenRadioss zaten kurulu: ${DEST} (${RELEASE})"
  exit 0
fi

echo "--- OpenRadioss ${RELEASE} indiriliyor ---"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "${tmp}/or.zip" "$URL"
unzip -q "${tmp}/or.zip" -d "${tmp}/unpack"

starter="$(find "${tmp}/unpack" -type f -name 'starter_linux64_gf' | head -n1 || true)"
if [[ -z "$starter" ]]; then
  echo "HATA: zip içinde starter_linux64_gf yok"
  find "${tmp}/unpack" -maxdepth 3 -type d
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
echo "OpenRadioss kuruldu: ${DEST}"
