#!/usr/bin/env bash
# Codespace / devcontainer kurulum betiği.
#
# Sistem paketleri Dockerfile'da; burada yalnız ÇALIŞMA ALANINA bağlı olanlar
# var (requirements.txt ve package.json ancak container oluşturulduktan sonra
# erişilebilir).
#
# `set -e`: bir adım patlarsa betik durur ve Codespace kurulum log'unda
# kırmızı görünür. Sessizce devam edip eksik bir ortamla başlamak, hatayı
# saatler sonra "uvicorn: command not found" olarak bulmaya yol açıyordu.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "--- Python bağımlılıkları ---"
pip install --no-cache-dir -r "$ROOT/backend/requirements.txt"

echo "--- Node bağımlılıkları ---"
cd "$ROOT/frontend" && npm install

echo "--- PostgreSQL ---"
# Postgres docker-compose ile geliyor. Codespace içinde Docker kullanılabilir
# olmayabilir; o durumda uyarıp devam ediyoruz — geliştirici elle başlatabilir
# ve geometri/mesh işleri veritabanı olmadan da çalışır.
if docker info >/dev/null 2>&1; then
  cd "$ROOT" && docker compose up -d
  # Postgres'in bağlantı kabul etmesini bekle; hemen ardından alembic
  # çalıştırmak "connection refused" ile patlıyordu.
  for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  echo "--- Migration ---"
  cd "$ROOT/backend" && alembic upgrade head
else
  echo "UYARI: Docker yok — Postgres başlatılamadı."
  echo "       Elle: docker compose up -d && cd backend && alembic upgrade head"
fi

echo "--- Doğrulama ---"
which ccx || { echo "HATA: ccx bulunamadı"; exit 1; }
python -c "import gmsh; print('gmsh OK')"
echo "Kurulum tamam."
