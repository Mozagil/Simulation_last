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


class CrashModelParams(BaseModel):
    """Solid kart + malzeme kanunu (OpenRadioss TYPE14 / LAW1|LAW2).

    Öneri yok: Isolid/NIP Radioss bayrakları, mühendis doldurur.
    LAW2: a = σy (MPa), b ve n sertleşme; σy verilmezse atanan malzeme yield.
    """

    law: str = Field(default="elastic", description="elastic=LAW1 | plastic=LAW2")
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

    @field_validator("law")
    @classmethod
    def _law_ok(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ("elastic", "plastic"):
            raise ValueError("law elastic veya plastic olmalı.")
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


def apply_barrier(params: dict[str, Any], barrier: CrashBarrierParams) -> dict[str, Any]:
    """`initial_velocity` ve `rigid_wall` alanlarını bariyerden doldurur (yerinde)."""
    vel, wall = barrier.to_inivel_rwall()
    params["initial_velocity"] = vel
    params["rigid_wall"] = wall
    return params
