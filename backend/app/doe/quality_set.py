"""0.5.5 kalite seti: ~200 ankastre kiriş, kapalı formla tarama.

Her örnek Euler-Bernoulli ile karşılaştırılabilir olsun diye yük hep −y
(uç CLOAD). −z senaryosu bu sette yok — analitik formül o eksende geçersiz.
"""

from __future__ import annotations

from app.doe.sampling import BcScenario, DoeSpec

QUALITY_SET_N = 200
QUALITY_SET_SEED = 2026

#: L/T ≥ 5 şablon kısıtı: min L / max T = 450/12 = 37.5.
_GEOMETRY = {
    "length": (450.0, 700.0),
    "thickness": (8.0, 12.0),
    "width": (35.0, 70.0),
}


def cantilever_quality_spec(material_ids: list[int], *, run_solver: bool = False) -> DoeSpec:
    if not material_ids:
        raise ValueError("material_ids boş olamaz.")
    return DoeSpec(
        name="kalite-200 cantilever",
        template_id="cantilever_beam",
        seed=QUALITY_SET_SEED,
        n_samples=QUALITY_SET_N,
        geometry=_GEOMETRY,
        element_size=(6.0, 14.0),
        load_fy=(-800.0, -200.0),
        material_ids=list(material_ids),
        bc_scenarios=[
            BcScenario(
                name="tip_-y",
                bcs=[
                    {"type": "fixed", "region": "ankastre_uc"},
                    {"type": "cload", "region": "yuk_yuzeyi", "fx": 0.0, "fy": -500.0, "fz": 0.0},
                ],
            )
        ],
        dimension=3,
        element_scheme="tet",
        analysis_type="static",
        run_solver=run_solver,
    )
