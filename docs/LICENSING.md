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

Kurulum: Codespace imajı `/opt/openradioss` (`latest-20260728`, kaynak derleme yok).
Yerel Windows: zip'i `backend/vendor/openradioss` altına aç;
`OPENRADIOSS_PATH` kök dizin (resmi değişken) veya engine dosyası.

## Gmsh / OpenFOAM

Gmsh: GPL. OpenFOAM (ileride): GPL — OpenRadioss AGPL'inden ayrı.
