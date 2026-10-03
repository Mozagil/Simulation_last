"""Crash bariyer girdi şeması — Faz 1.3 (API/UI yok).

Hız + açı + rigid wall noktası → OpenRadioss `/INIVEL` ve `/RWALL`.
Birim: mm / ms / ton; `speed_m_s` sayısal olarak mm/ms ile aynı (1 m/s = 1 mm/ms).

Açı: 0° = duvara dik yaklaşım (`velocity = -speed * unit(normal)`).
Pozitif açı, hızı `(-normal, u)` düzleminde döndürür; `u` = n'den arındırılmış
dünya +X (n ≈ ±X ise +Y).
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def _finite(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} sonlu bir sayı olmalı.")
    return float(value)


def _norm(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _unit(v: tuple[float, float, float], name: str) -> tuple[float, float, float]:
    n = _norm(v)
    if n < 1e-12:
        raise ValueError(f"{name} sıfır vektör olamaz.")
    return (v[0] / n, v[1] / n, v[2] / n)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(s: float, v: tuple[float, float, float]) -> tuple[float, float, float]:
    return (s * v[0], s * v[1], s * v[2])


def _add(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


class RigidWallParams(BaseModel):
    """Sonsuz düzlem bariyer: düzlem üzerindeki bir nokta + normal."""

    point: tuple[float, float, float] = Field(
        (0.0, 0.0, 0.0),
        description="Düzlem üzerindeki nokta",
        json_schema_extra={"unit": "mm"},
    )
    normal: tuple[float, float, float] = Field(
        (0.0, 0.0, 1.0),
        description="Düzlem normali (yazılırken birimlenir)",
    )

    @field_validator("point", "normal")
    @classmethod
    def _finite_vec(cls, value: tuple[float, float, float], info):
        if len(value) != 3:
            raise ValueError(f"{info.field_name} 3 bileşen olmalı.")
        return tuple(_finite(c, info.field_name) for c in value)

    @model_validator(mode="after")
    def _normal_nonzero(self) -> RigidWallParams:
        _unit(self.normal, "wall.normal")
        return self

    def unit_normal(self) -> tuple[float, float, float]:
        return _unit(self.normal, "wall.normal")


class CrashBarrierParams(BaseModel):
    """Birinci sınıf crash girdi yüzeyi (1.7 endpoint bu modeli kullanır)."""

    speed_m_s: float = Field(
        ...,
        ge=0,
        description="Çarpışma hız büyüklüğü (mm-ms biriminde 1 m/s = 1 mm/ms)",
        json_schema_extra={"unit": "m/s"},
    )
    angle_deg: float = Field(
        0.0,
        description="0 = duvara dik (-normal). Pozitif: (-normal, +X) düzleminde sapma",
        json_schema_extra={"unit": "deg"},
    )
    wall: RigidWallParams = Field(default_factory=RigidWallParams)

    @field_validator("speed_m_s", "angle_deg")
    @classmethod
    def _finite_scalar(cls, value: float, info) -> float:
        return _finite(value, info.field_name)

    def approach_and_sweep(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Birim yaklaşım (açı=0) ve süpürme ekseni (açı artınca)."""
        n = self.wall.unit_normal()
        approach = (-n[0], -n[1], -n[2])
        ref = (1.0, 0.0, 0.0)
        if abs(_dot(n, ref)) > 0.9:
            ref = (0.0, 1.0, 0.0)
        sweep = _sub(ref, _scale(_dot(ref, n), n))
        sweep = _unit(sweep, "angle sweep")
        return approach, sweep

    def velocity_mm_per_ms(self) -> tuple[float, float, float]:
        theta = math.radians(self.angle_deg)
        approach, sweep = self.approach_and_sweep()
        direction = _add(_scale(math.cos(theta), approach), _scale(math.sin(theta), sweep))
        # yuvarlama ile |dir|≈1; hız büyüklüğünü speed ile sabitle
        direction = _unit(direction, "velocity")
        return _scale(self.speed_m_s, direction)

    def to_inivel_rwall(self) -> tuple[dict[str, float], dict[str, list[float]]]:
        vx, vy, vz = self.velocity_mm_per_ms()
        nx, ny, nz = self.wall.unit_normal()
        px, py, pz = self.wall.point
        return (
            {"vx": vx, "vy": vy, "vz": vz},
            {"point": [px, py, pz], "normal": [nx, ny, nz]},
        )


