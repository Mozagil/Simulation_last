# Lisans notları (açık kaynak yığın)

Bu projede ticari CAE (ANSYS, HyperMesh, LS-DYNA) yok. Solver/mesh ikilileri
sunucuda çalışır; kullanıcı makinesinde CAE kurulumu varsayılmaz.

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

Gmsh: GPL. OpenFOAM (ileride): GPL — OpenRadioss AGPL'inden ayrı.
