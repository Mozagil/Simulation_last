# Lisans notları (açık kaynak yığın)

Bu projede ticari CAE (ANSYS, HyperMesh, LS-DYNA) yok. Solver/mesh ikilileri
sunucuda çalışır; kullanıcı makinesinde CAE kurulumu varsayılmaz.

## LS-DYNA keyword içe aktarma

Kullanıcı kararı (2026-10-11): `.k` / `.dyn` keyword dosyası yalnız içe
aktarma için okunur ve OpenRadioss kartlarına çevrilir
(`backend/app/importers/dyna_k.py`). Kurallar:

- LS-DYNA kurulmaz, çağrılmaz, lisansı gerekmez; çeviri saf Python, sunucuda.
  Çözüm yine yalnız OpenRadioss ile yapılır.
- Ters yön yok: keyword dosyası **yazılmaz**.
- Dosya formatı kendi başına telif konusu değil; LS-DYNA kılavuzunun metni ve
  tabloları ise telifli — kodda/dokümanda kopyalanmaz, eşlemeler kendi
  cümlelerimizle yazılır.
- "LS-DYNA" Ansys markası: yalnız tanımlayıcı kullanım ("LS-DYNA .k dosyası
  içe aktarma"); uyumluluk/onay iddiası, logo yok.
- Yüklenen dosyanın hakları kullanıcıya aittir (ürün kullanım şartları konusu).
- OpenRadioss'un kendi .k okuyucusu kullanılmaz.

Bu not hukuki görüş değildir; ticari dağıtımdan önce avukata danışılmalı.

## CalculiX

GPL. Debian/Codespace paketi `calculix-ccx` veya resmi `ccx` ikilisi.
Kaynak: `CCX_PATH` / PATH / `backend/vendor/ccx/` (vendor git'te yok).

## OpenRadioss

AGPL-3.0. Resmi ikililer: https://github.com/OpenRadioss/OpenRadioss/releases
(`OpenRadioss_linux64.zip` / `OpenRadioss_win64.zip`). Lisans sunucusu yok.

SaaS / ağ üzerinden sunum: AGPL, değiştirilmiş sürümü ağ kullanıcılarına
kaynak olarak sunma yükümlülüğü getirebilir. Dağıtmadan önce AGPL metnine bak.

**Durum (2026-10-02): resmi dağıtım sona erdi.** `github.com/OpenRadioss`
kuruluşunda genel depo kalmadı (29 Eyl – 1 Eki 2026 arası), sürüm paketleri 404,
`openradioss.org` Siemens "Simcenter Radioss R&D Program" (shared source,
başvurulu) sayfasına yönleniyor. Bu projede kullanılan kopya: Docker Hub
`dheiny/openradioss-solver:1.0.37` (Ağustos 2026) içindeki `latest-20260728`
ikilileri; imajdaki `COPYRIGHT.md` AGPL v3 bildirimini taşıyor. AGPL ile
dağıtılmış bir kopyanın lisansı geri alınamaz: kullanmak, dağıtmak,
değiştirmek bu lisansın şartlarıyla mümkün kalır. Üretici desteği ve yeni
sürüm yoktur; hata çıkarsa düzeltme bize kalır (kaynak arşivi edinilmeli).
Yükümlülükler aynı: solver ayrı süreç olarak, değiştirilmeden çalıştırılır;
ürün kodu AGPL'ye bulaşmaz. İmajı/ikiliyi birlikte dağıtırsak lisans metni ve
kaynağa erişim yolu kullanıcıya gösterilir.

Kurulum: yerel geliştirme Docker Desktop (WSL2) — `docker build -t
simsurrogate-openradioss:1.0.37 -f backend/docker/openradioss/Dockerfile .`,
`.env`: `OPENRADIOSS_DOCKER_IMAGE`, `OPENRADIOSS_DOCKER_HOME`
(`/opt/OpenRadioss/OpenRadioss`). Yedek: `docker save … | gzip >
vendor/openradioss-1.0.37.tar.gz` (git dışı). Codespace betiği
(`.devcontainer/install_openradioss.sh`) resmi URL'yi çeker, artık çalışmaz;
Codespace'te de imaj ya da yedek tar kullanılmalı. Eski yol (`OPENRADIOSS_PATH`
kök dizin / engine dosyası) yerel ikili varsa hâlâ geçerli.

## Gmsh / OpenFOAM

Gmsh: GPL. OpenFOAM: GPL — OpenRadioss AGPL'inden ayrı.

**OpenFOAM (Faz 2, kullanıcı kararı 2026-10-08): ESI dağıtımı** (openfoam.com,
OpenCFD Ltd.). Resmi Docker imajı `opencfd/openfoam-default:2412` (GPL v3).
Yalnız sunucu tarafında `docker run` ile koşar (`OPENFOAM_DOCKER_IMAGE`);
kullanıcıya OpenFOAM dağıtılmaz, lisans sunucusu yok. GPL, ikiliyi dağıtmadan
sunucuda çalıştırmayı serbest bırakır; imaj değiştirilip dağıtılırsa kaynak
verme yükümlülüğü doğar. "OpenFOAM" OpenCFD Ltd.'nin tescilli markasıdır —
ürün adında kullanılmaz, yalnız "OpenFOAM ile çözülür" şeklinde anılır.

**cfMesh (Faz 2.5b, kullanıcı kararı 2026-10-09):** resmi imajda yok; ESI'nin
topluluk modülü (https://develop.openfoam.com/Community/integration-cfmesh, GPL v3)
`backend/docker/openfoam/Dockerfile` ile resmi imajın üzerine derlenir
(`simsurrogate-openfoam:2412-cfmesh`). İmaj yalnız sunucuda koşar, dağıtılmaz;
dağıtılırsa GPL kaynak verme yükümlülüğü (Dockerfile + modül kaynağı) doğar.