class CrashShellParams(BaseModel):
    """Kabuk kartı (1.13): /PROP/TYPE1 (SHELL), Radioss 2020+ düzeni.

    Öneri yok: bayraklar Radioss değerleri, 0 = /DEF_SHELL varsayılanı.
    Kalınlık parça başına (`parts[].thickness_mm`) ya da burada ortak; kalınlığı
    olmayan kabuk parçası açık hata (sessiz varsayılan yok).
    İzinli değerler: OpenRadioss hm_cfg radioss2020 prop_p1_shell.
    """

    thickness_mm: float | None = Field(
        default=None, gt=0, description="Ortak kabuk kalınlığı t (mm)", json_schema_extra={"unit": "mm"}
    )
    ishell: int = Field(default=0, description="Ishell (formülasyon)")
    ismstr: int = Field(default=0, description="Ismstr (küçük/büyük şekil değiştirme)")
    ish3n: int = Field(default=0, description="Ish3n (üçgen formülasyonu)")
    nip: int = Field(default=0, description="N: kalınlık boyunca integrasyon noktası")

    @model_validator(mode="after")
    def _flags_ok(self) -> "CrashShellParams":
        allowed = {
            "ishell": {0, 1, 2, 3, 4, 12, 24},
            "ismstr": {0, 1, 2, 3, 4, 10},
            "ish3n": {0, 1, 2, 30, 31},
            "nip": {0, 1, 3, 4, 5, 6, 7, 8, 9, 10},
        }
        for name, ok in allowed.items():
            if getattr(self, name) not in ok:
                raise ValueError(f"kabuk {name} {sorted(ok)} olmalı.")
        if self.thickness_mm is not None:
            _finite(self.thickness_mm, "thickness_mm")
        return self


class CrashTabCurve(BaseModel):
    """LAW36 akma eğrisi (1.14c): plastik şekil değiştirme → gerçek gerilme (MPa),
    bir şekil değiştirme hızında. Deck /FUNCT olarak yazar (MPa → GPa)."""

    eps_dot_per_s: float = Field(default=0.0, ge=0, description="Bu eğrinin hızı ε̇ (1/s)", json_schema_extra={"unit": "1/s"})
    points: list[tuple[float, float]] = Field(
        ..., min_length=2, description="[(ε_p, σ MPa), …] — ε_p kesin artan"
    )

    @model_validator(mode="after")
    def _points_ok(self) -> "CrashTabCurve":
        _finite(self.eps_dot_per_s, "eps_dot_per_s")
        xs = [float(x) for x, _ in self.points]
        for x, y in self.points:
            _finite(x, "ε_p")
            _finite(y, "σ")
            if x < 0 or y < 0:
                raise ValueError("eğri noktaları negatif olamaz.")
        if any(b <= a for a, b in zip(xs, xs[1:])):
            raise ValueError("eğride ε_p kesin artan olmalı.")
        return self


