#!/usr/bin/env bash
# Codespace / devcontainer kurulum betiği.
#
# Sistem paketleri Dockerfile'da (önbelleklenir). Burada ÇALIŞMA ALANINA ve
# ORTAMA bağlı olan her şey var — bunlar image'a gömülemez çünkü ya repo
# dosyalarına ya da $CODESPACE_NAME gibi çalışma zamanı değişkenlerine
# ihtiyaç duyarlar.
#
# Bu listenin tamamı daha önce ELLE yapılıyordu ve her yeni Codespace'te
# baştan yaşanıyordu: pip/npm kurulumu, Postgres'i ayağa kaldırma, migration,
# ve en sinsisi — iki .env dosyasındaki host adları. Host adı her Codespace'te
# değiştiği için eski .env'ler sessizce yanlış adrese işaret ediyor ve hata
# tarayıcıda "CORS hatası" gibi görünüyordu.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== 1/6 Python bağımlılıkları ==="
pip install --no-cache-dir -r "$ROOT/backend/requirements.txt"

echo "=== 2/6 Node bağımlılıkları ==="
cd "$ROOT/frontend" && npm install

echo "=== 3/6 Ortam dosyaları (.env) ==="
# Frontend tarayıcıda çalışır: backend'e "localhost:8000" ile ulaşamaz, çünkü
# orada localhost KULLANICININ makinesidir. Codespace'in yönlendirilmiş
# adresi gerekir. Host adı her Codespace'te değiştiği için her kurulumda
# yeniden üretilir.
if [ -n "${CODESPACE_NAME:-}" ]; then
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  API_URL="https://${CODESPACE_NAME}-8000.${DOMAIN}"
else
  # Codespace dışı (yerel devcontainer): doğrudan localhost çalışır.
  API_URL="http://localhost:8000"
fi
printf 'VITE_API_BASE_URL=%s\n' "$API_URL" > "$ROOT/frontend/.env"
echo "frontend/.env -> $API_URL"

# Backend .env: CORS_ALLOW_ORIGINS BİLEREK yazılmıyor. main.py bu değişken
# boşken tüm origin'lere izin veriyor ve geliştirme için istediğimiz bu.
# Sabit bir origin yazmak, host adı değişince backend'in frontend'i
# reddetmesine yol açıyordu.
if [ ! -f "$ROOT/backend/.env" ]; then
  cat > "$ROOT/backend/.env" <<'ENVEOF'
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/cae_dev
ENVEOF
  echo "backend/.env oluşturuldu"
else
  echo "backend/.env zaten var, dokunulmadı"
fi

echo "=== 4/6 PostgreSQL ==="
if docker info >/dev/null 2>&1; then
  cd "$ROOT" && docker compose up -d
  # Bağlantı kabul etmesini bekle; hemen ardından alembic çalıştırmak
  # "connection refused" ile patlıyordu.
  for _ in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  echo "=== 5/6 Migration ==="
  cd "$ROOT/backend" && alembic upgrade head
else
  echo "UYARI: Docker yok — Postgres başlatılamadı."
  echo "       Elle: docker compose up -d && cd backend && alembic upgrade head"
fi

echo "=== 6/6 Doğrulama ==="
# Sessizce eksik bir ortamla başlamaktansa burada patlamak yeğdir: eksiklik
# aksi halde saatler sonra "uvicorn: command not found" ya da
# "libGLU.so.1 yok" olarak ortaya çıkıyordu.
which ccx >/dev/null || { echo "HATA: ccx (CalculiX) bulunamadı"; exit 1; }
python -c "import gmsh" || { echo "HATA: gmsh import edilemedi"; exit 1; }
python -c "import fastapi, sqlalchemy, psycopg2" || { echo "HATA: backend paketleri eksik"; exit 1; }

cat <<EOF

Kurulum tamam.

  Backend : cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
  Frontend: cd frontend && npm run dev -- --host 0.0.0.0

PORTS sekmesinden 5173 VE 8000 portlarını Public yapın — 8000 private
kalırsa tarayıcı isteği engeller ve hata konsola CORS hatası gibi düşer.
EOF
