# Kompozit ply verisi — açık literatür

> Yalnız doküman. Kütüphaneye (`composite_materials`) giriş ayrı adım. Ticari / lisanslı veri
> (vendor datasheet kopyası, GRANTA, ücretli makale tablosu) yazılmaz. **Araç değer önermez:**
> hangi set, hangi koşulda (sıcaklık, nem, Vf, kür) geçerli — karar mühendisin.

## Doğrulama kuralı

`docs/CRASH_MATERIALS.md` ile aynı: yalnız **birincil kaynağın kendi tablosundan** okunan değer
yazılır; ikincil kaynakta görülen sayı "Doğrulanmadı" tablosuna kaynak iziyle gider. Kaynakta
olmayan alan boş ("—") kalır; enine izotropi gibi bir varsayımla **doldurulmaz** (E3 = E2,
G13 = G12 vb. kaynak açıkça söylemedikçe yazılmaz). Okuma tarihi 2026-10-22; PDF'ler metne
çevrilip tablo satırları okundu.

Birimler: E, G GPa; dayanım MPa; ρ kg/m³; t_ply mm. psi/ksi/Msi → 1 ksi = 6.894757 MPa,
1 Msi = 6.894757 GPa. Değerler oda sıcaklığı, kuru / ortam, ortalama (B-basis değil).
Kütüphane alanlarına eşleme: E1 e1, E2 e2, … , Xt xt, Xc xc (pozitif büyüklük), Yt, Yc, S12.

## Kaynaklar

- **[NASA-IM7]** Maurya, Tanneru, Rajan (ASU), Pereira, Miller (NASA Glenn), *Experimental Tests
  to Characterize the Behavior and Properties of IM7-8552 Composite*, NASA/TM-20230001560
  (Şubat 2023) — Table 1 (nominal ply kalınlığı), Table 6–22 (test sonuçları), Table 31
  (özgül ağırlık). NTRS: `ntrs.nasa.gov/api/citations/20230001560/downloads/TM-20230001560.pdf`.
  ABD kamu eseri.
