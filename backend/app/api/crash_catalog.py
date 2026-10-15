"""Explicit şablon kataloğu (K0, 2026-10-04) — "durability ile aynı mantık".

Her madde: sektör, problem, durum, geometri şablonu (varsa), referans
(açık literatür / Altair Radioss Example Guide numarası — dosya kopyalanmaz)
ve doğrulama yaklaşımı. Durum:
- ``ready``: `/crash/scenario` ile koşulur (şablon + senaryo kurulumu var)
- ``planned``: altyapısı küçük ek (◐) — sıradaki K adımlarında
- ``major``: büyük yeni kabiliyet (✗, SPH / ALE) — ayrı faz

Senaryo kurulumunun kendisi `crash_scenario.py`'de (şablon başına varsayılan
parça rolü / RBODY / BCS / temas). Kabul kriteri yok; referanslar veri için.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from fastapi import APIRouter


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    sector: str  # otomotiv | savunma | is_makineleri | dogrulama
    title: str
    status: str  # ready | planned | major
    template_id: str | None
    mesh_dim: int | None
    reference: str
    validation: str
    infrastructure: str = ""
    step: str = ""
    #: Arayüz kartı başlangıç değerleri (aynı şablonu paylaşan örnekler için):
    #: geometry (şablon parametreleri), extras (karta özgü alanlar), common
    #: (eleman / v0 / süre), acc_cfc. Değerler mühendisin; yalnız başlangıç.
    defaults: dict = field(default_factory=dict)


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        "crash_box", "otomotiv", "Crash box eksenel ezilme (rijit duvar)", "ready", "crash_box_shell", 2,
        "RD-E 1700 (Radioss örnek kılavuzu)",
        "1.17f V1–V3: elastik dalga ρ·c·v·A, plastik plato σy·A, Wierzbicki–Abramowicz / Abramowicz–Jones",
        step="1.13–1.17",
    ),
    CatalogEntry(
        "s_rail", "otomotiv", "S-kiriş / ön kiriş eğilmeli çarpma", "ready", "s_rail_shell", 2,
        "RD-E 0300 (problem tanımı)",
        "momentum / enerji; ortalama kuvvet / aynı kesitli düz tüp (W&A) oranı (veri)",
        infrastructure="S profil şablonu", step="K7",
        defaults={"extras": {"sled": "50"}, "common": {"speed": "10", "tEnd": "20", "elem": "8"}},
    ),
    CatalogEntry(
        "pole_side", "otomotiv", "Direk (pole) yan çarpması (kiriş + uç kütleleri)", "ready", "pole_beam_shell", 2,
        "açık literatür (yan çarpma, rijit direk Ø254)",
        "momentum; ortalama direk kuvveti vs üç nokta eğilme çökme yükü 4·Mp/L",
        infrastructure="/RWALL/CYL silindirik rijit duvar", step="K3",
    ),
    CatalogEntry(
        "head_impactor", "otomotiv", "Kaput — kafa impaktörü (HIC)", "ready", "plate_ball_shell", 2,
        "açık literatür (yaya koruma yetişkin kafa formu Ø165 / 4.5 kg, 40 km/h)",
        "HIC15 / CFC1000 (1.17e); kafa ivmesi integrali = Δv (impuls / m)",
        infrastructure="rijit küre (1.18) + ivme kanalı", step="K5",
        defaults={
            "geometry": {"plate_size": 600.0, "plate_thickness": 0.8, "ball_diameter": 165.0, "gap": 1.0},
            "extras": {"ballT": "1", "ballMass": "", "ballTotal": "4.5"},
            "common": {"speed": "11.1", "tEnd": "15", "elem": "10"},
            "acc_cfc": 1000,
        },
    ),
    CatalogEntry(
        "drop_test", "otomotiv", "Düşme testi (zemin, yüzey / kenar / köşe)", "ready", "drop_box_shell", 2,
        "RD-E 0600", "v = √(2·g·H), serbest düşme temas anı, momentum / enerji dengesi",
        infrastructure="/GRAV yerçekimi + zemin", step="K2",
    ),
    CatalogEntry(
        "door_intrusion", "otomotiv", "Kapı intrüzyonu (darbe kirişi, Ø305 silindir itme)", "ready",
        "door_beam_shell", 2,
        "FMVSS 214 statik ezme mantığı (Ø305 silindir) — metin kopyalanmaz",
        "kuvvet–intrüzyon eğrisi; plato / ankastre kiriş çökme yükü 8·Mp/L (veri)",
        infrastructure="zorlanmış hız (1.17c) + silindir impaktör", step="K8",
        defaults={"extras": {"push": "1"}, "common": {"tEnd": "120", "elem": "8"}},
    ),
    CatalogEntry(
        "plate_perforation", "savunma", "Plaka delinme / darbe (rijit küre)", "ready", "plate_ball_shell", 2,
        "RD-E 2600; Recht & Ipson (1963)",
        "1.18e V4 elastik yarı-statik (Timoshenko ankastre plaka) + V5 Recht–Ipson tutarlılığı",
        step="1.18",
    ),
    CatalogEntry(
        "taylor_bar", "savunma", "Taylor çubuğu (rijit duvara silindir)", "ready", "taylor_bar", 3,
        "Taylor (1948); Wilkins & Guinan (1973)", "son boy L1/L0 ≈ exp(−ρ·v0²/(2·σ0)); momentum / enerji",
        infrastructure="solid silindir şablonu + 3D senaryo yolu", step="K1",
    ),
    CatalogEntry(
        "hopkinson_bar", "savunma", "Hopkinson çubuğu (çarpıcı → giriş çubuğu)", "ready", "hopkinson_bar", 3,
        "RD-E 0800 (problem tanımı); 1B elastik dalga kuramı",
        "giriş çubuğunda σ = ρ·c·v0/2 ve darbe süresi 2·Ls/c (kesit kuvveti)",
        infrastructure="çok parçalı çubuk + temas", step="K9",
        defaults={"common": {"speed": "10", "tEnd": "0.15", "elem": "4"}},
    ),
    CatalogEntry(
        "blast_plate", "savunma", "Patlama yüklü plaka (Friedlander darbesi)", "ready", "blast_plate_shell", 2,
        "açık literatür (Friedlander basınç darbesi)",
        "uygulanan impuls A·∫p dt = plaka momentumu; dış iş = IE + KE; kalıcı çökme (veri)",
        infrastructure="zamana bağlı basınç yükü (/PLOAD)", step="K10",
        defaults={"common": {"tEnd": "3", "elem": "10"}},
    ),
    CatalogEntry(
        "bird_strike", "savunma", "Kuş / yumuşak cisim çarpması (SPH)", "ready", "blast_plate_shell", 2,
        "RD-E 4900 (problem tanımı); Wilbeck yumuşak cisim kuramı",
        "aktarılan impuls m·v, darbe süresi L/v, kararlı akış kuvveti ρ·A·v² (veri / oran)",
        infrastructure="SPH (K12: /SPHCEL + /PROP/SPH + /MAT/HYDRO)", step="K12",
        defaults={"geometry": {"plate_size": 600.0, "plate_thickness": 6.0},
                  "extras": {"birdKg": "1.82", "ld": "2"}, "common": {"speed": "150", "tEnd": "3", "elem": "15"}},
    ),
    CatalogEntry(
        "underbody_blast", "savunma", "Mayın / araç altı patlama (ampirik PBLAST)", "ready", "blast_plate_shell", 2,
        "TM5-1300 / Kingery–Bulmash (OpenRadioss /LOAD/PBLAST, zemin yansımalı)",
        "Hopkinson–Cranz küp kök ölçekleme (impuls ∝ W, varış ∝ W^1/3); taban çökmesi (veri)",
        infrastructure="/LOAD/PBLAST (K13; tam ALE / yakıt–hava etkileşimi ayrı faz)", step="K13",
        defaults={"geometry": {"plate_size": 1000.0, "plate_thickness": 10.0},
                  "extras": {"tnt": "6", "standoff": "500"}, "common": {"tEnd": "3", "elem": "25"}},
    ),
    CatalogEntry(
        "rops", "is_makineleri", "ROPS — portal çerçeve yanal yavaş itme", "ready", "rops_frame_shell", 2,
        "ISO 3471 (enerji / kuvvet koşulları — mantık, metin kopyalanmaz)",
        "kuvvet–deplasman eğrisi ve emilen enerji (veri); portal sallanma yükü 4·Mp/H",
        infrastructure="çerçeve şablonu + zorlanmış hız", step="K4",
    ),
    CatalogEntry(
        "fops", "is_makineleri", "FOPS — kabin tavanına düşen cisim", "ready", "plate_ball_shell", 2,
        "ISO 3449 (düşme enerjisi — mantık, metin kopyalanmaz)",
        "KE₀ = m·g·H, serbest düşme temas anı; tavan çökmesi / cisim ilerlemesi (veri)",
        infrastructure="rijit cisim düşürme (1.18 + /GRAV)", step="K6",
        defaults={
            "geometry": {"plate_size": 1200.0, "plate_thickness": 6.0, "ball_diameter": 250.0, "gap": 1.0},
            "extras": {"ballT": "2", "ballMass": "", "ballTotal": "227", "height": "5210", "g": "9.81"},
            "common": {"tEnd": "25", "elem": "20"},
        },
    ),
    CatalogEntry(
        "bucket_rock", "is_makineleri", "Kepçe tabanına taş darbesi", "ready", "bucket_rock_shell", 2,
        "açık literatür (iş makinesi kepçe aşınma / darbe)",
        "taş ivmesi ∫|a|dt = I/m (momentum); taban çökmesi / plastik enerji (veri)",
        infrastructure="kepçe şablonu + rijit impaktör", step="K11",
        defaults={"extras": {"ballT": "2", "ballMass": "", "ballTotal": "300"},
                  "common": {"speed": "5", "tEnd": "20", "elem": "20"}},
    ),
    CatalogEntry(
        "can_crush", "dogrulama", "Alüminyum kutu (can) ezme — açılı C-kesit çarpıcı", "ready", "can_crush_shell", 2,
        "Ansys Explicit örneği (problem tanımı, kullanıcı 2026-10-14; dosya kopyalanmadı)",
        "enerji dengesi; deformasyon, eşdeğer plastik şekil değiştirme, geri sekme (1.24c) — veri",
        infrastructure="genel temas (1.24a) + rijit çarpıcı + geri sekme metrikleri", step="1.24d",
        defaults={"extras": {"ballT": "1", "ballMass": "5"},
                  "common": {"speed": "10", "tEnd": "10", "elem": "3"},
                  "material": "6061-T6"},
    ),
)

_BY_ID = {e.id: e for e in CATALOG}
if len(_BY_ID) != len(CATALOG):  # pragma: no cover — import anında
    raise RuntimeError("Katalog id'leri tekrar ediyor.")


def scenario_templates() -> dict[str, int]:
    """`/crash/scenario` ile koşulabilen şablon → mesh boyutu (durum ready)."""
    return {e.template_id: int(e.mesh_dim) for e in CATALOG
            if e.status == "ready" and e.template_id and e.mesh_dim}


router = APIRouter(prefix="/crash", tags=["crash"])


@router.get("/catalog")
def crash_catalog() -> dict:
    return {"entries": [asdict(e) for e in CATALOG], "scenario_templates": scenario_templates()}
