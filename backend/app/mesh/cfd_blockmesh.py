"""CFD mesh — blockMesh ile parametrik kanal (Faz 2.3).

CFD mesh'i FEA mesh'inden ayrıdır: parçanın değil akışkan hacminin sonlu
hacim ağı. Bu modül en basit hali — dikdörtgen kanal — için OpenFOAM
``blockMeshDict`` metni üretir. STEP geometri (snappyHexMesh / cfMesh) 2.5'te
``mesh/cfd_mesher.py`` altında gelir; burada üretilen kutu orada arka plan
ağı (rüzgâr tüneli) olarak da kullanılacak.

Yamalar: ``inlet`` (x = 0), ``outlet`` (x = L), ``walls`` (y = 0 ve y = H),
``frontAndBack`` (z = 0 ve z = D; 2B'de ``empty``, 3B'de duvar). Birim m.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

INLET, OUTLET, WALLS, FRONT_BACK = "inlet", "outlet", "walls", "frontAndBack"


class ChannelMeshParams(BaseModel):
    length_m: float = Field(gt=0, description="Kanal boyu L (x)")
    height_m: float = Field(gt=0, description="Kanal yüksekliği H (y)")
    #: 2B'de tek hücre kalınlık (değer sonucu etkilemez); 3B'de kanal derinliği.
    depth_m: float | None = Field(None, gt=0, description="Derinlik D (z)")
    nx: int = Field(gt=0, description="x yönünde hücre")
    ny: int = Field(gt=0, description="y yönünde hücre")
    nz: int = Field(1, gt=0, description="z yönünde hücre (2B'de 1)")
    two_d: bool = True
    #: Duvara doğru sıklaşma: kanal ortasındaki hücre / duvardaki hücre oranı
    #: (1 = düzgün). İki yarıya simetrik uygulanır.
    wall_grading: float = Field(1.0, gt=0)

    @model_validator(mode="after")
    def _two_d_ok(self) -> "ChannelMeshParams":
        if self.two_d and self.nz != 1:
            raise ValueError("2B kanalda nz = 1 olmalı.")
        return self

    @property
    def depth(self) -> float:
        if self.depth_m is not None:
            return self.depth_m
        return self.height_m / max(self.ny, 1)

    @property
    def cell_count(self) -> int:
        return self.nx * self.ny * self.nz


def _n(x: float) -> str:
    return f"{x:.6g}"


def channel_block_mesh_dict(p: ChannelMeshParams) -> str:
    L, H, D = p.length_m, p.height_m, p.depth
    verts = [(0, 0, 0), (L, 0, 0), (L, H, 0), (0, H, 0), (0, 0, D), (L, 0, D), (L, H, D), (0, H, D)]
    vtxt = "\n".join(f"    ({_n(x)} {_n(y)} {_n(z)})" for x, y, z in verts)
    if p.wall_grading == 1.0:
        grading = "simpleGrading (1 1 1)"
    else:
        g = _n(p.wall_grading)
        inv = _n(1.0 / p.wall_grading)
        # y: alt yarı duvardan merkeze büyür, üst yarı merkezden duvara küçülür
        grading = f"simpleGrading (1 ((0.5 0.5 {g}) (0.5 0.5 {inv})) 1)"
    fb_type = "empty" if p.two_d else "wall"
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "  SimSurrogate — CFD kanal (blockMesh), otomatik üretildi\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
        "    class       dictionary;\n    object      blockMeshDict;\n}\n\n"
        "convertToMeters 1;\n\n"
        f"vertices\n(\n{vtxt}\n);\n\n"
        f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({p.nx} {p.ny} {p.nz}) {grading}\n);\n\n"
        "edges\n(\n);\n\n"
        "boundary\n(\n"
        f"    {INLET}\n    {{\n        type patch;\n        faces ((0 4 7 3));\n    }}\n"
        f"    {OUTLET}\n    {{\n        type patch;\n        faces ((1 2 6 5));\n    }}\n"
        f"    {WALLS}\n    {{\n        type wall;\n        faces ((0 1 5 4) (3 7 6 2));\n    }}\n"
        f"    {FRONT_BACK}\n    {{\n        type {fb_type};\n        faces ((0 3 2 1) (4 5 6 7));\n    }}\n"
        ");\n\n"
        "mergePatchPairs\n(\n);\n"
    )


def channel_patches(p: ChannelMeshParams, inlet_velocity_m_s: float, outlet_pressure: float = 0.0) -> list[dict]:
    """Case yazıcının (``CfdCaseParams.patches``) beklediği yama listesi."""
    return [
        {"name": INLET, "kind": "inlet", "velocity_m_s": [inlet_velocity_m_s, 0.0, 0.0]},
        {"name": OUTLET, "kind": "outlet", "pressure": outlet_pressure},
        {"name": WALLS, "kind": "wall"},
        {"name": FRONT_BACK, "kind": "empty" if p.two_d else "wall"},
    ]


def poiseuille_reference(p: ChannelMeshParams, mean_velocity_m_s: float, nu_m2_s: float) -> dict[str, float]:
    """Paralel levhalar arası tam gelişmiş laminer akış (2B Poiseuille).

    dp/dx = 12·ν·U/H² (kinematik), u_max = 1.5·U, Re = U·H/ν.
    Girişte düzgün hız verildiği için giriş bölgesinde (L_e ≈ 0.05·Re·H)
    ek basınç kaybı vardır — karşılaştırmada bu bilinmeli (veri olarak).
    """
    U, H, nu = mean_velocity_m_s, p.height_m, nu_m2_s
    grad = 12.0 * nu * U / H**2
    re = U * H / nu
    return {
        "re": re,
        "dpdx_kinematic": grad,
        "dp_kinematic": grad * p.length_m,
        "u_max_m_s": 1.5 * U,
        "entrance_length_m": 0.05 * re * H,
    }
