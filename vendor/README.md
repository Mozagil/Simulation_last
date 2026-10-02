# vendor/ — depoda tutulan üçüncü parti ikililer

## openradioss-latest-20260728-linux64-agpl.tar.gz

OpenRadioss'un son açık sürümü (`latest-20260728`, Linux x86_64, GNU/gfortran
derlemesi). İçerik: `OpenRadioss/exec/` (starter, engine, SP/OMPI varyantları,
`th_to_csv`, `anim_to_vtk`), `hm_cfg_files/` (kart tanımları), `extlib/`
(hm_reader, h3d), `licenses/`, `COPYRIGHT.md` (GNU AGPL v3 bildirimi, Altair
1986-2026).

| | |
|---|---|
| Boyut | 77 499 950 bayt (açılınca 219 MB) |
| SHA-256 | `5ed4cad8e544a981f1b24f1b4e720570fdc4812051f259eebada4bd29f7cb3ce` |
| Alındığı yer | Docker Hub `dheiny/openradioss-solver:1.0.37` (Ağustos 2026) içindeki `/opt/OpenRadioss/OpenRadioss` |
| Tarih | 2026-10-02 |

**Neden depoda:** 29 Eyl – 1 Eki 2026 arasında OpenRadioss'un GitHub deposu ve
sürüm paketleri yayından kalktı; Siemens projeyi kapalı "Simcenter Radioss R&D
Program"a taşıdı. Bu arşiv, AGPL v3 ile dağıtılmış son kopya; lisans geri
alınamaz, kullanım ve dağıtım bu şartlarla serbest (`docs/LICENSING.md`).
Üretici desteği ve yeni sürüm yok.

**Kullanım:** `backend/docker/openradioss/Dockerfile` imajı bu arşivden kurar:

```bash
docker build -t simsurrogate-openradioss:1.0.37 -f backend/docker/openradioss/Dockerfile .
```

Yerel ikili istersen (Linux/WSL): `tar -xzf … -C /opt/` ve
`OPENRADIOSS_PATH=/opt/OpenRadioss/OpenRadioss`.

Doğrulama: `sha256sum vendor/openradioss-latest-20260728-linux64-agpl.tar.gz`.
