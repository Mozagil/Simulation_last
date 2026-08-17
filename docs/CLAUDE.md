# Proje: CAE Analiz Otomasyon Platformu (durability → crash)

Bu dosya, bu repoda çalışan her coding agent (Claude Code dahil) için bağlayıcı kuralları içerir.
Detaylar için `docs/` klasörüne bak: `ARCHITECTURE.md`, `ROADMAP.md`, `LICENSING.md`,
`CODING_STANDARDS.md`, `TESTING.md`. Bu dosyaları OKUMADAN kod yazma — özellikle
`TESTING.md`, çünkü çalışma şeklimizin temeli o.

## Projenin özeti

Kullanıcı parametre girer (yük, hız, geometri vb.) → backend geometriyi (STEP/IGES) alıp
mesh üretir → girdi dosyasını parametrize eder → solver'ı sunucuda çalıştırır → sonuçları
otomatik post-process edip grafik/metrik üretir → veritabanına kaydeder → frontend'de
gösterir. Faz 2'de bu veriden bir surrogate (ML tahmin) modeli eğitilir.

**ÖNEMLİ — güncellendi:** Bu projede ANSYS, HyperMesh veya LS-DYNA hiçbir fazda
kullanılmayacak. Tüm yığın (CAD import, mesh, solver, post-process) açık kaynak.
Kullanıcı tarafında (frontend'i açan kişide) hiçbir CAE yazılımı kurulu OLMAYACAK —
sunucuda da ticari lisans/lisans sunucusu gerekmiyor artık.

- **Durability solver:** CalculiX (açık kaynak, implicit)
- **Crash solver:** OpenRadioss (açık kaynak, explicit — Altair Radioss'un açık kaynak sürümü)
- **CFD solver:** OpenFOAM (açık kaynak, GPL)
- **Kompozit modelleme:** ayrı bir solver DEĞİL — CalculiX ve OpenRadioss'un kompozit
  katman (ply) desteği üzerine kurulu çapraz bir modül (bkz. `docs/ARCHITECTURE.md#kompozit-modelleme`)
- **Mesh:** Gmsh (tüm analiz tipleri için ortak, CFD'de snappyHexMesh ile birlikte)
- **Geometri import/preview:** STEP/IGES, bkz. `docs/ARCHITECTURE.md#geometri-ve-mesh`

## Mevcut faz

**FAZ 0 — Durability analizi (CalculiX + Gmsh).** Diğer fazlara henüz geçme.
Solver: CalculiX. Mesh: Gmsh. Post-process: pyLife (yorulma/fatigue).
Neden: pipeline'ı (geometri import → mesh → pre-process → solve → post-process → db →
frontend) uçtan uca çalışır hale getirmek. Faz geçişleri `docs/ROADMAP.md`'de —
şu an 4 analiz tipi (durability, crash, kompozit, CFD) + surrogate model için toplam
5 fazlık bir plan var, sırayla ilerlenir.

**Faz değiştirmeden önce bana sor.** Bir sonraki faza otomatik geçme, onay iste.

## Ana kural: küçük adım, her adımda yerel doğrulama

Detay: `docs/TESTING.md`. Özet: agent **hiçbir zaman** birden fazla katmana dokunan büyük
bir iş parçası üretmez. Her adım tek başına yerelde çalıştırılıp görülebilecek kadar küçük
olmalı (bir endpoint, bir bileşen, bir mesh adımı vb.) ve agent her adımın sonunda "ne
yapıldı / nasıl çalıştırılır / ne görmen lazım" formatını sunup **kullanıcının onayını
bekler** — onay gelmeden bir sonraki adıma geçmez. UI adımları da işlevle birlikte,
o an sunulabilir kalitede tasarlanır, "sonra güzelleştiririz" diye ertelenmez.

## Agent için sabit kurallar

1. **Solver adaptör deseni zorunlu.** Hiçbir iş mantığı (backend API, job queue, db şeması,
   frontend) doğrudan bir solver'a (CalculiX/OpenRadioss/OpenFOAM) bağımlı yazılmayacak.
   Her solver `SolverAdapter` arayüzünü uygular: `build_input(params) -> InputArtifact`,
   `run(artifact) -> job_handle`, `parse_results(job_handle) -> ResultSet`.
   `InputArtifact` tek dosya (CalculiX/OpenRadioss) ya da klasör (OpenFOAM case) olabilir —
   arayüz bunu soyutlar, üst katmanlar farkı bilmez. Aynı desen mesh aracı için de geçerli:
   `MesherAdapter` — bkz. `docs/ARCHITECTURE.md#geometri-ve-mesh`.
2. **Ticari CAE yazılımı yok.** ANSYS, HyperMesh, LS-DYNA bu projede hiçbir yerde
   kullanılmaz/önerilmez — ne kod içinde ne dokümantasyonda. Tamamen açık kaynak yığın.
   Kod hiçbir noktada "kullanıcının makinesinde X kurulu" varsayımı yapmaz. Solver/mesh
   çağrıları sadece backend/worker sürecinde, sunucu tarafında olur. Detay: `docs/LICENSING.md`
   (özellikle OpenRadioss'un AGPL lisansının SaaS kullanımdaki etkisi için).
3. **Kompozit modelleme yeni bir solver DEĞİL.** CalculiX ve OpenRadioss adaptörlerinin
   üzerine, malzeme/kesit tanımı ve post-process katmanında eklenen çapraz bir modül olarak
   ele alınır. Yeni bir `SolverAdapter` yazma, mevcut ikisini genişlet.
4. **Araç mühendise karar vermez, veri gösterir.** Kullanıcı zaten simülasyon mantığını
   bilen bir mühendis — hangi mesh tipini, hangi kalite eşiğini, hangi BC'yi kullanacağını
   kendisi bilir. Agent "akıllı öneri/uyarı" mekanizmaları (örn. "bu ayarı denesen mi",
   "bu geometri için X daha uygun olur") yazmaz — sadece işlemi mümkün kılar ve sonucu
   (sayısal veri, görselleştirme) sunar. Bu, özellikle mesh/BC/solver ayarı gibi mühendislik
   kararı gerektiren her noktada geçerli; belirsizlik varsa otomasyon eklemek yerine
   kullanıcıya sor.
3. **Küçük, izole PR/adım mantığı.** Bir agent görevi tek bir modülü hedeflemeli
   (örn. sadece "keyword parser", sadece "job queue endpoint"). Birden fazla katmana aynı
   anda dokunma — sebebi debug edilebilirlik.
4. **Gizli anahtar / API key asla koda gömülmez.** `.env` + `.env.example` kullan, gerçek
   değerleri commit etme.
5. **Her yeni endpoint/modül için minimum 1 test yaz.** Test yoksa görev tamamlanmış sayılmaz.
6. **Belirsizlik varsa varsayım yapıp ilerle, varsayımı açıkça belirt** — ama mimari/faz
   kararlarında (solver seçimi, DB şeması değişikliği, yeni bağımlılık ekleme) durup sor.

## Teknoloji yığını (sabit — değiştirmeden önce sor)

- Backend: Python, FastAPI
- Geometri import + mesh: Gmsh (Python API, OpenCASCADE tabanlı STEP/IGES import dahil)
- Geometri işleme (midsurface, düşük seviye yüzey sorguları): pythonocc-core
  (yalnızca Gmsh'in yetersiz kaldığı yerlerde — bkz. `docs/ARCHITECTURE.md#geometri-işleme-operasyonları`)
- İş kuyruğu: Celery + Redis (Faz 0'da basit bir `subprocess`/`asyncio` runner da kabul edilir,
  ölçeklenme ihtiyacı çıkınca Celery'ye geçilir)
- Veritabanı: PostgreSQL (SQLAlchemy + Alembic migration)
- Frontend: React + TypeScript, 3B önizleme için three.js (glTF/STL render)
- ML (Faz 2): scikit-learn ile başla, ihtiyaç olursa PyTorch

## Klasör yapısı (hedef)

```
/backend
  /app
    /api          # FastAPI route'ları
    /geometry      # STEP/IGES import, tessellation (web önizleme için glTF/STL üretimi)
    /mesh          # mesh adaptörleri (gmsh.py, snappyhexmesh.py, ...)
    /materials     # malzeme kütüphanesi, atama, S-N eğrisi verisi
    /solvers       # solver adaptörleri (calculix.py, openradioss.py, openfoam.py, ...)
    /composite     # katman/failure kriteri modülü (calculix ve openradioss üzerine katman)
    /preprocess    # girdi dosyası parametrize etme
    /postprocess   # sonuç parse + metrik/grafik üretimi
    /models        # SQLAlchemy modelleri
    /ml            # Faz 2: surrogate model kodu
  /tests
/frontend
  /src
/docs
  ARCHITECTURE.md
  ROADMAP.md
  LICENSING.md
  CODING_STANDARDS.md
```

## Çalışma ortamı ve agent rolleri

Bu proje iki farklı ortamda, iki farklı amaçla geliştiriliyor. Her ortamdaki agent bu
dosyanın tamamını okur, ama kendi bölümüne göre davranır.

### A) claude.ai (GitHub connector) — GELİŞTİRME agent'ı

Kullanıcı gündüz buradan prompt yazıyor. Bu ortamda görev **yeni kod üretmek**tir.

- Yukarıdaki tüm kurallar (mikro-adım, solver adaptör deseni, faz onayı, ticari CAE
  yasağı, test yazma zorunluluğu) burada da tam olarak geçerli.
- Asla `main` branch'e direkt commit atma. Her mikro-adım için ayrı bir branch aç
  (`feature/kısa-açıklama` ya da `fix/kısa-açıklama`) ve PR oluştur.
- PR açıklamasında mutlaka şunlar olsun: ne yapıldı, nasıl yerelde/Codespaces'te
  doğrulanır, hangi test(ler) eklendi.
- Bir PR = bir mikro-adım (`docs/ROADMAP.md`'deki tek bir madde). Birden fazla katmana
  (örn. hem backend hem frontend hem db şeması) aynı anda dokunma — "küçük, izole
  PR/adım" kuralı burada da geçerli.
- PR açtıktan sonra kullanıcıya kısa özet ver: "PR #[numara]: [özet]. Codespaces'te
  test edilmesi gereken: [varsa]." — sonra kullanıcının onayını bekle, sıradaki adıma
  onay gelmeden geçme.
- Emin olmadığın mimari kararlarda (solver seçimi, DB şeması, yeni bağımlılık) kod
  yazmadan önce dur, sor.

### B) GitHub Codespaces + Claude Code — TEST/DEBUG agent'ı

Kullanıcı burada (mola aralarında ya da akşam) bekleyen PR'ları doğruluyor. Bu ortamda
görev **yeni özellik geliştirmek DEĞİL, mevcut PR'ı test edip doğrulamak**tır.

Standart akış:
1. İlgili PR branch'ini checkout et: `git checkout <branch-adı>`
2. Bağımlılıkları kur (backend: `pip install -r requirements.txt`; frontend:
   `npm install`)
3. Testleri çalıştır (`pytest` / `npm test`)
4. Varsa lint/type-check çalıştır
5. PR açıklamasındaki "nasıl doğrulanır" adımlarını manuel de dene (örn. `curl
   localhost:8000/health`, tarayıcıda ekranı kontrol et)

Hata bulursan:
- Küçük/bariz bir hataysa (typo, import eksikliği, basit test hatası) kendin düzelt,
  **aynı branch'e** commit et (yeni branch açma). Commit mesajı: `fix: <kısa açıklama>`
- Hata mimari bir soruna işaret ediyorsa (yol haritasındaki bir kararla çelişiyor,
  solver adaptör desenini bozuyor gibi) düzeltmeden önce durumu özetleyip kullanıcıya
  sor — bu ortamda da mimari kararı agent tek başına vermez.
- Her commit sonrası hangi testlerin geçtiğini/geçmediğini raporla.

Bitirince:
- Tüm testler yeşilse: "PR #<numara> test edildi, merge edilebilir" diye net bir onay
  ver.
- `main` branch'e asla direkt commit/push yapma — merge kararı kullanıcıya ait.
- Yol haritasında olmayan yeni bir özellik/kütüphane ekleme.
- İş bitince Codespace'i durdurmayı unutma (kota tasarrufu) — kullanıcıya hatırlat.