class CrashFailJohnson(BaseModel):
    """/FAIL/JOHNSON (1.14d): Johnson-Cook hasar D1…D5; hm_cfg radioss2017 düzeni.
    Hasar 1'e ulaşınca eleman silinir (Ifail_sh / Ifail_so davranışı)."""

    d1: float = 0.0
    d2: float = 0.0
    d3: float = 0.0
    d4: float = 0.0
    d5: float = 0.0
    eps_dot0_per_s: float = Field(default=0.0, ge=0, description="ε̇₀ (1/s)", json_schema_extra={"unit": "1/s"})
    ifail_sh: int = Field(default=0, description="Kabuk silme: 0, 1, 2")
    ifail_so: int = Field(default=0, description="Solid silme: 0, 1, 2")
    dadv: float = Field(default=0.0, ge=0, description="Dadv (çatlak ilerleme ölçütü)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashFailJohnson":
        for name in ("d1", "d2", "d3", "d4", "d5", "eps_dot0_per_s", "dadv"):
            _finite(getattr(self, name), name)
        if self.ifail_sh not in (0, 1, 2) or self.ifail_so not in (0, 1, 2):
            raise ValueError("ifail_sh / ifail_so 0, 1 veya 2 olmalı.")
        if self.d4 != 0 and self.eps_dot0_per_s <= 0:
            raise ValueError("d4 ≠ 0 iken eps_dot0_per_s > 0 olmalı.")
        return self


class CrashFailTensStrain(BaseModel):
    """/FAIL/TENSSTRAIN (1.14d): çekme şekil değiştirmesi; hm_cfg radioss2021 düzeni.
    ε_t1'de hasar başlar, ε_t2'de eleman silinir. S_Flag yalnız ek kart
    gerektirmeyen değerler (0, 1, 11, 21); ölçek fonksiyonu yok."""

    eps_t1: float = Field(default=0.0, ge=0, description="ε_t1: hasar başlangıcı")
    eps_t2: float = Field(default=0.0, ge=0, description="ε_t2: kopma (silme)")
    eps_f1: float = Field(default=0.0, ge=0, description="ε_f1: 1. asal çekme kopma")
    eps_f2: float = Field(default=0.0, ge=0, description="ε_f2: 2. asal çekme kopma")
    s_flag: int = Field(default=0, description="S_Flag: 0, 1, 11, 21")

    @model_validator(mode="after")
    def _ok(self) -> "CrashFailTensStrain":
        for name in ("eps_t1", "eps_t2", "eps_f1", "eps_f2"):
            _finite(getattr(self, name), name)
        if self.s_flag not in (0, 1, 11, 21):
            raise ValueError("s_flag 0, 1, 11 veya 21 olmalı (ek kartlı seçenekler yok).")
        if self.eps_t2 > 0 and self.eps_t2 <= self.eps_t1:
            raise ValueError("eps_t2, eps_t1'den büyük olmalı.")
        if self.eps_t1 == 0 and self.eps_t2 == 0 and self.eps_f1 == 0 and self.eps_f2 == 0:
            raise ValueError("TENSSTRAIN için en az bir şekil değiştirme sınırı gerekli.")
        return self


class CrashFailParams(BaseModel):
    """Parça/malzeme başına kopma kriterleri (ikisi birden olabilir)."""

    johnson: CrashFailJohnson | None = None
    tensstrain: CrashFailTensStrain | None = None


class CrashModelParams(BaseModel):
    """Solid kart + malzeme kanunu (OpenRadioss TYPE14 / LAW1|LAW2).

    Öneri yok: Isolid/NIP Radioss bayrakları, mühendis doldurur.
    LAW2: a = σy (MPa), b ve n sertleşme; σy verilmezse atanan malzeme yield.
    """

    law: str = Field(default="elastic", description="elastic=LAW1 | plastic=LAW2 | tabulated=LAW36")
    isolid: int = Field(default=1, ge=0, le=24, description="TYPE14 Isolid")
    ismstr: int = Field(default=0, ge=0, le=12, description="TYPE14 Ismstr")
    nip: int = Field(default=1, ge=1, le=9, description="TYPE14 Inpts (NIP)")
    sigma_y_pa: float | None = Field(
        default=None,
        ge=0,
        description="LAW2 a (Pa). Boşsa malzeme yield_strength",
        json_schema_extra={"unit": "Pa"},
    )
    harden_b_mpa: float = Field(default=0.0, ge=0, description="LAW2 b (MPa)")
    harden_n: float = Field(default=1.0, ge=0, description="LAW2 n")
    # 1.14a — Johnson-Cook hız / sıcaklık terimleri ve sınırlar (LAW2). Hepsi 0 =
    # terim kapalı / Radioss varsayılanı. Birimler mühendis birimi; deck kg–mm–ms'ye
    # çevirir. Kart düzeni hm_cfg radioss140 matl2_plas_johns (2022 bunu kullanır).
    eps_p_max: float = Field(default=0.0, ge=0, description="EPS_p_max: kopma plastik şekil değiştirmesi")
    sig_max0_mpa: float = Field(default=0.0, ge=0, description="SIG_max0 (MPa): plastik gerilme üst sınırı", json_schema_extra={"unit": "MPa"})
    jc_c: float = Field(default=0.0, ge=0, description="c: şekil değiştirme hızı katsayısı")
    jc_eps_dot0_per_s: float = Field(default=0.0, ge=0, description="ε̇₀ (1/s): referans hız", json_schema_extra={"unit": "1/s"})
    jc_icc: int = Field(default=0, description="ICC: hızın SIG_max'a etkisi (0, 1, 2)")
    jc_fsmooth: int = Field(default=0, description="Fsmooth: hız yumuşatma (0, 1)")
    jc_fcut_hz: float = Field(default=0.0, ge=0, description="F_cut (Hz): hız filtresi kesme frekansı", json_schema_extra={"unit": "Hz"})
    jc_chard: float = Field(default=0.0, ge=0, le=1, description="Chard: boşaltmada sertleşme katsayısı")
    jc_m: float = Field(default=0.0, ge=0, description="m: sıcaklık üssü")
    jc_t_melt_k: float = Field(default=0.0, ge=0, description="T_melt (K)", json_schema_extra={"unit": "K"})
    jc_rho_cp: float = Field(default=0.0, ge=0, description="ρCp (J/(m³·K)): hacimsel özgül ısı", json_schema_extra={"unit": "J/(m³·K)"})
    jc_t_r_k: float = Field(default=0.0, ge=0, description="T_r (K): oda sıcaklığı", json_schema_extra={"unit": "K"})
    # 1.14c — LAW36 (tabulated): eğriler istekte gelir, job.json'a kaydedilir
    # (DB şeması değişmez). eps_p_max, jc_fsmooth, jc_fcut_hz, jc_chard LAW36'da
    # da aynı anlamla kullanılır (EPS_p_max, F_smooth, F_cut, C_hard).
    tab_curves: list[CrashTabCurve] = Field(
        default_factory=list, description="LAW36 akma eğrileri (hız artan sırada)"
    )
    tab_eps_t: float = Field(default=0.0, ge=0, description="LAW36 Eps_t: hasar başlangıç çekme şekil değiştirmesi")
    tab_eps_m: float = Field(default=0.0, ge=0, description="LAW36 Eps_m: maksimum çekme şekil değiştirmesi")
    tab_eps_f: float = Field(default=0.0, ge=0, description="LAW36 Eps_f: eleman silme çekme şekil değiştirmesi")
    tab_vp: int = Field(default=0, description="LAW36 VP: 0 toplam, 1 plastik hız")
    shell: CrashShellParams = Field(
        default_factory=CrashShellParams, description="Kabuk parçalar için /PROP/TYPE1"
    )
    fail: CrashFailParams = Field(
        default_factory=CrashFailParams, description="/FAIL kriterleri (1.14d); boş = kopma yok"
    )

    @field_validator("law")
    @classmethod
    def _law_ok(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ("elastic", "plastic", "tabulated"):
            raise ValueError("law elastic, plastic veya tabulated olmalı.")
        return v

    @field_validator("harden_b_mpa", "harden_n")
    @classmethod
    def _finite_hard(cls, value: float, info) -> float:
        return _finite(value, info.field_name)

    @field_validator("sigma_y_pa")
    @classmethod
    def _finite_sy(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _finite(value, "sigma_y_pa")

    @model_validator(mode="after")
    def _jc_ok(self) -> "CrashModelParams":
        for name in (
            "eps_p_max", "sig_max0_mpa", "jc_c", "jc_eps_dot0_per_s", "jc_fcut_hz",
            "jc_chard", "jc_m", "jc_t_melt_k", "jc_rho_cp", "jc_t_r_k",
        ):
            _finite(getattr(self, name), name)
        for name in ("tab_eps_t", "tab_eps_m", "tab_eps_f"):
            _finite(getattr(self, name), name)
        if self.tab_vp not in (0, 1):
            raise ValueError("tab_vp 0 veya 1 olmalı.")
        if self.law == "tabulated":
            if not self.tab_curves:
                raise ValueError("LAW36 (tabulated) için en az bir akma eğrisi gerekli.")
            rates = [c.eps_dot_per_s for c in self.tab_curves]
            if any(b <= a for a, b in zip(rates, rates[1:])):
                raise ValueError("LAW36 eğrilerinin hızları kesin artan sırada olmalı.")
        if self.jc_icc not in (0, 1, 2):
            raise ValueError("jc_icc 0, 1 veya 2 olmalı.")
        if self.jc_fsmooth not in (0, 1):
            raise ValueError("jc_fsmooth 0 veya 1 olmalı.")
        # Tutarlılık (öneri değil): terim açıksa ihtiyaç duyduğu girdi eksik olamaz.
        if self.jc_c > 0 and self.jc_eps_dot0_per_s <= 0:
            raise ValueError("jc_c > 0 iken referans hız jc_eps_dot0_per_s > 0 olmalı.")
        if self.jc_m > 0 and self.jc_t_melt_k <= self.jc_t_r_k:
            raise ValueError("jc_m > 0 iken jc_t_melt_k, jc_t_r_k'den büyük olmalı.")
        return self


class CrashContactParams(BaseModel):
    """Bir temas tanımı (1.12): /INTER/TYPE7 veya /INTER/TYPE24.

    Parça kimlikleri mesh part_id'si (0 tabanlı). Yüzeyler parçanın solid dış
    derisi (/SURF/PART/EXT). master = slave → self-contact. Öneri yok:
    Istf/Inacti/Iedge Radioss bayrakları, mühendis doldurur.
    TYPE7: slave düğümleri (/GRNOD/PART) → master yüzey; gapmin (mm) kullanılır.
    TYPE24: slave yüzey ↔ master yüzey (simetrik); gapmin yok sayılır.
    """

    type: int = Field(default=7, description="7 | 24")
    master_part: int = Field(ge=0)
    slave_part: int = Field(ge=0)
    fric: float = Field(default=0.0, ge=0, description="Coulomb sürtünme")
    gapmin: float = Field(
        default=0.0, ge=0, description="TYPE7 GAPmin (mm)", json_schema_extra={"unit": "mm"}
    )
    stfac: float = Field(
        default=1.0, gt=0, description="Stfac: ölçek (Istf=1'de rijitlik, kN/mm)"
    )
    istf: int = Field(default=0, description="Istf (rijitlik tanımı)")
    inacti: int = Field(default=0, description="Inacti (ilk penetrasyon)")
    iedge: int = Field(default=0, description="TYPE24 Iedge (kenar–kenar)")

    @field_validator("type")
    @classmethod
    def _type_ok(cls, value: int) -> int:
        if value not in (7, 24):
            raise ValueError("temas tipi 7 veya 24 olmalı.")
        return value

    @model_validator(mode="after")
    def _flags_ok(self) -> "CrashContactParams":
        # İzinli değerler: OpenRadioss hm_cfg radioss2020 TYPE7 / radioss2021 TYPE24.
        if self.type == 7:
            istf_ok, inacti_ok = {0, 1, 2, 3, 4, 5, 1000}, {0, 1, 2, 3, 5, 6, 1000}
        else:
            istf_ok, inacti_ok = {0, 2, 3, 4, 5, 6, 1000}, {-1, 0, 5, 1000}
        if self.istf not in istf_ok:
            raise ValueError(f"TYPE{self.type} Istf {sorted(istf_ok)} olmalı.")
        if self.inacti not in inacti_ok:
            raise ValueError(f"TYPE{self.type} Inacti {sorted(inacti_ok)} olmalı.")
        if self.iedge not in (0, 1, 1000):
            raise ValueError("Iedge 0, 1 veya 1000 olmalı.")
        return self

    @field_validator("fric", "stfac", "gapmin")
    @classmethod
    def _finite_vals(cls, value: float, info) -> float:
        return _finite(value, info.field_name)


def apply_barrier(params: dict[str, Any], barrier: CrashBarrierParams) -> dict[str, Any]:
    """`initial_velocity` ve `rigid_wall` alanlarını bariyerden doldurur (yerinde)."""
    vel, wall = barrier.to_inivel_rwall()
    params["initial_velocity"] = vel
    params["rigid_wall"] = wall
    return params
