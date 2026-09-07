"""Skewness / warpage / free-edge — Gmsh'siz birim testler."""

import math

from app.mesh.free_edge import free_edges_from_connectivity
from app.mesh.quality import (
    element_skewness,
    element_warpage,
    quad_skewness,
    quad_warpage_deg,
    triangle_skewness,
)


def test_equilateral_triangle_skewness_is_near_zero():
    h = math.sqrt(3) / 2
    nodes = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, h, 0.0))
    assert triangle_skewness(nodes) < 1e-6


def test_degenerate_triangle_skewness_is_high():
    nodes = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, 0.001, 0.0))
    assert triangle_skewness(nodes) > 0.8


def test_unit_square_quad_skewness_and_warpage_near_zero():
    nodes = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    assert quad_skewness(nodes) < 1e-6
    assert quad_warpage_deg(nodes) < 1e-4


def test_warped_quad_has_nonzero_warpage():
    """Bilerek bir düğümü kaldırma — warpage derece olarak yüksek çıkmalı."""
    nodes = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.4),
        (0.0, 1.0, 0.0),
    )
    assert element_warpage(nodes) > 10.0
    assert element_skewness(nodes) >= 0.0


def test_regular_tet_skewness_below_skewed_sliver():
    good = (
        (1.0, 1.0, 1.0),
        (1.0, -1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
    )
    sliver = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.5, 0.01, 0.0),
        (0.5, 0.0, 0.01),
    )
    assert element_skewness(good) < element_skewness(sliver)
    assert element_warpage(good, solid=True) == 0.0


def test_closed_tri_pair_has_no_free_edge_open_has_three():
    # İki üçgen bir quad'ı kapar — dış çevre 4 kenar serbest
    closed_ish = [[0, 1, 2], [0, 2, 3]]
    assert len(free_edges_from_connectivity(closed_ish)) == 4
    # Tek üçgen: 3 serbest kenar
    assert free_edges_from_connectivity([[0, 1, 2]]) == [(0, 1), (0, 2), (1, 2)]
