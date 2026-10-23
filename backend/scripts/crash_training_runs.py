"""Crash eğitim testleri (T1–T30, Belgeler → Eğitim) — belgedeki alt adımları API üzerinden koşar.

Her model bir kez kurulur (`/crash/scenario` setup_only ya da şablon + mesh), her adım bu
tabandan yalnız belgedeki tek değişikliği yapar ve `/crash/solve` (wait) ile çözülür. Koşular
crash_runs'a kaydolur (Karşılaştır'da görünür). Sonuç: `training_runs.json` — kaldığı yerden
devam eder; rapor `crash_training_report.py` ile.

    python scripts/crash_training_runs.py                 # tümü
    python scripts/crash_training_runs.py --model M1      # yalnız Model 1
    python scripts/crash_training_runs.py --only T8a,T8b  # seçili adımlar
    python scripts/crash_training_runs.py --redo T21b     # kayıtlıyı yeniden koş
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

OUT = Path(__file__).resolve().parent.parent / "reports" / "crash_training" / "training_runs.json"

Req = dict[str, Any]
Mutate = Callable[[Req, dict[str, Any]], Req]


@dataclass
class Step:
    key: str  # ör. "T2b"
    test: str  # "T2"
    model: str  # "M1"
    label: str  # belgedeki alt madde
    base: str = ""  # MODELS anahtarı; boş = model tabanı
    mutate: Mutate | None = None
    #: "solve" | "reuse:<key>" (aynı koşu, yeni koşu yok) | "cfc" | "doe" | "dyna" | "compare"
    kind: str = "solve"
    extra: dict[str, Any] = field(default_factory=dict)


# ── Model tabanları ────────────────────────────────────────────────────────
# Senaryo gövdesi (`/crash/scenario`, setup_only) ya da {"template": ...} (şablon + mesh + malzeme).
SLED_100 = [{"name": "kizak", "region": "kutu_arka", "mass_kg": 100.0}]
SLED_50 = [{"name": "kizak", "region": "kutu_arka", "mass_kg": 50.0}]
RAIL_X = [{"name": "kizak_ray", "rigid_body": "kizak", "dofs": "011111"}]

MODELS: dict[str, dict[str, Any]] = {
    "M1": {"title": "Model 1 — Crash box (3 mm) + 100 kg kızak, rijit duvara 10 m/s",
           "scenario": {"template_id": "crash_box_shell", "geometry": {"wall": 3.0}, "element_size_mm": 5.0,
                        "element_scheme": "quad", "material_name": "S235", "speed_m_s": 10.0, "t_end_ms": 20.0,
                        "rigid_bodies": SLED_100, "model": {"law": "plastic"}}},
    "M1_7075": {"title": "Model 1 — 7075-T6 (kütüphane JC seti)",
                "scenario": {"template_id": "crash_box_shell", "geometry": {"wall": 3.0}, "element_size_mm": 5.0,
                             "element_scheme": "quad", "material_name": "7075-T6", "speed_m_s": 10.0,
                             "t_end_ms": 20.0, "rigid_bodies": SLED_100, "model": {"law": "plastic"}}},
    "M2": {"title": "Model 2 — Crash box (2 mm) + raylı kızak 50 kg, 12 m/s, 30 ms",
           "scenario": {"template_id": "crash_box_shell", "geometry": {"wall": 2.0}, "element_size_mm": 5.0,
                        "element_scheme": "quad", "material_name": "S235", "speed_m_s": 12.0, "t_end_ms": 30.0,
                        "rigid_bodies": SLED_50, "boundary_conditions": RAIL_X, "model": {"law": "plastic"}}},
    "M3": {"title": "Model 3 — İki parça: kutu + çarpma plakası (3D solid), duvarsız",
           "template": {"template_id": "crash_box_plate", "params": {}, "element_size": 10.0, "dimension": 3,
                        "element_scheme": "tet", "material_name": "S235", "parts": [0, 1]},
           "solve": {"dimension": 3, "t_end_ms": 3.0, "use_rigid_wall": False, "scenario": "rigid_wall",
                     "barrier": {"speed_m_s": 10.0, "angle_deg": 0.0, "direction": [-1.0, 0.0, 0.0]},
                     "model": {"law": "plastic"},
                     "parts": [{"part_id": 0, "role": "moving"}, {"part_id": 1, "role": "fixed"}]}},
    "M4": {"title": "Model 4 — Plaka delinme (hazır senaryo: rijit küre)",
           "scenario": {"template_id": "plate_ball_shell"}},
    "M6": {"title": "Model 6 — Alüminyum kutu (can) ezme: açılı C-kesit çarpıcı + sabit blok",
           "scenario": {"template_id": "can_crush_shell", "material_name": "6061-T6", "element_size_mm": 3.0,
                        "speed_m_s": 10.0, "t_end_ms": 10.0, "ball_thickness_mm": 1.0, "ball_mass_kg": 5.0}},
    "M6_30": {"title": "Model 6 — çarpıcı açısı 30°",
              "scenario": {"template_id": "can_crush_shell", "material_name": "6061-T6", "element_size_mm": 3.0,
                           "speed_m_s": 10.0, "t_end_ms": 10.0, "ball_thickness_mm": 1.0, "ball_mass_kg": 5.0,
                           "geometry": {"impactor_angle_deg": 30.0}}},
    "M5_blast": {"title": "Patlama yüklü plaka (Friedlander)",
                 "scenario": {"template_id": "blast_plate_shell", "element_size_mm": 10.0, "t_end_ms": 3.0}},
    "M5_door": {"title": "Kapı intrüzyonu (Ø305 silindir sabit hızla itme)",
                "scenario": {"template_id": "door_beam_shell", "element_size_mm": 8.0, "t_end_ms": 120.0,
                             "push_speed_m_s": 1.0}},
    "M5_drop": {"title": "Düşme testi (zemin, yerçekimi)",
                "scenario": {"template_id": "drop_box_shell", "drop_height_mm": 1000.0,
                             "gravity": {"accel_m_s2": -9.81, "direction": "Z"}}},
    "M5_srail": {"title": "S-kiriş eğilmeli çarpma (50 kg kızak)",
                 "scenario": {"template_id": "s_rail_shell", "element_size_mm": 8.0, "speed_m_s": 10.0,
                              "t_end_ms": 20.0, "rigid_bodies": [{"name": "kizak", "region": "arka_halka",
                                                                  "mass_kg": 50.0}]}},
    "M5_bird": {"title": "Kuş / yumuşak cisim çarpması (SPH)",
                "scenario": {"template_id": "blast_plate_shell", "geometry": {"plate_size": 600.0,
                                                                            "plate_thickness": 6.0},
                             "element_size_mm": 15.0, "speed_m_s": 150.0, "t_end_ms": 3.0,
                             "bird_mass_kg": 1.82, "bird_ld": 2.0}},
    "M5_bird_fine": {"title": "Kuş çarpması — SPH aralığı yarıya",
                     "scenario": {"template_id": "blast_plate_shell", "geometry": {"plate_size": 600.0,
                                                                                 "plate_thickness": 6.0},
                                  "element_size_mm": 15.0, "speed_m_s": 150.0, "t_end_ms": 3.0,
                                  "bird_mass_kg": 1.82, "bird_ld": 2.0, "bird_spacing_mm": None}},
    "M5_pole": {"title": "Direk (pole) yan çarpması (uç kütleleri 20 kg)",
                "scenario": {"template_id": "pole_beam_shell", "end_mass_kg": 20.0}},
    "M5_pole_thin": {"title": "Direk yan çarpması — direk Ø150",
                     "scenario": {"template_id": "pole_beam_shell", "end_mass_kg": 20.0,
                                  "pole_diameter_mm": 150.0}},
}


# ── Yardımcı mutasyonlar ──────────────────────────────────────────────────
def m(**model: Any) -> Mutate:
    """Global malzeme kartı alanları (model.*)."""

    def f(r: Req, _res: dict[str, Any]) -> Req:
        r["model"].update(model)
        return r

    return f


def chain(*fs: Mutate) -> Mutate:
    def f(r: Req, res: dict[str, Any]) -> Req:
        for g in fs:
            r = g(r, res)
        return r

    return f


def setv(path: str, value: Any) -> Mutate:
    """Nokta yolu ile alan (ör. "barrier.angle_deg")."""

    def f(r: Req, _res: dict[str, Any]) -> Req:
        cur = r
        *head, last = path.split(".")
        for k in head:
            cur = cur.setdefault(k, {})
        cur[last] = copy.deepcopy(value)
        return r

    return f


def shell(**kw: Any) -> Mutate:
    def f(r: Req, _res: dict[str, Any]) -> Req:
        r["model"].setdefault("shell", {}).update(kw)
        return r

    return f


TYPE7_SELF = [{"type": 7, "master_part": 0, "slave_part": 0}]
TYPE24_SELF = [{"type": 24, "master_part": 0, "slave_part": 0}]
LAW36_CURVE = [{"eps_dot_per_s": 0.0, "points": [[0.0, 235.0], [0.1, 320.0], [0.3, 380.0]]}]
#: Brar 2009 seti; ε̇₀ setin kaynağında yok — kartta 0 kalınca /crash/solve reddeder (422), mühendis
#: girer: burada 1 1/s (raporda belirtilir).
#: m = 1.56 da sette var ama T_melt / T_r yok — m > 0 iken çözücü T_melt > T_r ister (422); sıcaklık
#: terimi kapalı (m = 0) koşulur.
JC_7075 = {"sigma_y_pa": 546e6, "harden_b_mpa": 674.0, "harden_n": 0.72, "jc_c": 0.059,
           "jc_eps_dot0_per_s": 1.0}


def damp_from_peak(r: Req, res: dict[str, Any]) -> Req:
    """T21b: /DAMP başlangıcı = T21a'nın tepe |u| zamanı (koşudan okunur)."""
    t0 = (res.get("T21a") or {}).get("scalars", {}).get("model_disp_peak_t_ms") or 0.0
    r["damping"] = {"alpha_per_s": 0.0, "beta_s": 1e-5, "part_ids": [0], "t_start_ms": round(float(t0), 3)}
    return r


