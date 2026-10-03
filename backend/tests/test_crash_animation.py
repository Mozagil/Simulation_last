"""1.17d — anim_to_vtk ASCII → deforme şekil verisi (yüzey, kare konumları, skalerler)."""

from __future__ import annotations

import pytest

from app.postprocess.openradioss_anim import build_animation, parse_vtk_ascii, surface_faces


def _vtk(time: float, dx: float, alive: int = 1) -> str:
    # gerçek anim_to_vtk biçimi (iş cded46ab…), iki kabuk dörtgen + bir rijit duvar çizgisi
    return f"""# vtk DataFile Version 3.0
vtk output
ASCII
DATASET UNSTRUCTURED_GRID
FIELD FieldData 2
TIME 1 1 double
{time}
CYCLE 1 1 int
0
POINTS 6 float
{0 + dx} 0 0 1 0 0 1 1 0
{0 + dx} 1 0 2 0 0 2 1 0
CELLS 3 13
4 0 1 2 3
4 1 4 5 2
2 0 1
CELL_TYPES 3
9
9
3
POINT_DATA 6
SCALARS NODE_ID int 1
LOOKUP_TABLE default
1 2 3 4 5 6
VECTORS Displacement float
{dx} 0 0 0 0 0 0 0 0
{dx} 0 0 0 0 0 0 0 0
CELL_DATA 3
SCALARS ELEMENT_ID int 1
LOOKUP_TABLE default
1 2 3
SCALARS PART_ID int 1
LOOKUP_TABLE default
1 1 2
SCALARS EROSION_STATUS int 1
LOOKUP_TABLE default
1 {alive} 1
SCALARS EPSP float 1
LOOKUP_TABLE default
0.0 0.25 0
SCALARS 1DELEM_Specific_Energy float 1
LOOKUP_TABLE default
0 0 0
"""


def test_parse_vtk_ascii():
    d = parse_vtk_ascii(_vtk(0.5, -3.0))
    assert d["time"] == 0.5
    assert d["points"][0] == [-3.0, 0.0, 0.0] and len(d["points"]) == 6
    assert d["cells"][1] == [1, 4, 5, 2] and d["cell_types"] == [9, 9, 3]
    assert d["point_data"]["Displacement"][0] == [-3.0, 0.0, 0.0]
    assert d["cell_data"]["EROSION_STATUS"] == [1.0, 1.0, 1.0]


def test_surface_faces_shell_and_solid():
    faces, owner = surface_faces([[0, 1, 2, 3], [9, 9]], [9, 3])
    assert faces == [[0, 1, 2, 3]] and owner == [0]  # çizgi hücresi atlanır
    # iki tet ortak yüzü paylaşır → 4 + 4 − 2 = 6 dış yüz
    faces, owner = surface_faces([[0, 1, 2, 3], [1, 2, 3, 4]], [10, 10])
    assert len(faces) == 6 and sorted(set(owner)) == [0, 1]


def test_build_animation_frames_scalars_and_erosion():
    a = build_animation([_vtk(0.0, 0.0), _vtk(1.0, -3.0, alive=0)])
    assert a["faces"] == [[0, 1, 2, 3], [1, 4, 5, 2]] and a["face_part"] == [1, 1]
    wall = build_animation([_vtk(0.0, 0.0).replace("1 2 3 4 5 6", "1 2 3 0 5 6")])
    assert wall["faces"] == [[1, 4, 5, 2]]  # NODE_ID 0 (rijit duvar noktası) içeren yüz atlanır
    assert [f["time"] for f in a["frames"]] == [0.0, 1.0]
    assert a["frames"][1]["positions"][:3] == [-3.0, 0.0, 0.0]
    assert a["frames"][1]["node"]["disp_mag"][0] == 3.0
    assert a["frames"][1]["face_alive"] == [1, 0]  # 2. kabuk silindi
    assert a["frames"][1]["face"]["EPSP"] == [0.0, 0.25]
    assert a["scalars"]["disp_mag"] == {"location": "node", "min": 0.0, "max": 3.0}
    assert a["scalars"]["EPSP"]["max"] == pytest.approx(0.25)
    assert "1DELEM_Specific_Energy" not in a["scalars"]  # hep sıfır → gösterilmez


def test_frame_thinning_keeps_last():
    a = build_animation([_vtk(float(t), 0.0) for t in range(10)], max_frames=4)
    times = [f["time"] for f in a["frames"]]
    assert times[0] == 0.0 and times[-1] == 9.0 and len(times) <= 5