- **[MIL17]** MIL-HDBK-17-2F Vol. 2, *Polymer Matrix Composites: Materials Properties*,
  17 Haziran 2002 — Distribution Statement A (kamuya açık, sınırsız). Normalize ortalamalar
  (tablodaki Vf ve t_ply'ye); veri sınıfı çoğunlukla "Screening" / "Interim" (az parti).
- **[PURDUE]** C. T. Sun, K. J. Yoon, *Characterization of Elastic-Plastic Properties of
  AS4/APC-2 Thermoplastic Composite*, CML 88-3 (NASA NAG-1-825), 1988, Table 1; C. T. Sun,
  Y. Rui, *Orthotropic Elasto-Plastic Behavior of AS4/APC-2 … in Compression*, CML 89-2, 1989,
  Table 1. NTRS 19880017858, 19900003643.
- **[SNL]** Mandell, Samborsky, Agastra, Sears, Wilson, *Analysis of SNL/MSU/DOE Fatigue Database
  Trends for Wind Turbine Blade Materials*, SAND2010-7052 (Aralık 2010) — Table 6 (s. 60–62),
  malzeme kimliği Table 2(a)/(b). "Approved for public release; unlimited". UNT Digital Library.

## Doğrulanan setler — UD

| # | Malzeme | Kaynak | E1 | E2 | E3 | ν12 | G12 | G13 | G23 | ρ | Xt | Xc | Yt | Yc | S12 | S13 | S23 | Vf % | t_ply |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| U1 | IM7/8552 | NASA-IM7 | 159.3 (ç) / 134.1 (b) | 8.96 (ç) / 9.20 (b) | 7.52 (ç) / 10.07 (b) | 0.3235 | 4.49 | 5.27 | 2.86 | 1610 | 2705 | 805 ‡ | 81.0 | 239.5 | 99.9 † | 103.6 † | 51.1 | — | 0.18 |
| U2 | AS4/3501-6 (bleed) | MIL17 §4.2.12 (a)–(e) | 135.1 (ç) / 122.7 (b) | 10.20 | — | — | — | — | — | 1590 | 2006 | 1448 | 53.6 | — | — | — | — | 60 | 0.135 |
| U3 | IM6/APC-2 (karbon/PEEK) | MIL17 §4.9.1 (a)–(h) | 148.9 (ç) / 133.8 (b) | 8.83 | — | 0.342 | 5.38 | — | — | 1550 | 2413 | 1151 | 64.9 | — | 164.8 | — | — | 60 | 0.137 |
| U4 | AS4/APC-2 (karbon/PEEK) | PURDUE | 127.7 (ç) / 130.8 (b) | 10.27 (ç) / 10.7 (b) | — | 0.32 | — | — | — | — | 2132 | 1234 | 95.1 | 176 | 82.0–84.7 * | — | — | — | — |
| U5 | S2-449/SP381 (S2-cam/epoksi) | MIL17 §6.2.1 (a)–(f) | 47.6 | 13.3 | — | — | 4.75 | — | — | 1850 | 1696 | 1158 | 62.1 | — | 98.6 | — | — | 50 | 0.229 |
| U6 | E-cam UD prepreg NCT307-D1-E300 | SNL Table 6 | 35.5 | 8.33 | — | 0.33 | 4.12 | — | — | — | 1005 | 788 | 51.2 | 168 | 112 | — | — | 47 | — |
| U7 | Karbon UD prepreg NCT307-D1-34-600 (Grafil 34-600, standart modül) | SNL Table 6 | 123 | 8.20 | — | 0.31 | 4.71 | — | — | — | 1979 | 1000 | 59.9 | 223 | 103 | — | — | 53 | — |
| U8 | E-cam dikişli UD (Vectorply E-LT-5500) / SP Prime 20LV, VARTM | SNL Table 6 | 41.8 | 14.0 | — | 0.28 | 2.63 | — | — | — | 1151 | 740 | 59.0 | 202 | 30 § | — | — | 54 | — |

Kalınlık yönü kayma tamamlayıcıları (yalnız G13/G23/S13/S23 — tam set değil):

| Malzeme | Kaynak | G13 | G23 | S13 | S23 | ρ | Vf % | t_ply |
|---|---|---|---|---|---|---|---|---|
| T800HB/3900-2 UD | MIL17 §4.2.34 (b)–(c) | 3.30 | 2.19 | 88.3 | 42.1 | 1550 | 55.5 | 0.191 |
| T700S/3900-2 düz dokuma | MIL17 §4.2.33 (b)–(c) | 2.88 | 2.76 | 71.7 | 71.0 | 1530 | 54 | 0.201 |

## Doğrulanan setler — dokuma (1 = çözgü, 2 = atkı)

| # | Malzeme | Kaynak | E1 | E2 | ν12 | G12 | ρ | Xt | Xc | Yt | Yc | S12 | Vf % | t_ply |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W1 | T300 3k/934 düz dokuma | MIL17 §4.2.6 (a)–(g) | 62.7 (ç) / 57.9 (b) | 62.1 (ç) / 57.2 (b) | — | — | 1550 | 627 | 655 | 607 | 621 | — | 57 | 0.196 |
| W2 | E-cam 7781/EA9396 8-harness saten | MIL17 §6.2.4 (a)–(g) | 23.4 | 23.5 | 0.115 | 5.23 | 1910 | 333 | 320 | 348 | 260 | 79.3 | 54 (normalize 50) | 0.216 |
| W3 | E-cam 7781 prepreg NB307-D1-7781-497A, 0/90 | SNL Table 6 | 19.2 | 19.2 | 0.13 | 3.95 | — | 337 | 497 | 337 | 497 | 115 | 39 | — |

## Notlar (veri)

- (ç) çekme, (b) basma modülü — kaynak ikisini ayrı verir; kütüphanenin tek E alanı için hangisinin
  kullanılacağı mühendisin kararı (seed adımında kaynak alanında hangisi olduğu yazılır).
- ‡ **U1 Xc = 805 MPa dayanım olarak kullanılamaz:** rapor numunelerin uç ezilmesi + boyuna matris
  yarılmasıyla kırıldığını yazar (ASTM D6641'e göre kabul edilmeyen kırılma).
- † **U1 S12, S13 gerçek dayanım değil:** V-çentik testinin %5 mühendislik birim şekil değiştirme
  kesmesindeki gerilme.
- U1: rapor ν21 = 0.0208, ν31 = 0.026 verir; ν13 ve ν23 yazmaz (hesaplanmadı). Zt = 54.1, Zc = 244.5 MPa.
  ρ özgül ağırlık 1.61'den.
- \* **U4 S12 türetilmiş:** eksen dışı testlerden Tsai-Hill / tek parametreli ölçütle geri hesap
  (çekme raporu 82.0, basma raporu 84.7). Basma tablosunda 90° Poisson sütunu metin çıkarımında
  kaymış — kullanılmadı.
- § **U8 S12 = 30 MPa** ±45 testinden (ASTM D3518), kaynakta yazdığı gibi; kumaşta %6 90° iplik var.
- MIL17 S2-449/SP381 tanımı kendi içinde çelişkili (17k / 43.5k tow; 111 / 284 g/m²).
- Kütüphanede şu an olan `T300/epoxy` ve `E-glass/epoxy` seed'leri "tipik el kitabı aralığı"
  olarak girildi, bu belgedeki kurala göre birincil kaynaklı değil.

## Doğrulanmadı — sayı yazılmadı

| Malzeme | Durum | Bakılacak birincil kaynak (iz) |
|---|---|---|
| T300/BSL914C, AS4/3501-6, E-cam/LY556, E-cam/MY750 (WWFE-I) | Açık kopya yok (Elsevier) | Soden, Hinton, Kaddour, Compos. Sci. Technol. 58 (1998) 1011–1022, Table 1 |
| IM7/8552, S2-cam/epoksi vb. (WWFE-II) | Ücretli (SAGE) | Kaddour & Hinton, J. Compos. Mater. 46 (2012) 2295–2312 |
| IM7/8552 (NCAMP) | Kamuya açık ama site bot korumasıyla indirilemedi; elle indirilebilir | NCAMP CAM-RP-2009-015 Rev A, NCP-RP-2009-028 Rev B (Wichita State) |
| AS4/3502 | İkincil (LaRC03 raporu) | Shuart, AIAA J. 27(9) (1989) |
| Kevlar 49/epoksi | DTIC erişilemedi (403) | RARDE 11/83 (DTIC ADA136614); DTIC ADA281587 |
| Aramid (MIL17 Bölüm 5) | Kontrol edildi, veri yok | — |
| PVC köpük çekirdek (Divinycell H sınıfı) | Yalnız vendor datasheet (lisans) | Açık birincil aday: Experimental Mechanics (2012) doi:10.1007/s11340-012-9703-4 — açık erişim doğrulanmadı |
| Nomex / alüminyum bal peteği | Yalnız vendor datasheet (Hexcel HexWeb) | Açık birincil kaynak bulunamadı |