#: Belgede yay kütlesi yok; Radioss /PROP/TYPE4 sıfır kütleyi reddeder (ERROR 229) — test girdisi 0.1 kg
#: (raporda belirtilir).
SPRING_MASS = 0.1


def spring(k: float, c: float) -> Mutate:
    return setv("springs", [{"name": "yay_1", "end_a": {"rigid_body": "kizak"},
                             "end_b": {"point": [-50.0, 25.0, 20.0], "fixed": True},
                             "k_n_per_mm": k, "c_n_s_per_mm": c, "mass_kg": SPRING_MASS}])


def drop_bc(name_prefix: str) -> Mutate:
    """Senaryonun ürettiği kilit kartlarını kaldır (ör. kenar kilidi)."""

    def f(r: Req, _res: dict[str, Any]) -> Req:
        r["boundary_conditions"] = [b for b in r.get("boundary_conditions", [])
                                    if not str(b.get("name", "")).startswith(name_prefix)]
        return r

    return f


def drop_rbody(index: int) -> Mutate:
    def f(r: Req, _res: dict[str, Any]) -> Req:
        rbs = r.get("rigid_bodies", [])
        if index < len(rbs):
            gone = rbs.pop(index)["name"]
            r["boundary_conditions"] = [b for b in r.get("boundary_conditions", []) if b.get("rigid_body") != gone]
        return r

    return f


