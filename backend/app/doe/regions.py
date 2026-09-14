"""İsimlendirilmiş bölge -> face/edge id (0.5.4).

DOE BC'leri şablon yüzey numarasına değil bölge adına bağlanır. Parametre
değişince Gmsh etiketleri kayabilir; isim `PhysicalGroup` üzerinden sabit kalır.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.geometry import PhysicalGroup


class DoeBindError(ValueError):
    pass


def groups_by_name(db: Session, geometry_id: int) -> dict[str, PhysicalGroup]:
    rows = db.query(PhysicalGroup).filter(PhysicalGroup.geometry_id == geometry_id).all()
    return {g.name: g for g in rows}


def bind_scenario_bcs(
    groups: dict[str, PhysicalGroup],
    bcs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """`region` alanını face_ids / edge_ids ile değiştirir."""
    bound: list[dict[str, Any]] = []
    for raw in bcs:
        bc = dict(raw)
        region = bc.pop("region", None)
        if region:
            group = groups.get(str(region))
            if group is None:
                raise DoeBindError(
                    f"Bölge '{region}' yok. Mevcut: {sorted(groups)}"
                )
            tags = list(group.entity_tags or [])
            if not tags:
                raise DoeBindError(f"Bölge '{region}' boş.")
            if int(group.dim) == 1:
                bc["edge_ids"] = tags
            else:
                bc["face_ids"] = tags
        bound.append(bc)
    return bound
