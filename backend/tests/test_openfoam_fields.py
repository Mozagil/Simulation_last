"""Faz 2.6b — OpenFOAM alan dosyası yama değerleri ve yeniden bağlanma noktası."""

from __future__ import annotations

import pytest

from app.postprocess.openfoam_fields import patch_vectors, reattachment_x

FIELD = """FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    object      wallShearStress;
}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform (0 0 0);
boundaryField
{
    inlet
    {
        type            calculated;
        value           uniform (0 0 0);
    }
    lowerWall
    {
        type            calculated;
        value           nonuniform List<vector>
4
(
(-0.6 0 0)
(0.02 0 0)
(0.05 0 0)
(-0.01 0 0)
)
;
    }
}
"""


def test_patch_vectors_nonuniform_and_uniform():
    assert patch_vectors(FIELD, "lowerWall") == [(-0.6, 0, 0), (0.02, 0, 0), (0.05, 0, 0), (-0.01, 0, 0)]
    assert patch_vectors(FIELD, "inlet") == [(0.0, 0.0, 0.0)]
    with pytest.raises(ValueError, match="Yama yok"):
        patch_vectors(FIELD, "upperWall")


def test_reattachment_last_sign_change_interpolated():
    centres = [(-0.01, 0, 0), (0.05, 0, 0), (0.10, 0, 0), (0.15, 0, 0), (0.20, 0, 0)]
    shear = [(-0.6, 0, 0), (0.02, 0, 0), (0.05, 0, 0), (0.01, 0, 0), (-0.03, 0, 0)]
    # aralık 0 < x: (0.15, +0.01) → (0.20, −0.03): 0.15 + 0.05·0.01/0.04 = 0.1625
    assert reattachment_x(centres, shear, 0.0, 0.3) == pytest.approx(0.1625)
    assert reattachment_x(centres[:3], shear[:3], 0.0, 0.3) is None