def part_roles(*roles: str) -> Mutate:
    def f(r: Req, _res: dict[str, Any]) -> Req:
        for p, role in zip(r["parts"], roles):
            p["role"] = role
        return r

    return f


# ── Adım planı (belgedeki alt maddeler) ───────────────────────────────────
def plan() -> list[Step]:
    S = Step
    return [
        # Model 1
        S("T1a", "T1", "M1", "LAW1 elastik → çöz", mutate=m(law="elastic")),
        S("T1b", "T1", "M1", "LAW2 plastik → çöz"),
        S("T2a", "T2", "M1", "b = 0, n = 1 → çöz", mutate=m(harden_b_mpa=0.0, harden_n=1.0)),
        S("T2b", "T2", "M1", "b = 500 MPa, n = 0.5 → çöz", mutate=m(harden_b_mpa=500.0, harden_n=0.5)),
        S("T2c", "T2", "M1", "a = 400e6 Pa → çöz", mutate=m(sigma_y_pa=400e6)),
        S("T3a", "T3", "M1", "Hız 15 m/s, c = 0 → çöz", mutate=setv("barrier.speed_m_s", 15.0)),
        S("T3b", "T3", "M1", "Hız 15 m/s, c = 0.05, ε̇₀ = 1 → çöz",
          mutate=chain(setv("barrier.speed_m_s", 15.0), m(jc_c=0.05, jc_eps_dot0_per_s=1.0))),
        S("T4", "T4", "M1", "T3b + m = 1, T_melt 1800 K, T_r 293 K, ρCp 3.8e6 → çöz",
          mutate=chain(setv("barrier.speed_m_s", 15.0),
                       m(jc_c=0.05, jc_eps_dot0_per_s=1.0, jc_m=1.0, jc_t_melt_k=1800.0, jc_t_r_k=293.0,
                         jc_rho_cp=3.8e6))),
        S("T5", "T5", "M1", "LAW36 eğri 0 235 / 0.1 320 / 0.3 380 → çöz (T2a ile karşılaştır)",
          mutate=m(law="tabulated", tab_curves=LAW36_CURVE)),
        S("T6a", "T6", "M1", "Duvar konumu ön uçtan (Modelden seç: x = 0, kesit merkezi) → çöz",
          mutate=setv("barrier.wall.point", [0.0, 25.0, 20.0])),
        S("T6b", "T6", "M1", "Açı 15° → çöz", mutate=setv("barrier.angle_deg", 15.0)),
        S("T6c", "T6", "M1", "Açı 0, bilerek yanlış yön (−X) → çöz",
          mutate=setv("barrier.wall.normal", [-1.0, 0.0, 0.0])),
        S("T7a", "T7", "M1", "Çıktı ayarları: TH aralığı 0.1 ms → çöz", mutate=setv("engine.th_dt_ms", 0.1)),
        S("T7b", "T7", "M1", "TH aralığı boş (varsayılan) → çöz"),
        S("T7c", "T7", "M1", "Sonuçlar → CFC 60 (post-process, T7b koşusu)", kind="cfc",
          extra={"of": "T7b", "force_cfc": 60}),
        S("T7d", "T7", "M1", "Sonuçlar → CFC 600 (post-process, T7b koşusu)", kind="cfc",
          extra={"of": "T7b", "force_cfc": 600}),
        S("T21a", "T21", "M1", "Süre 40 ms → çöz; Geri sekme kartı", mutate=setv("t_end_ms", 40.0)),
        S("T21b", "T21", "M1", "40 ms + /DAMP α 0, β 1e-5 s, parça #0, başlangıç = tepe zamanı → çöz",
          mutate=chain(setv("t_end_ms", 40.0), damp_from_peak)),
        S("T24a", "T24", "M1", "7075-T6 ata → Kütüphane JC seti (A, B, n, c) + ε̇₀ = 1 1/s elle, m kapalı (T_melt/T_r sette yok) → çöz", base="M1_7075", mutate=m(**JC_7075)),
        S("T24b", "T24", "M1", "Aynı a, b, n, c, ε̇₀ elle → çöz (aynı deck)", base="M1_7075", mutate=m(**JC_7075)),
        S("T24c", "T24", "M1", "Karşılaştırma tabanı: S235 LAW2 (T1b)", kind="reuse:T1b"),
        S("T30a", "T30", "M1", "Ishell 0 (varsayılan) → çöz", mutate=shell(ishell=0)),
        S("T30b", "T30", "M1", "Ishell 24 (QEPH) → çöz", mutate=shell(ishell=24)),
        S("T30c", "T30", "M1", "Ishell 12 (tam entegre) → çöz", mutate=shell(ishell=12)),
        # Model 2
        S("T8a", "T8", "M2", "Temas yok → çöz"),
        S("T8b", "T8", "M2", "TYPE7 #0↔#0 → çöz", mutate=setv("contacts", TYPE7_SELF)),
        S("T8c", "T8", "M2", "TYPE24 #0↔#0 → çöz", mutate=setv("contacts", TYPE24_SELF)),
        S("T9a", "T9", "M2", "TYPE7 + kızak Rayda → çöz", kind="reuse:T8b"),
        S("T9b", "T9", "M2", "TYPE7 + kızak Serbest → çöz",
          mutate=chain(setv("contacts", TYPE7_SELF), setv("boundary_conditions", []))),
        S("T10a", "T10", "M2", "Rayda koşusunda HG/IE (Ishell 0)", kind="reuse:T8b"),
        S("T10b", "T10", "M2", "Uzman → Ishell 24 → çöz",
          mutate=chain(setv("contacts", TYPE7_SELF), shell(ishell=24))),
        S("T19a", "T19", "M2", "TYPE24 kapsam Parça çifti #0↔#0 → çöz", kind="reuse:T8c"),
        S("T19b", "T19", "M2", "TYPE24 kapsam Tüm model → çöz",
          mutate=setv("contacts", [{"type": 24, "all_parts": True}]), extra={"deck_grep": ["/SURF/PART/7901",
                                                                                          "/INTER/TYPE24"]}),
        S("T20a", "T20", "M2", "Ezilme referansı: Kütle / kızak #1 → çöz",
          mutate=chain(setv("contacts", TYPE7_SELF), setv("crush_ref", {"rigid_body": "kizak"}))),
        S("T20b", "T20", "M2", "Referans kaldırıldı → ezilme skalerleri yok", kind="reuse:T8b"),
        S("T22a", "T22", "M2", "Yay kızak ↔ nokta (−50, 25, 20) sabit, K 500 N/mm, C 0, kütle 0.1 kg → çöz",
          mutate=chain(setv("contacts", TYPE7_SELF), spring(500.0, 0.0)),
          extra={"deck_grep": ["/PROP/TYPE4", "/SPRING", "/BCS/41"]}),
        S("T22b", "T22", "M2", "K 5000 → çöz", mutate=chain(setv("contacts", TYPE7_SELF), spring(5000.0, 0.0))),
        S("T22c", "T22", "M2", "K 500, C 20 → çöz", mutate=chain(setv("contacts", TYPE7_SELF), spring(500.0, 20.0))),
        # Model 3
        S("T11a", "T11", "M3", "Kutu Hareketli, plaka Sabit, temas YOK → çöz"),
        S("T11b", "T11", "M3", "Temas TYPE7 kutu → plaka → çöz",
          mutate=setv("contacts", [{"type": 7, "master_part": 1, "slave_part": 0}])),
        S("T11c", "T11", "M3", "Plaka Serbest → çöz",
          mutate=chain(setv("contacts", [{"type": 7, "master_part": 1, "slave_part": 0}]),
                       part_roles("moving", "free"))),
        S("T12", "T12", "M3", "İki parça Serbest; kutu 10 m/s (−1,0,0), plaka 5 m/s (1,0,0) → çöz",
          mutate=chain(setv("contacts", [{"type": 7, "master_part": 1, "slave_part": 0}]),
                       part_roles("free", "free"),
                       setv("initial_velocities", [
                           {"name": "kutu_v", "part_id": 0, "speed_m_s": 10.0, "direction": [-1.0, 0.0, 0.0]},
                           {"name": "plaka_v", "part_id": 1, "speed_m_s": 5.0, "direction": [1.0, 0.0, 0.0]}]))),
        # Model 4
        S("T13a", "T13", "M4", "Kopma kapalı (senaryonun kendisi) → çöz"),
        S("T13b", "T13", "M4", "Çekme gerinimi ε_t1 0.2, ε_f1 0.3 (/FAIL/TENSSTRAIN) → çöz",
          mutate=setv("model.fail", {"tensstrain": {"eps_t1": 0.2, "eps_f1": 0.3}})),
        S("T13c", "T13", "M4", "Çekme gerinimi kapalı; LAW2 EPS_p_max 0.3 → çöz", mutate=m(eps_p_max=0.3)),
        S("T14", "T14", "M4", "Kopma kapalı; #1 (küre) ayrı kart LAW1, #0 (plaka) LAW2 → çöz",
          mutate=lambda r, _res: _part_model(r, 1, {"law": "elastic"})),
        # Model 6
        S("T23a", "T23", "M6", "Senaryo: çarpıcı Rijit gövde, blok Sabit, kutu Serbest, Tüm model temas → çöz"),
        S("T23b", "T23", "M6", "Çarpıcı açısı 15° → 30° (şablon) → çöz", base="M6_30"),
        # Model 5+
        S("T15a", "T15", "M5_blast", "Olduğu gibi (kenar kilidi var) → çöz"),
        S("T15b", "T15", "M5_blast", "Kenar kilidi kartı silindi → çöz", mutate=lambda r, _res: _drop_all_bcs(r)),
        S("T16", "T16", "M5_door", "Senaryoyu koş (silindir sabit 1 m/s itme)"),
        S("T17a", "T17", "M5_drop", "Yerçekimi açık → çöz"),
        S("T17b", "T17", "M5_drop", "Yerçekimi kapalı → çöz", mutate=setv("gravity", None)),
        S("T18", "T18", "M5_srail", "Kirişin ortasından kesit (M, M1, M2) → çöz",
          mutate=lambda r, _res: _mid_section(r), extra={"deck_grep": ["/SECT"]}),
        S("T25", "T25", "M5x", "Karşılaştır: T1b, T2c, T10b — enerji eğrileri + enerji dengesi", kind="compare",
          extra={"runs": ["T1b", "T2c", "T10b"]}),
        S("T26", "T26", "M5x", "Mini DOE: crash_box t 2–4 mm, v 8–15 m/s, 20 nokta → eğit (5-fold) → tahmin",
          kind="doe"),
        S("T27a", "T27", "M5_bird", "Senaryoyu koş (SPH kuş 1.82 kg, 150 m/s)",
          extra={"deck_grep": ["/SPHCEL", "/INTER/TYPE7"]}),
        S("T27b", "T27", "M5_bird", "SPH parçacık aralığı yarıya → çöz", mutate=_half_sph),
        S("T28a", "T28", "M5_pole", "Senaryoyu koş (uç kütleleri 20 kg)"),
        S("T28b", "T28", "M5_pole", "Uç kütle kartlarından biri silindi → çöz", mutate=drop_rbody(1)),
        S("T28c", "T28", "M5_pole", "Direk Ø254 → Ø150 → çöz", base="M5_pole_thin"),
        S("T29a", "T29", "M5x", "Basit .k (kare kutu, *MAT_PIECEWISE_LINEAR_PLASTICITY, *RIGIDWALL_PLANAR, "
          "*INITIAL_VELOCITY_GENERATION, mm–t–s) → içe aktar → çöz", kind="dyna", extra={"mat": "024"}),
        S("T29b", "T29", "M5x", "Aynı .k, belgedeki gibi *MAT_PLASTIC_KINEMATIC → içe aktar (atlanan kart listesi) "
          "→ çöz", kind="dyna", extra={"mat": "003"}),
    ]


