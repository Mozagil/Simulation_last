#!/usr/bin/env bash
# Her Codespace başlatılışında (postStartCommand) çalışır.
#
# Amaç: ortam açıldığında hiçbir elle adım kalmasın —
#   1. .env dosyaları güncel Codespace adıyla üretilir
#   2. Postgres (docker compose), backend (uvicorn) ve frontend (vite) başlar
#   3. 5173 ve 8000 portları public yapılır
#
# Buradaki hiçbir adım ölümcül değil: bir servis başlamazsa diğerleri yine
# denenir; log'lar /tmp/simulation_last/ altında. `set -e` bilerek yok.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR=/tmp/simulation_last
mkdir -p "$LOG_DIR"

echo "--- .env ---"
if [ ! -f "$ROOT/backend/.env" ]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "backend/.env oluşturuldu (.env.example kopyası)"
fi

if [ -n "${CODESPACE_NAME:-}" ]; then
  # Codespace adı her yeni ortamda değişir; frontend/.env'i her başlatmada
  # yeniden yazıyoruz ki eski ada işaret eden bayat bir URL kalmasın.
  # NOT: Codespaces'te bu dosyayı elle düzenleme, sonraki restart'ta ezilir.
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  API_URL="https://${CODESPACE_NAME}-8000.${DOMAIN}"
  printf 'VITE_API_BASE_URL=%s\n' "$API_URL" > "$ROOT/frontend/.env"
  echo "frontend/.env -> $API_URL"
elif [ ! -f "$ROOT/frontend/.env" ]; then
  cp "$ROOT/frontend/.env.example" "$ROOT/frontend/.env"
  echo "frontend/.env oluşturuldu (localhost)"
fi

echo "--- PostgreSQL ---"
if docker info >/dev/null 2>&1; then
  (cd "$ROOT" && docker compose up -d) || echo "UYARI: docker compose up başarısız"
else
  echo "UYARI: Docker yok — Postgres başlatılamadı (elle: docker compose up -d)"
fi

echo "--- Backend (uvicorn :8000) ---"
if pgrep -f "uvicorn app.main:app" >/dev/null; then
  echo "zaten çalışıyor"
else
  (cd "$ROOT/backend" && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
      >"$LOG_DIR/backend.log" 2>&1 &)
  echo "başlatıldı, log: $LOG_DIR/backend.log"
fi

echo "--- Frontend (vite :5173) ---"
if pgrep -f "vite" >/dev/null; then
  echo "zaten çalışıyor"
else
  (cd "$ROOT/frontend" && nohup npm run dev -- --host 0.0.0.0 \
      >"$LOG_DIR/frontend.log" 2>&1 &)
  echo "başlatıldı, log: $LOG_DIR/frontend.log"
fi

echo "--- Port görünürlüğü ---"
if [ -n "${CODESPACE_NAME:-}" ] && command -v gh >/dev/null 2>&1; then
  # Portlar ancak süreçler dinlemeye başlayınca kayda giriyor; birkaç kez dene.
  ok=0
  for _ in $(seq 1 20); do
    if gh codespace ports visibility 5173:public 8000:public \
         --codespace "$CODESPACE_NAME" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 3
  done
  if [ "$ok" = 1 ]; then
    echo "5173 ve 8000 public"
    gh codespace ports --codespace "$CODESPACE_NAME" 2>/dev/null || true
  else
    echo "UYARI: port görünürlüğü ayarlanamadı. Elle:"
    echo "  gh codespace ports visibility 5173:public 8000:public --codespace \$CODESPACE_NAME"
  fi
else
  echo "Codespaces dışı ortam, atlandı"
fi

echo "--- Hazır ---"
if [ -n "${CODESPACE_NAME:-}" ]; then
  echo "Frontend: https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
fi
