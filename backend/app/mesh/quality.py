"""Eleman kalite metrikleri — skewness (eşaçısal) ve warpage.

Gmsh native Jacobian / kenar oranı `gmsh_adapter.compute_mesh_quality` içinde
kalır. Bu modül düğüm koordinatlarından sektör metriklerini üretir
(ARCHITECTURE.md#mesh-kalite-kriterleri).
"""

from __future__ import annotations

import math
from typing import Sequence

Vec3 = tuple[float, float, float]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _angle_deg(vertex: Vec3, p_prev: Vec3, p_next: Vec3) -> float:
    ba = _sub(p_prev, vertex)
    bc = _sub(p_next, vertex)
    na, nb = _norm(ba), _norm(bc)
    if na < 1e-30 or nb < 1e-30:
        return 0.0
    c = max(-1.0, min(1.0, _dot(ba, bc) / (na * nb)))
    return math.degrees(math.acos(c))


def triangle_skewness(nodes: Sequence[Vec3]) -> float:
    """Eşaçısal skewness: 0 mükemmel (60°), 1 dejenere. Referans 60°."""
    if len(nodes) < 3:
        return 0.0
    a, b, c = nodes[0], nodes[1], nodes[2]
    angles = (
        _angle_deg(a, c, b),
        _angle_deg(b, a, c),
        _angle_deg(c, b, a),
    )
    return max(abs(ang - 60.0) / 60.0 for ang in angles)


def quad_skewness(nodes: Sequence[Vec3]) -> float:
    """Eşaçısal skewness: referans 90°. 0 mükemmel, 1 dejenere."""
    if len(nodes) < 4:
        return triangle_skewness(nodes)
    corners = (
        (nodes[0], nodes[3], nodes[1]),
        (nodes[1], nodes[0], nodes[2]),
        (nodes[2], nodes[1], nodes[3]),
        (nodes[3], nodes[2], nodes[0]),
    )
    return max(abs(_angle_deg(v, p, n) - 90.0) / 90.0 for v, p, n in corners)


def quad_warpage_deg(nodes: Sequence[Vec3]) -> float:
    """Quad yüzünün iki üçgen yarısının normal açı farkı (derece). 0 = düzlemsel."""
    if len(nodes) < 4:
        return 0.0
    p0, p1, p2, p3 = nodes[0], nodes[1], nodes[2], nodes[3]

    def _split_angle(a: Vec3, b: Vec3, c: Vec3, d: Vec3) -> float:
        n1 = _cross(_sub(b, a), _sub(c, a))
        n2 = _cross(_sub(c, a), _sub(d, a))
        na, nb = _norm(n1), _norm(n2)
        if na < 1e-30 or nb < 1e-30:
            return 0.0
        cos = max(-1.0, min(1.0, _dot(n1, n2) / (na * nb)))
        return math.degrees(math.acos(cos))

    return max(_split_angle(p0, p1, p2, p3), _split_angle(p1, p2, p3, p0))


def element_skewness(nodes: Sequence[Vec3]) -> float:
    n = len(nodes)
    if n == 3:
        return triangle_skewness(nodes)
    if n == 4:
        # Quad kabuk veya tet: tet'te dört düğüm uzayda, dört yüz üçgeni.
        # Warpage tet için 0; skewness yüzlerin max'ı. Düzlemsel quad'ta
        # dört düğüm neredeyse koplanar — tet ayrımı: hacim.
        vol = abs(_dot(_sub(nodes[3], nodes[0]), _cross(_sub(nodes[1], nodes[0]), _sub(nodes[2], nodes[0]))))
        if vol > 1e-12:
            faces = (
                (nodes[0], nodes[1], nodes[2]),
                (nodes[0], nodes[1], nodes[3]),
                (nodes[0], nodes[2], nodes[3]),
                (nodes[1], nodes[2], nodes[3]),
            )
            return max(triangle_skewness(f) for f in faces)
        return quad_skewness(nodes)
    if n == 8:
        faces = (
            (nodes[0], nodes[1], nodes[2], nodes[3]),
            (nodes[4], nodes[5], nodes[6], nodes[7]),
            (nodes[0], nodes[1], nodes[5], nodes[4]),
            (nodes[1], nodes[2], nodes[6], nodes[5]),
            (nodes[2], nodes[3], nodes[7], nodes[6]),
            (nodes[3], nodes[0], nodes[4], nodes[7]),
        )
        return max(quad_skewness(f) for f in faces)
    return 0.0


def element_warpage(nodes: Sequence[Vec3], *, solid: bool = False) -> float:
    """Warpage (derece). Tet/tri: 0. Quad/hex yüzleri: iki üçgen normal farkı."""
    if solid:
        return 0.0
    n = len(nodes)
    if n == 4:
        return quad_warpage_deg(nodes)
    if n == 8:
        faces = (
            (nodes[0], nodes[1], nodes[2], nodes[3]),
            (nodes[4], nodes[5], nodes[6], nodes[7]),
            (nodes[0], nodes[1], nodes[5], nodes[4]),
            (nodes[1], nodes[2], nodes[6], nodes[5]),
            (nodes[2], nodes[3], nodes[7], nodes[6]),
            (nodes[3], nodes[0], nodes[4], nodes[7]),
        )
        return max(quad_warpage_deg(f) for f in faces)
    return 0.0


def metric_summary(name: str, values: list[float]) -> dict[str, float | str | list[float]]:
    finite = [v for v in values if v == v and abs(v) != float("inf")]
    if not finite:
        return {"name": name, "min": 0.0, "max": 0.0, "mean": 0.0, "values": values}
    return {
        "name": name,
        "min": min(finite),
        "max": max(finite),
        "mean": sum(finite) / len(finite),
        "values": values,
    }
