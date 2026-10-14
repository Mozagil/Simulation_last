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
    """Rijit duvar: sonsuz düzlem (nokta + normal) ya da K3 silindir (/RWALL/CYL:
    eksen üzerindeki nokta + eksen yönü + çap). Silindirde `normal` yalnız ilk
    hız yönü içindir (açı 0 → −normal), duvar geometrisi değil."""

    kind: str = Field(default="plane", description="plane | cyl")
    axis: tuple[float, float, float] = Field(
        (0.0, 0.0, 1.0), description="cyl: silindir ekseni (nokta → nokta + eksen)"
    )
    diameter_mm: float | None = Field(default=None, gt=0, description="cyl: çap (mm)")

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
        if self.kind not in ("plane", "cyl"):
            raise ValueError("wall.kind plane ya da cyl olmalı.")
        if self.kind == "cyl":
            _unit(self.axis, "wall.axis")
            if self.diameter_mm is None:
                raise ValueError("cyl duvar için diameter_mm gerekli.")
            _finite(self.diameter_mm, "diameter_mm")
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
        description="Yalnız `direction` verilmemişse: 0 = duvara dik (-normal), pozitif "
        "(-normal, +X) düzleminde sapma. Duvar yoksa referansı yok — `direction` kullan.",
        json_schema_extra={"unit": "deg"},
    )
    wall: RigidWallParams = Field(default_factory=RigidWallParams)
    #: TODO 11.1 — hız yönü duvardan bağımsız. Verilirse ilk hız bu yönde
    #: (normalize edilir, `angle_deg` yok sayılır); verilmezse eski davranış
    #: (duvar normali + açı) — mevcut koşular ve testler değişmez.
    direction: tuple[float, float, float] | None = Field(
        default=None,
        description="İlk hız yönü (normalize edilir); boş = duvar normalinden",
    )

    @field_validator("speed_m_s", "angle_deg")
    @classmethod
    def _finite_scalar(cls, value: float, info) -> float:
        return _finite(value, info.field_name)

    @field_validator("direction")
    @classmethod
    def _direction_ok(cls, value):
        if value is None:
            return None
        for i, c in enumerate(value):
            _finite(c, f"direction[{i}]")
        _unit(value, "direction")
        return value

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
        if self.direction is not None:
            return _scale(self.speed_m_s, _unit(self.direction, "direction"))
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
        wall: dict = {"point": [px, py, pz], "normal": [nx, ny, nz]}
        if self.wall.kind == "cyl":
            wall.update(kind="cyl", axis=list(_unit(self.wall.axis, "wall.axis")),
                        diameter_mm=float(self.wall.diameter_mm or 0.0))
        return {"vx": vx, "vy": vy, "vz": vz}, wall


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
    # 1.17h — hourglass kontrolü (hm_cfg prop_p1_shell: Hm Hf Hr Dm Dn satırı);
    # 0 = Radioss varsayılanı (hm_cfg: 0.01; aralık 0…0.05). Etkisi Ishell'e bağlı (1–4 hourglass katsayılı
    # formülasyonlar; 12 / 24 farklı stabilizasyon) — seçim mühendisin.
    hm: float = Field(default=0.0, ge=0, le=0.05, description="Hm: düzlem içi (membran) hourglass katsayısı")
    hf: float = Field(default=0.0, ge=0, le=0.05, description="Hf: düzlem dışı (eğilme) hourglass katsayısı")
    hr: float = Field(default=0.0, ge=0, le=0.05, description="Hr: dönme hourglass katsayısı")

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
        for name in ("hm", "hf", "hr"):
            _finite(getattr(self, name), name)
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


def check_curve_rates(curves: list[CrashTabCurve]) -> None:
    rates = [c.eps_dot_per_s for c in curves]
    if any(b <= a for a, b in zip(rates, rates[1:])):
        raise ValueError("LAW36 eğrilerinin hızları kesin artan sırada olmalı.")


