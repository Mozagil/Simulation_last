# Kompozit doğrulama (Faz 3.10)

Sonuçlar veridir; kabul ölçütü mühendisindir. Her vaka yeniden üretilebilir
(betik + parametreler aşağıda).

## V-P1 — klasik laminat kabuk plaka: CLT vs CalculiX (2026-10-20)

**Kurulum:** kesit kartları uygulamanın yazıcısından
(`app/composite/section_writer.py` → `*ELASTIC, TYPE=ENGINEERING CONSTANTS`,
`*ORIENTATION`, `*SHELL SECTION, COMPOSITE`). Ağ, BC ve yük betikte düzenli
S8R ızgarası olarak yazılır; Gmsh ve `/composite/solve` zinciri bu vakada yok.
Malzeme tipik T300/epoxy (E1 135, E2 = E3 10, G12 = G13 5.2, G23 3.4 GPa;
ν12 = ν13 0.30, ν23 0.45; seed ile aynı, mill test değil). Katman 0.25 mm,
dört katman, h = 1 mm. CalculiX 2.23 (`vendor/ccx`), doğrusal statik.

Betik: `backend/scripts/composite_validation_vp1.py` → `uploads/reports/composite_validation_vp1.json`.
Test: `backend/tests/test_composite_validation_vp1.py` (ccx yoksa ccx koşuları atlanır).

| Vaka | Dizilim | Geometri / ağ | Yük | BC |
|---|---|---|---|---|
| a | [0/90]s | 200 × 50 mm, 20 × 6 S8R | x = a kenarında Nx = 10 N/mm (tutarlı düğüm yükü) | x = 0: u = 0; (0,0): v = 0; tüm düğümler w = 0 |
| b | [30]₄ | 200 × 50 mm, 20 × 6 S8R | aynı | aynı |
| c | [0/90]s | 200 × 200 mm, 20 × 20 S8R (a/h = 200) | düzgün basınç q = 1e-4 MPa | dört kenar w = 0 (dönmeler serbest); köşede u, v |

Zar vakalarında (a, b) düzgün şekil değiştirme alanı u = εx·x,
v = εy·y + γxy·x bu BC ile tam uyumludur; ölçüm köşe düğümlerinin
deplasmanından: εx = Δu/a, εy = Δv/b, γxy = Δv/a.

**Referanslar** (`backend/app/composite/reference.py`):
- Zar: [ε0; κ] = ABD⁻¹ · [N; M] (ABD: `app/composite/layup.py`).
- Plaka: Navier çift serisi, basit mesnetli özel ortotrop plaka
  (B = 0, D16 = D26 = 0), m, n tek ≤ 99, kayma şekil değiştirmesi yok
  (Reddy, *Mechanics of Laminated Composite Plates and Shells*, §5.2).
  İzotrop kontrol: Timoshenko & Woinowsky-Krieger kare plaka
  w = 0.00406 q a⁴ / D (test).

| Vaka | Büyüklük | CLT | ccx | fark |
|---|---|---|---|---|
| a [0/90]s | εx | 1.3725e-04 | 1.3749e-04 | +0.17 % |
| a [0/90]s | εy | −5.679e-06 | −5.897e-06 | +3.8 % (daha negatif) |
| a [0/90]s | γxy | 0 | 2.7e-08 | εx'in %0.02'si |
| b [30]₄ | εx | 4.5641e-04 | 4.5641e-04 | 0.000 % |
| b [30]₄ | εy | −1.7308e-04 | −1.7308e-04 | −0.001 % |
| b [30]₄ | γxy | −5.7513e-04 | −5.7513e-04 | 0.000 % |
| c [0/90]s | w merkez (mm) | 0.18007 | 0.18042 | +0.19 % |

**Veri notları:**
- **Bulunan hata (3.8 yazıcısı, bu adımda düzeltildi):** COMPOSITE veri
  satırının 4. alanına ply açısı sayı olarak yazılıyordu; ccx bu alanda
  `*ORIENTATION` **adı** bekler ve "nonexistent orientation" ile durur. Yani
  kompozit deste ccx'te hiç koşmuyordu (birim testler ccx çalıştırmadığı için
  görünmedi). Şimdi her farklı ply açısı için ayrı rozet yazılır: ortak
  eksenler (dir0 + yardımcı vektör) ve ek dönme satırı `3, θ` (yerel 3 ekseni
  etrafında). Satır `t, nint, MALZEME, OR_<parça>_<k>` olur.
- **Açı işaret kuralı:** vaka b'de γxy işareti ve büyüklüğü CLT ile aynı
  (Ā16 ≠ 0); ccx ek dönmesi ile CLT'nin θ'sı (laminat x → lif 1, CCW) eşleşiyor.
- **a'daki εy farkı:** ccx kabuğu kalınlık boyunca tek 3B elemana
  (C3D20R) genişletir; katmanlar arası farklı εz (ν13, ν23) bu tek elemanda
  temsil edilemez. Kontrol koşusu: ν13 = ν23 = 0 iken fark %3.8 → %0.9.
  εx ve eğilme sehimi bu etkiden belirgin etkilenmiyor.
- **c'deki +%0.19:** CLT kaymayı ihmal eder, ccx (genişletilmiş katı) içerir;
  a/h = 200'de beklenen mertebede.
- Ölçek: yalnız düz plaka, tek rozet (global X). Eğri kabukta yerel 3 ekseni
  normalden sapar; bu doğrulama onu kapsamaz.
