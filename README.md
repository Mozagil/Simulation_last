# CAE Analiz Otomasyon Platformu

Kullanıcının parametre (yük, hız, geometri vb.) girdiği; backend'in geometri
(STEP/IGES) import edip mesh ürettiği, girdi dosyasını parametrize ettiği, solver'ı
sunucuda çalıştırdığı, sonuçları otomatik post-process ederek grafik/metrik ürettiği,
veritabanına kaydettiği ve frontend'de gösterdiği bir web platformu.

Tüm yığın açık kaynak: CalculiX (durability), OpenRadioss (crash), OpenFOAM (CFD),
mesh için Gmsh. Kullanıcı tarafında hiçbir CAE yazılımı kurulu olmasına gerek yok.

Çalışma kuralları ve mimari kararlar için bkz. [`CLAUDE.md`](./CLAUDE.md) ve `docs/`
klasörü:

- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — sistem mimarisi, veri akışı,
  solver/mesh adaptör arayüzleri
- [`docs/ROADMAP.md`](./docs/ROADMAP.md) — faz planı, mikro-adım listesi

## Mevcut durum

**Faz 0 — Durability pilotu (CalculiX + Gmsh), Adım 0: altyapı iskeleti.**
Şu an sadece boş bir FastAPI projesi ve `/health` endpoint'i var.

## Codespaces'te çalıştırma

Codespace açılınca `.devcontainer/start.sh` otomatik çalışır: `.env` dosyalarını
güncel Codespace adıyla üretir, Postgres + backend (:8000) + frontend (:5173)
sunucularını başlatır ve iki portu public yapar. Elle bir şey başlatmaya gerek yok.

- Frontend adresi: `https://$CODESPACE_NAME-5173.app.github.dev`
  (VS Code → PORTS sekmesindeki linke tıkla, adresi elle yazma)
- Sunucu logları: `/tmp/simulation_last/backend.log`, `/tmp/simulation_last/frontend.log`
- Bir sunucuyu yeniden başlatmak için: `pkill -f uvicorn` / `pkill -f vite`,
  sonra `bash .devcontainer/start.sh`
- `frontend/.env` her başlatmada yeniden yazılır; Codespaces'te elle düzenleme.

## Backend'i yerelde çalıştırma

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Doğrulama:

```bash
curl localhost:8000/health
# {"status":"ok"}
```

## Testleri çalıştırma

```bash
cd backend
pytest
```