def parse_tab_curves(raw: Any) -> list[CrashTabCurve]:
    """Malzeme kütüphanesindeki `crash_curves` JSON'u → doğrulanmış eğriler (1.14c2)."""
    curves = [CrashTabCurve.model_validate(c) for c in (raw or [])]
    check_curve_rates(curves)
    return curves


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
    # 1.17h — solid hourglass katsayısı h (/PROP/TYPE14 "qa qb h" satırı); 0 = varsayılan (hm_cfg: 0.10; aralık 0…0.15)
    solid_hourglass_h: float = Field(default=0.0, ge=0, le=0.15, description="Solid hourglass katsayısı h")
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
        # Eğri yoksa (1.14c2) deck kurulurken parçaya atanmış malzemenin
        # kütüphane eğrileri kullanılır; o da yoksa SolverError → 422.
        if self.law == "tabulated":
            check_curve_rates(self.tab_curves)
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

    1.24a — `all_parts=True`: genel temas (tüm modelin tek yüzeyi, öz temas;
    ≈ LS-DYNA AUTOMATIC_SINGLE_SURFACE). Yalnız TYPE24; master/slave verilmez.
    """

    type: int = Field(default=7, description="7 | 24")
    master_part: int | None = Field(default=None, ge=0)
    slave_part: int | None = Field(default=None, ge=0)
    all_parts: bool = Field(default=False, description="Genel temas: tüm parçalar, öz temas (TYPE24)")
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
    def _parts_ok(self) -> "CrashContactParams":
        if self.all_parts:
            if self.type != 24:
                raise ValueError("genel temas (all_parts) yalnız TYPE24 ile.")
            if self.master_part is not None or self.slave_part is not None:
                raise ValueError("genel temasta master_part / slave_part verilmez.")
        elif self.master_part is None or self.slave_part is None:
            raise ValueError("master_part ve slave_part gerekli (ya da all_parts).")
        return self

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

# 1.15a — engine kontrol kartları. Zaman adımı kartının türü mühendisin
# kararıdır; "" = kart yazılmaz (Radioss eleman zaman adımı, Δt_sca 0.9).
DT_KINDS = ("", "DT", "NODA/0", "NODA/STOP", "NODA/CST/0")


class CrashEngineParams(BaseModel):
    """Engine çıktı aralıkları + zaman adımı kontrolü (hm_cfg: eng_tfile r51,
    eng_anim_dt r51, eng_dt r110, eng_dt_noda r2017). Süreler ms."""

    th_dt_ms: float | None = Field(
        default=None, gt=0, description="/TFILE TH yazma aralığı (ms); boş = t_end/200"
    )
    anim_dt_ms: float | None = Field(
        default=None, gt=0, description="/ANIM/DT aralığı (ms); boş = max(t_end/20, 0.1)"
    )
    dt_kind: str = Field(default="", description="'' | DT | NODA/0 | NODA/STOP | NODA/CST/0")
    dt_scale: float = Field(default=0.0, ge=0, le=1, description="Δt_sca; 0 = Radioss varsayılanı (0.9)")
    dt_min_ms: float = Field(default=0.0, ge=0, description="Δt_min (ms)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashEngineParams":
        for name in ("th_dt_ms", "anim_dt_ms", "dt_scale", "dt_min_ms"):
            v = getattr(self, name)
            if v is not None:
                _finite(v, name)
        if self.dt_kind not in DT_KINDS:
            raise ValueError("dt_kind '', DT, NODA/0, NODA/STOP veya NODA/CST/0 olmalı.")
        if self.dt_kind == "" and (self.dt_scale or self.dt_min_ms):
            raise ValueError("dt_scale / dt_min_ms için dt_kind seçilmeli.")
        # Tutarlılık: CST (kütle ekleme) ve STOP, Δt_min olmadan anlamsız.
        if self.dt_kind in ("NODA/CST/0", "NODA/STOP") and self.dt_min_ms <= 0:
            raise ValueError(f"/DT/{self.dt_kind} için dt_min_ms > 0 olmalı.")
        return self

# 1.15b — /TH seçimi. Değişkenler hm_cfg OUTPUTBLOCK (th_node r110, th_part
# r2025, th_rwall r110, th_inter r110) listelerinden; yalnız tekil değişkenler —
# DEF ve kısa yollar (D, V, A, XYZ, DX_iii …) sütun sayısını belirsiz bıraktığı
# için yok (post-process sütunları deck sırasıyla adlandırır).
TH_VARS: dict[str, tuple[str, ...]] = {
    "node": (
        "DX", "DY", "DZ", "VX", "VY", "VZ", "AX", "AY", "AZ", "VRX", "VRY", "VRZ",
        "ARX", "ARY", "ARZ", "REACX", "REACY", "REACZ", "REACXX", "REACYY", "REACZZ",
        "X", "Y", "Z", "DRX", "DRY", "DRZ",
    ),
    "part": (
        "IE", "KE", "XMOM", "YMOM", "ZMOM", "MASS", "HE", "TURBKE", "XCG", "YCG", "ZCG",
        "XXMOM", "YYMOM", "ZZMOM", "IXX", "IYY", "IZZ", "IXY", "IYZ", "IZX", "RIE",
        "KERB", "RKERB", "RKE", "ERODED", "HEAT", "VX", "VY", "VZ", "PW",
    ),
    # FN / FT (bileşke) ve OFRIC listede var ama bu ikili th_to_csv'de sütun
    # yazmıyor (1.15b koşusu: RWALL FNX FNY FNZ FN → 3 sütun); yalnız bileşenler.
    "rwall": ("FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"),
    "inter": ("FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"),
    # 1.15c — th_sectio r110; bileşenler + moment (sütun yazdığı koşuyla doğrulandı)
    "sect": ("FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ", "MX", "MY", "MZ"),
}


def _th_vars_ok(kind: str, values: list[str]) -> list[str]:
    out = [v.strip().upper() for v in values]
    bad = [v for v in out if v not in TH_VARS[kind]]
    if bad:
        raise ValueError(f"/TH/{kind.upper()} değişkeni geçersiz: {', '.join(bad)}")
    if len(set(out)) != len(out):
        raise ValueError(f"/TH/{kind.upper()} değişkenleri tekrar ediyor.")
    # Radioss sütunları kendi (hm_cfg liste) sırasıyla yazar, istek sırasıyla
    # değil (1.15b koşusu: PART IE KE HE MASS XMOM → IE KE XMOM MASS HE).
    order = TH_VARS[kind]
    return sorted(out, key=order.index)


class CrashThGroup(BaseModel):
    enabled: bool = True
    vars: list[str] = Field(default_factory=list)


class CrashThParams(BaseModel):
    """Zaman geçmişi grupları. Varsayılan = 1.15 öncesi deck (RWALL FN*, INTER
    FN*+FT*, PART IE KE, düğüm yok)."""

    rwall: CrashThGroup = Field(default_factory=lambda: CrashThGroup(vars=["FNX", "FNY", "FNZ"]))
    inter: CrashThGroup = Field(
        default_factory=lambda: CrashThGroup(vars=["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"])
    )
    part: CrashThGroup = Field(default_factory=lambda: CrashThGroup(vars=["IE", "KE"]))
    # Kesitte FN/FT ayrımı Radioss'un kesit normaline bağlı (1.15c: x yönlü
    # eksenel kuvvet FTX'te çıktı); toplam = FN + FT, bu yüzden ikisi de varsayılan.
    sect: CrashThGroup = Field(
        default_factory=lambda: CrashThGroup(vars=["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"])
    )
    node_ids: list[int] = Field(default_factory=list, description="/TH/NODE düğümleri (mesh id)")
    node_vars: list[str] = Field(default_factory=lambda: ["AX", "AY", "AZ"])

    @model_validator(mode="after")
    def _ok(self) -> "CrashThParams":
        for kind in ("rwall", "inter", "part", "sect"):
            g: CrashThGroup = getattr(self, kind)
            g.vars = _th_vars_ok(kind, g.vars)
            if g.enabled and not g.vars:
                raise ValueError(f"/TH/{kind.upper()} açıkken en az bir değişken gerekli.")
        self.node_vars = _th_vars_ok("node", self.node_vars)
        if self.node_ids and not self.node_vars:
            raise ValueError("/TH/NODE düğümleri için en az bir değişken gerekli.")
        if any(n <= 0 for n in self.node_ids) or len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("node_ids pozitif ve tekil olmalı.")
        return self


class CrashSectionParams(BaseModel):
    """/SECT/PARAL (1.15c, hm_cfg radioss110): paralelkenar kesit M, M1, M2
    (mm); seçili parçaların kesitten geçen elemanları. N1–N3 = 0 yazılır (yerel
    eksen yok). FN*/FT* ayrımında Radioss'un kullandığı normal (M1−M)×(M2−M)
    DEĞİL — x = sabit kesitte x kuvveti FTX'te çıktı; global toplam FN + FT.
    Iframe (moment merkezi): 10 global eksen C0, 11 kesit geometrik merkezi,
    12 kesit ağırlık merkezi, 13 (0,0,0)."""

    name: str = Field(default="section", min_length=1, max_length=60)
    origin: tuple[float, float, float]
    corner1: tuple[float, float, float]
    corner2: tuple[float, float, float]
    parts: list[int] = Field(default_factory=list, description="Boş = tüm parçalar")
    iframe: int = Field(default=10)

    @model_validator(mode="after")
    def _ok(self) -> "CrashSectionParams":
        for name in ("origin", "corner1", "corner2"):
            for v in getattr(self, name):
                _finite(v, name)
        if self.iframe not in (10, 11, 12, 13):
            raise ValueError("iframe 10, 11, 12 veya 13 olmalı.")
        a = [c - o for c, o in zip(self.corner1, self.origin)]
        b = [c - o for c, o in zip(self.corner2, self.origin)]
        n = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
        if _norm(n) < 1e-9:
            raise ValueError(f"Kesit '{self.name}': M, M1, M2 doğrusal (alan sıfır).")
        return self


class _NodeSelection(BaseModel):
    """Düğüm seçimi: şablon / kullanıcı bölgesi (PhysicalGroup adı) ya da parça."""

    name: str = Field(default="set", min_length=1, max_length=60)
    region: str | None = Field(default=None, description="Bölge adı (ör. kutu_arka)")
    part_id: int | None = Field(default=None, ge=0, description="Mesh parça numarası")

    @model_validator(mode="after")
    def _one_target(self):
        # K7 — /BCS rijit gövde ana düğümüne de verilebilir (CrashBcParams.rigid_body).
        targets = [t for t in (self.region, self.part_id, getattr(self, "rigid_body", None)) if t is not None]
        if len(targets) != 1:
            raise ValueError(f"'{self.name}': region, part_id (ya da rigid_body) tam olarak biri verilmeli.")
        return self


class CrashInitVelParams(_NodeSelection):
    """/INIVEL/TRA kartı (TODO 11.9): bölge ya da parça düğümlerine ilk hız.

    Kart tabanlı yükleme: `initial_velocities` boş değilse bariyer hızı
    parçalara otomatik verilmez, ilk hız yalnız bu kartlardan gelir. Seçime
    bağlı rijit gövde ana düğümü de aynı hızı alır (ek kütle momentuma girsin).
    """

    speed_m_s: float = Field(..., ge=0, description="Hız büyüklüğü (m/s = mm/ms)")
    direction: tuple[float, float, float] = Field(..., description="Yön (normalize edilir)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashInitVelParams":
        _finite(self.speed_m_s, "speed_m_s")
        for i, c in enumerate(self.direction):
            _finite(c, f"direction[{i}]")
        _unit(self.direction, f"'{self.name}' direction")
        return self

    def velocity_mm_per_ms(self) -> tuple[float, float, float]:
        return _scale(self.speed_m_s, _unit(self.direction, "direction"))


class CrashMassParams(_NodeSelection):
    """/ADMAS (1.17b, hm_cfg radioss110): Iflag 1 = toplam kütle düğümlere
    eşit dağıtılır, 0 = her düğüme bu kütle. kg (kg–mm–ms)."""

    mass_kg: float = Field(..., gt=0)
    distribution: str = Field(default="total", description="total (type 1) | per_node (type 0)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashMassParams":
        _finite(self.mass_kg, "mass_kg")
        if self.distribution not in ("total", "per_node"):
            raise ValueError("distribution total veya per_node olmalı.")
        return self


class CrashRigidBodyParams(_NodeSelection):
    """/RBODY (1.17b, hm_cfg radioss2021): seçili düğümler rijit; ana düğüm
    seçimin ağırlık merkezinde yeni düğüm; `mass_kg` ana düğüme eklenir (ör.
    kızak). Ikrem, ICoG Radioss bayrakları (0 = varsayılan); atalet ek yok."""

    mass_kg: float = Field(default=0.0, ge=0)
    ikrem: int = Field(default=0, description="0: bağımlı düğümler rijit duvardan çıkarılır, 1: çıkarılmaz")
    icog: int = Field(default=0, description="0–4 (hm_cfg); 0 = Radioss varsayılanı (1)")
    # K5 — ana düğüm ivmesi /TH/NODE'a (ilk sırada) yazılır: kafa formu ivmesi,
    # HIC ve CFC (1.17e) bu kanaldan hesaplanır.
    th_accel: bool = Field(default=False, description="Ana düğüm ivmesini TH'ye yaz (HIC kanalı)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashRigidBodyParams":
        _finite(self.mass_kg, "mass_kg")
        if self.ikrem not in (0, 1):
            raise ValueError("ikrem 0 veya 1 olmalı.")
        if self.icog not in (0, 1, 2, 3, 4):
            raise ValueError("icog 0–4 olmalı.")
        return self


class CrashBcParams(_NodeSelection):
    """/BCS (1.17c, hm_cfg radioss51): bölge ya da parça düğümlerinde kilitli
    serbestlikler. `dofs` 6 hane Tx Ty Tz Rx Ry Rz (1 = kilitli)."""

    dofs: str = Field(default="111111", description="Tx Ty Tz Rx Ry Rz, ör. 111000")
    # K7 — rijit gövde ana düğümü (ör. kızağı yalnız x'te yönlendirmek: 011111);
    # bağımlı düğümlere /BCS Radioss'ta kinematik çakışma verir.
    rigid_body: str | None = Field(default=None, description="rigid_bodies[].name — ana düğüm")

    @model_validator(mode="after")
    def _ok(self) -> "CrashBcParams":
        if len(self.dofs) != 6 or any(c not in "01" for c in self.dofs) or "1" not in self.dofs:
            raise ValueError(f"'{self.name}': dofs 6 haneli 0/1 olmalı ve en az bir 1 içermeli.")
        return self


class CrashImpVelParams(BaseModel):
    """/IMPVEL (1.17c, hm_cfg radioss120): sabit zorlanmış hız (m/s = mm/ms).
    Hedef bölge, parça ya da rijit gövde (ana düğümü). t_stop 0 = Radioss
    varsayılanı (sonsuz)."""

    name: str = Field(default="impvel", min_length=1, max_length=60)
    region: str | None = None
    part_id: int | None = Field(default=None, ge=0)
    rigid_body: str | None = Field(default=None, description="rigid_bodies[].name")
    direction: str = Field(default="X", description="X Y Z (öteleme) | XX YY ZZ (dönme)")
    velocity_m_s: float = Field(..., description="İşaretli; dönmede rad/ms")
    t_start_ms: float = Field(default=0.0, ge=0)
    t_stop_ms: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _ok(self) -> "CrashImpVelParams":
        targets = [t for t in (self.region, self.part_id, self.rigid_body) if t is not None]
        if len(targets) != 1:
            raise ValueError(f"'{self.name}': region, part_id ya da rigid_body'den tam olarak biri.")
        if self.direction not in ("X", "Y", "Z", "XX", "YY", "ZZ"):
            raise ValueError("direction X, Y, Z, XX, YY ya da ZZ olmalı.")
        for n in ("velocity_m_s", "t_start_ms", "t_stop_ms"):
            _finite(getattr(self, n), n)
        if self.t_stop_ms and self.t_stop_ms <= self.t_start_ms:
            raise ValueError("t_stop_ms, t_start_ms'den büyük olmalı (0 = sonsuz).")
        return self


class CrashGravityParams(BaseModel):
    """/GRAV (K2, hm_cfg radioss51 LOADS/grav): sabit yerçekimi ivmesi tüm parça
    düğümlerine (+ rijit gövde ana düğümleri). İşaretli büyüklük m/s²; deck
    mm/ms²'ye çevirir (1 m/s² = 1e-3 mm/ms²). Değer / yön mühendisin."""

    accel_m_s2: float = Field(default=-9.81, description="İşaretli ivme (m/s²), ör. −9.81")
    direction: str = Field(default="Z", description="X | Y | Z (global)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashGravityParams":
        _finite(self.accel_m_s2, "accel_m_s2")
        if self.accel_m_s2 == 0:
            # Radioss Fscale_Y = 0'ı varsayılan 1 sayar (1.17c tuzağı) — sıfır yerçekimi = kart yok.
            raise ValueError("accel_m_s2 sıfır olamaz; yerçekimi istenmiyorsa gravity boş bırakılır.")
        if self.direction not in ("X", "Y", "Z"):
            raise ValueError("direction X, Y ya da Z olmalı.")
        return self


class CrashPressureLoadParams(BaseModel):
    """/PLOAD (K10, hm_cfg radioss2021 LOADS/pload): parçanın kabuk yüzeyine
    zamana bağlı basınç, Friedlander pozitif evresi
    p(t) = Ps·(1 − τ)·e^(−b·τ), τ = (t − t0)/td ∈ [0, 1]; dışında 0. Basınç
    kabuk normali boyunca (yön mesh normaline bağlı — işaret mühendisin;
    negatif Ps ters yön). Birim: MPa, ms."""

    name: str = Field(default="pload", min_length=1, max_length=60)
    part_id: int = Field(default=0, ge=0)
    peak_mpa: float = Field(..., description="Ps (MPa), işaretli")
    duration_ms: float = Field(..., gt=0, description="td (ms) pozitif evre süresi")
    decay: float = Field(default=1.0, ge=0, description="b: Friedlander sönüm katsayısı (0 = doğrusal)")
    t_start_ms: float = Field(default=0.0, ge=0, description="t0 (ms)")
    samples: int = Field(default=40, ge=4, le=400, description="/FUNCT nokta sayısı")

    @model_validator(mode="after")
    def _ok(self) -> "CrashPressureLoadParams":
        for n in ("peak_mpa", "duration_ms", "decay", "t_start_ms"):
            _finite(getattr(self, n), n)
        if self.peak_mpa == 0:
            raise ValueError("peak_mpa sıfır olamaz (Radioss Fscale 0'ı 1 sayar).")
        return self

    def pressure_mpa(self, t_ms: float) -> float:
        import math

        tau = (t_ms - self.t_start_ms) / self.duration_ms
        if tau < 0.0 or tau > 1.0:
            return 0.0
        return self.peak_mpa * (1.0 - tau) * math.exp(-self.decay * tau)

    def impulse_per_area_mpa_ms(self) -> float:
        """∫p dt (MPa·ms) — kapalı form: Ps·td·[1/b − (1 − e^(−b))/b²]; b = 0 → Ps·td/2."""
        import math

        b = self.decay
        if b < 1e-9:
            return self.peak_mpa * self.duration_ms / 2.0
        return self.peak_mpa * self.duration_ms * (1.0 / b - (1.0 - math.exp(-b)) / (b * b))


class CrashSphProjectileParams(BaseModel):
    """K12 — SPH mermi (ör. kuş): kapsül (silindir + iki yarım küre) içinde kübik
    kafes parçacıklar; /SPHCEL + /PROP/SPH (hm_cfg r2019) + /MAT/HYDRO (LAW6,
    r2020: P = C1·μ, Pmin kesmesi). Mesh'e girmez, deck'te üretilir. Hedef parça
    yüzeyine TYPE7 (SPH düğümleri slave). Değerler mühendisin; varsayılanlar
    literatürdeki su benzeri kuş modeli mertebesi."""

    name: str = Field(default="kus", min_length=1, max_length=60)
    diameter_mm: float = Field(default=100.0, gt=0)
    length_mm: float = Field(default=200.0, gt=0, description="Toplam boy (≥ çap; = çap → küre)")
    centre: tuple[float, float, float] = Field(default=(0.0, 0.0, 0.0))
    axis: tuple[float, float, float] = Field(default=(0.0, 0.0, 1.0), description="Kapsül ekseni")
    spacing_mm: float = Field(default=10.0, gt=0, description="Parçacık aralığı")
    density_kg_m3: float = Field(default=950.0, gt=0)
    bulk_gpa: float = Field(default=2.2, gt=0, description="C1 hacim modülü (GPa)")
    pmin_gpa: float = Field(default=-1.0e-4, le=0, description="Pmin çekme kesmesi (GPa)")
    velocity_m_s: tuple[float, float, float] = Field(default=(0.0, 0.0, -100.0))
    target_part: int = Field(default=0, ge=0, description="Çarptığı mesh parçası (TYPE7 master)")
    gapmin_mm: float = Field(default=0.0, ge=0, description="TYPE7 GAPmin (0 = Radioss varsayılanı)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashSphProjectileParams":
        if self.length_mm < self.diameter_mm:
            raise ValueError("length_mm, diameter_mm'den küçük olamaz.")
        _unit(self.axis, "sph.axis")
        if self.diameter_mm / self.spacing_mm > 60:
            raise ValueError("spacing_mm çok küçük (çap / aralık ≤ 60).")
        for v in (*self.centre, *self.velocity_m_s):
            _finite(v, "sph")
        return self

    def particles(self) -> list[tuple[float, float, float]]:
        """Kapsül içindeki kübik kafes noktaları (merkezlenmiş)."""
        import math

        ax = _unit(self.axis, "sph.axis")
        r, half = self.diameter_mm / 2.0, (self.length_mm - self.diameter_mm) / 2.0
        ext = self.length_mm / 2.0
        n = int(math.ceil(ext / self.spacing_mm)) + 1
        cx, cy, cz = self.centre
        out = []
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                for k in range(-n, n + 1):
                    x, y, z = i * self.spacing_mm, j * self.spacing_mm, k * self.spacing_mm
                    s = x * ax[0] + y * ax[1] + z * ax[2]  # eksen boyunca
                    s_c = max(-half, min(half, s))
                    dx, dy, dz = x - s_c * ax[0], y - s_c * ax[1], z - s_c * ax[2]
                    if dx * dx + dy * dy + dz * dz <= r * r + 1e-9:
                        out.append((cx + x, cy + y, cz + z))
        return out

    def particle_mass_kg(self) -> float:
        return self.density_kg_m3 * (self.spacing_mm ** 3) * 1e-9


class CrashBlastLoadParams(BaseModel):
    """K13 — /LOAD/PBLAST (hm_cfg radioss2022): ampirik patlama basıncı (TM5-1300,
    Kingery–Bulmash; OpenRadioss hesaplar) parçanın yüzeyine. exp_data 1 serbest
    hava küresel, 2 zemin yansımalı yarım küre (mayın). TNT eşdeğeri kg, mm, ms.
    Değerler / model seçimi mühendisin."""

    name: str = Field(default="mayin", min_length=1, max_length=60)
    part_id: int = Field(default=0, ge=0)
    tnt_kg: float = Field(..., gt=0, description="TNT eşdeğeri kütle (kg)")
    point: tuple[float, float, float] = Field(..., description="Patlama noktası (mm)")
    exp_data: int = Field(default=2, description="1 serbest hava (küresel), 2 zemin yansımalı (yarım küre)")
    t_det_ms: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _ok(self) -> "CrashBlastLoadParams":
        if self.exp_data not in (1, 2):
            raise ValueError("exp_data 1 ya da 2 olmalı.")
        for v in (*self.point, self.tnt_kg, self.t_det_ms):
            _finite(v, "pblast")
        return self


class CrashFilterParams(BaseModel):
    """1.17e — SAE J211 CFC kanal filtresi sınıfları (Hz); None = süzme yok.
    Ham eğriler korunur; süzülmüş olanlar `_cfc<sınıf>` ekiyle eklenir."""

    force_cfc: int | None = Field(default=None, description="Kuvvet kanalları (duvar, temas, kesit)")
    acc_cfc: int | None = Field(default=None, description="İvme kanalları (TH düğüm AX AY AZ, HIC)")

    @model_validator(mode="after")
    def _ok(self) -> "CrashFilterParams":
        for name in ("force_cfc", "acc_cfc"):
            v = getattr(self, name)
            if v is not None and v not in (60, 180, 600, 1000):
                raise ValueError(f"{name} 60, 180, 600 ya da 1000 olmalı.")
        return self