def _part_model(r: Req, part_id: int, override: dict[str, Any]) -> Req:
    for p in r["parts"]:
        if p["part_id"] == part_id:
            pm = copy.deepcopy(r["model"])
            pm.update(override)
            p["model"] = pm
    return r


def _drop_all_bcs(r: Req) -> Req:
    r["boundary_conditions"] = []
    return r


def _half_sph(r: Req, _res: dict[str, Any]) -> Req:
    for s in r.get("sph_projectiles", []):
        if s.get("spacing_mm"):
            s["spacing_mm"] = s["spacing_mm"] / 2.0
    return r


def _mid_section(r: Req) -> Req:
    """S-kiriş ortası: büküm ortası x = L1 + R·sin(θ/2) (şablon varsayılanı L1 100, R 150, θ 45°) — yz
    düzlemi, geniş köşeler (kesiti tümüyle keser)."""
    x = round(100.0 + 150.0 * math.sin(math.radians(22.5)), 1)
    r["sections"] = [{"name": "orta_kesit", "origin": [x, -500.0, -500.0], "corner1": [x, 500.0, -500.0],
                      "corner2": [x, -500.0, 500.0], "parts": []}]
    return r


# ── HTTP ──────────────────────────────────────────────────────────────────
class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def get(self, path: str) -> Any:
        with urllib.request.urlopen(self.base + path, timeout=120) as r:
            return json.loads(r.read())

    def post(self, path: str, body: Any, timeout: int = 3600) -> Any:
        rq = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                    headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(rq, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{path}: HTTP {exc.code} {exc.read().decode(errors='replace')[:800]}") from exc

    def post_multipart(self, path: str, files: dict[str, tuple[str, bytes]], fields: dict[str, str]) -> Any:
        bd = "----crashtraining"
        crlf = "\r\n"
        body = b""
        for k, v in fields.items():
            body += f"--{bd}{crlf}Content-Disposition: form-data; name=\"{k}\"{crlf}{crlf}{v}{crlf}".encode()
        for k, (fn, content) in files.items():
            head = (f"--{bd}{crlf}Content-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"{crlf}"
                    f"Content-Type: application/octet-stream{crlf}{crlf}")
            body += head.encode() + content + crlf.encode()
        body += f"--{bd}--{crlf}".encode()
        rq = urllib.request.Request(self.base + path, data=body,
                                    headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
        try:
            with urllib.request.urlopen(rq, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{path}: HTTP {exc.code} {exc.read().decode(errors='replace')[:800]}") from exc


# ── Model kurulumu ────────────────────────────────────────────────────────
def build_base(api: Api, key: str, state: dict[str, Any]) -> Req:
    """Model tabanı: bir kez kurulur (geometri + mesh + malzeme), istek state'te saklanır."""
    bases = state.setdefault("bases", {})
    if key in bases:
        return copy.deepcopy(bases[key]["request"])
    spec = MODELS[key]
    if "scenario" in spec:
        res = api.post("/crash/scenario", {**spec["scenario"], "setup_only": True, "name": spec["title"]})
        req = res["solve_request"]
        info = {"scenario": res.get("scenario"), "mesh": res.get("mesh"), "crash": res.get("crash")}
    else:
        t = spec["template"]
        geo = api.post(f"/templates/{t['template_id']}/create", {"params": t["params"]})
        gid = geo["geometry_id"]
        mesh = api.post(f"/geometry/{gid}/mesh", {"element_size": t["element_size"], "dimension": t["dimension"],
                                                  "element_scheme": t["element_scheme"]})
        mats = api.get("/materials")["materials"]
        mat = next(x for x in mats if x["name"] == t["material_name"])
        for pid in t["parts"]:
            api.post("/materials/assignments", {"geometry_id": gid, "part_id": pid, "material_id": mat["id"]})
        req = {"geometry_id": gid, **copy.deepcopy(spec["solve"])}
        info = {"scenario": {"template_id": t["template_id"], "geometry": geo.get("template_params"),
                             "element_size_mm": t["element_size"], "element_scheme": t["element_scheme"],
                             "material_name": mat["name"], "regions": geo.get("regions")},
                "mesh": {k: v for k, v in mesh.items() if not isinstance(v, (list, dict)) or k in ("parts",)}}
    req.update(run_solver=True, wait=True)
    req.setdefault("model", {}).setdefault("law", "plastic")
    bases[key] = {"title": spec["title"], "request": req, **info}
    return copy.deepcopy(req)


SCALAR_KEYS = None  # tümü saklanır


def run_step(api: Api, step: Step, state: dict[str, Any]) -> dict[str, Any]:
    res = state.setdefault("results", {})
    rec: dict[str, Any] = {"test": step.test, "model": step.model, "label": step.label, "kind": step.kind}
    t0 = time.time()
    if step.kind.startswith("reuse:"):
        src = res[step.kind.split(":", 1)[1]]
        rec.update({k: src.get(k) for k in ("run_id", "job_id", "status", "scalars", "request", "base")})
        rec["reused_from"] = step.kind.split(":", 1)[1]
    elif step.kind == "cfc":
        src = res[step.extra["of"]]
        out = api.get(f"/crash/jobs/{src['job_id']}/cfc?force_cfc={step.extra['force_cfc']}")
        rec.update(run_id=src["run_id"], status="post-process", cfc=out, base=src.get("base"))
    elif step.kind == "compare":
        rec.update(status="compare", runs={k: res[k]["run_id"] for k in step.extra["runs"] if k in res})
    elif step.kind == "doe":
        rec.update(run_doe(api))
    elif step.kind == "dyna":
        rec.update(run_dyna(api, step.extra.get("mat", "024")))
    else:
        base_key = step.base or step.model
        req = build_base(api, base_key, state)
        if step.mutate:
            req = step.mutate(req, res)
        req.pop("_geom", None)
        req["name"] = f"Eğitim {step.key} · {step.label}"[:200]
        out = api.post("/crash/solve", req)
        rec.update(run_id=out.get("run_id"), job_id=out.get("job_id"), status=out.get("status"),
                   message=out.get("message"), scalars=out.get("scalars") or {}, request=req, base=base_key)
        if step.extra.get("deck_grep"):
            rec["deck_cards"] = deck_cards(api, req, step.extra["deck_grep"])
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


def deck_cards(api: Api, req: Req, needles: list[str]) -> dict[str, list[str]]:
    """Deck önizlemesinden aranan kart başlıkları + ardından gelen birkaç satır."""
    try:
        prev = api.post("/crash/deck/preview", {**req, "run_solver": False, "wait": False})
    except Exception as exc:  # noqa: BLE001 — rapor için not
        return {"_error": [str(exc)[:300]]}
    text = prev.get("starter") or prev.get("deck") or prev.get("text") or json.dumps(prev)
    lines = text.splitlines()
    found: dict[str, list[str]] = {}
    for n in needles:
        for i, ln in enumerate(lines):
            if ln.startswith(n):
                found.setdefault(n, []).append("\n".join(lines[i:i + 4]))
                if len(found[n]) >= 3:
                    break
    return found


# ── T26: mini DOE ─────────────────────────────────────────────────────────
def run_doe(api: Api) -> dict[str, Any]:
    """Aynı adlı çalışma varsa ona bağlanır (POST /studies çalışmayı kendisi başlatır)."""
    name = "Eğitim T26 mini DOE"
    studies = api.get("/crash/doe/studies")
    studies = studies.get("studies", studies) if isinstance(studies, dict) else studies
    sid = next((x["id"] for x in studies if x.get("name") == name), None)
    if sid is None:
        spec = {"name": name, "n_samples": 20, "seed": 26,
                "base": {"template_id": "crash_box_shell", "element_size_mm": 5.0, "speed_m_s": 10.0,
                         "t_end_ms": 20.0, "rigid_bodies": SLED_100, "model": {"law": "plastic"}},
                "vary": {"geometry.wall": [2.0, 4.0], "speed_m_s": [8.0, 15.0]}}
        st = api.post("/crash/doe/studies", spec)
        sid = st.get("id") or st.get("study_id")
        if st.get("status") not in ("running", "done", "completed"):
            api.post(f"/crash/doe/studies/{sid}/run", {})
    while True:
        cur = api.get(f"/crash/doe/studies/{sid}")
        if cur.get("status") not in ("running", "pending", "queued"):
            break
        time.sleep(20)
    out: dict[str, Any] = {"status": "doe", "study_id": sid, "study": cur}
    try:
        out["train"] = api.post("/crash/ml/train", {"template_id": "crash_box_shell", "scenario": "rigid_wall",
                                                    "study_id": sid, "n_folds": 5})
        feats = api.get("/crash/ml/models/crash_box_shell/rigid_wall").get("feature_keys") or []
        out["feature_keys"] = feats

        def inputs(t: float, v: float) -> dict[str, float]:
            # değişkenler: cidar t (geom.wall = parts.0.thickness_mm) ve hız
            return {k: (v if "speed" in k else t) for k in feats if "speed" in k or "wall" in k or "thickness" in k}

        for key, t in (("predict_in", 3.0), ("predict_ood", 6.0)):
            out[key + "_inputs"] = inputs(t, 10.0)
            out[key] = api.post("/crash/ml/predict", {"template_id": "crash_box_shell", "scenario": "rigid_wall",
                                                       "inputs": out[key + "_inputs"]})
    except Exception as exc:  # noqa: BLE001 — rapor için not
        out["ml_error"] = str(exc)[:1500]
    return out


# ── T29: .k içe aktarma ───────────────────────────────────────────────────
def run_dyna(api: Api, mat: str = "024") -> dict[str, Any]:
    from scripts.crash_training_kfile import simple_k  # noqa: PLC0415

    imp = api.post_multipart("/crash/import/dyna", {"main": (f"egitim_t29_mat{mat}.k", simple_k(mat).encode())},
                             {"length_to_mm": "1", "mass_to_kg": "1000", "time_to_s": "1"})
    iid = imp.get("import_id") or imp.get("id")
    out: dict[str, Any] = {"import": imp, "import_id": iid, "units": "mm–t–s"}
    try:
        sol = api.post(f"/crash/import/dyna/{iid}/solve", {"name": f"Eğitim T29 · .k içe aktarma (MAT_{mat})",
                                                            "wait": True})
        out.update(status=sol.get("status"), run_id=sol.get("run_id"), job_id=sol.get("job_id"),
                   message=sol.get("message"), scalars=sol.get("scalars") or {})
    except Exception as exc:  # noqa: BLE001
        out.update(status="error", message=str(exc)[:1200])
    return out


# ── Ana döngü ─────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8001")
    ap.add_argument("--model", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--redo", default="")
    a = ap.parse_args()
    api = Api(a.api)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    only = {s for s in a.only.split(",") if s}
    redo = {s for s in a.redo.split(",") if s}
    for step in plan():
        if a.model and step.model != a.model:
            continue
        if only and step.key not in only:
            continue
        if step.key in state.get("results", {}) and step.key not in redo:
            continue
        try:
            rec = run_step(api, step, state)
        except Exception as exc:  # noqa: BLE001 — koşu düşerse raporda görünür
            rec = {"test": step.test, "model": step.model, "label": step.label, "kind": step.kind,
                   "status": "error", "message": str(exc)[:1500]}
        state.setdefault("results", {})[step.key] = rec
        OUT.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
        sc = rec.get("scalars") or {}
        print(f"{step.key:6} #{rec.get('run_id')} {rec.get('status')} {rec.get('wall_s', '')}s "
              f"Fmax={sc.get('rwall_force_max')} IE={sc.get('internal_energy_final')} {rec.get('message') or ''}"[:300],
              flush=True)


if __name__ == "__main__":
    main()
