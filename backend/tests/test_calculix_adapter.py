"""CalculiX adaptör: .inp üretimi (ccx olmadan)."""

from pathlib import Path

import pytest

from app.mesh.base import MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter
from app.solvers.calculix import CalculiXAdapter
from app.solvers.base import SolverError

FIXTURES = Path(__file__).parent / "fixtures"
BOX = FIXTURES / "box.step"


def test_materials_inp_block_converts_si_to_consistent_mm_units():
    """KRİTİK: malzeme kütüphanesi SI birimlerinde saklıyor (E: Pa,
    yoğunluk: kg/m³) ama geometri mm — CalculiX'e dönüştürmeden gönderilirse
    malzeme 1.000.000 kat daha sert görünüyordu (gerçek bir ankastre kiriş
    testinde: beklenen 25.5mm sapma yerine 0.0000226mm çıkmıştı). Bu test,
    dönüşümün .inp çıktısında doğru uygulandığını doğruluyor.
    """
    from app.solvers.calculix import _materials_inp_block

    text = _materials_inp_block(
        [
            {
                "part_id": 0,
                "name": "6061-T6",
                "youngs_modulus": 68900000000.0,  # Pa (SI, veritabanı formatı)
                "poisson_ratio": 0.33,
                "density": 2700.0,  # kg/m³ (SI, veritabanı formatı)
            }
        ],
        dimension=3,
        shell_thickness=0.0,
    )
    # E: Pa -> MPa (1e6'ya bölünmeli): 68900000000.0 / 1e6 = 68900.0
    assert "6.890000e+04" in text  # 68900 MPa
    assert "6.890000e+10" not in text  # eski (dönüştürülmemiş) Pa değeri OLMAMALI
    # yoğunluk: kg/m³ -> tonne/mm³ (1e-12 ile çarpılmalı): 2700 * 1e-12 = 2.7e-9
    assert "2.700000e-09" in text


def test_calculix_build_input_writes_material_and_section(tmp_path):
    step = tmp_path / "box.step"
    step.write_bytes(BOX.read_bytes())
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=8.0, dimension=3, element_scheme="tet")
    )

    ccx = CalculiXAdapter()
    artifact = ccx.build_input(
        {
            "mesh_path": mesh.mesh_path,
            "dimension": 3,
            "output_dir": tmp_path / "run",
            "job_name": "testjob",
            "materials": [
                {
                    "part_id": 0,
                    "name": "S355",
                    "youngs_modulus": 210e9,
                    "poisson_ratio": 0.3,
                    "density": 7850.0,
                }
            ],
            "bcs": [
                {"type": "fixed", "face_ids": [1]},
                {"type": "cload", "face_ids": [2], "fx": 0, "fy": 0, "fz": -1000},
                {"type": "gravity", "gx": 0, "gy": 0, "gz": -9810},
                {
                    "type": "displacement",
                    "edge_ids": [1],
                    "dofs": {"1": 0.0, "2": 0.0},
                },
                {
                    "type": "bearing",
                    "face_ids": [3],
                    "magnitude": 5000,
                    "axis": [0, 0, -1],
                },
                {
                    "type": "pressure",
                    "face_ids": [4],
                    "magnitude": 1e5,
                    "dz": -1,
                },
            ],
        }
    )
    text = artifact.path.read_text(encoding="utf-8")
    assert "*MATERIAL, NAME=S355" in text
    assert "*ELASTIC" in text
    assert "*DENSITY" in text
    assert "*SOLID SECTION" in text
    assert "*BOUNDARY" in text
    assert "*CLOAD" in text
    assert "*STEP" in text
    assert "GRAV" in text


def test_bcs_pressure_dload_and_sliding_transform():
    from app.solvers.calculix import _bcs_inp_block

    nsets = {"FACE_1": [1, 2, 3], "EDGE_1": [4, 5]}
    elsets = {"FACE_EL_1": [10, 11], "PART_0": [10, 11]}
    model_text, step_text = _bcs_inp_block(
        [
            {"type": "pressure", "face_ids": [1], "magnitude": 1e5},
            {
                "type": "sliding",
                "edge_ids": [1],
                "normal": [0.0, 0.0, 1.0],
            },
            {"type": "gravity", "gx": 0, "gy": 0, "gz": -9810},
        ],
        nsets,
        elsets,
        dimension=2,
    )
    # KRİTİK: *DLOAD (yük) SADECE step_text'te olmalı, model_text'te DEĞİL —
    # gerçek bir CalculiX çalıştırmasında *CLOAD/*DLOAD *STEP dışında kalınca
    # "should only be used within a STEP" hatasıyla durduğu doğrulandı.
    assert "*DLOAD" in step_text
    assert "*DLOAD" not in model_text
    assert "FACE_EL_1, P," in step_text
    assert "PART_0, GRAV," in step_text
    # *TRANSFORM/*BOUNDARY (model seviyesi) model_text'te olmalı.
    assert "*TRANSFORM, NSET=EDGE_1" in model_text
    assert "EDGE_1, 1, 1" in model_text
    assert "*TRANSFORM" not in step_text


def test_cload_edge_ids_distributes_force_across_edge_nodes():
    """KRİTİK: kenar seçip kuvvet uygulama (ör. ankastre kiriş serbest uç
    yükü, klasik mukavemet problemi) — toplam kuvvet, kenardaki node
    sayısına eşit bölünmeli.
    """
    from app.solvers.calculix import _bcs_inp_block

    nsets = {"EDGE_12": [226, 227, 228]}
    _model_text, step_text = _bcs_inp_block(
        [{"type": "cload", "edge_ids": [12], "fx": 0, "fy": -9000, "fz": 0}],
        nsets,
        {},
        dimension=3,
    )
    assert "*CLOAD" in step_text
    # 9000 N / 3 node = 3000 N her birine.
    assert "226, 2, -3000" in step_text
    assert "227, 2, -3000" in step_text
    assert "228, 2, -3000" in step_text


def test_calculix_submit_without_ccx_raises(tmp_path):
    inp = tmp_path / "x.inp"
    inp.write_text("*HEADING\n", encoding="utf-8")
    from app.solvers.base import InputArtifact
    from unittest.mock import patch

    ccx = CalculiXAdapter()
    # Bu sandbox'ta gerçek ccx kurulu olabilir (biz kurduk) — test her
    # ortamda tutarlı çalışsın diye _ccx_executable'ı None dönecek şekilde
    # geçici olarak mock'luyoruz (gerçek "kurulu değil" senaryosu).
    with patch("app.solvers.calculix._ccx_executable", return_value=None):
        with pytest.raises(SolverError, match="ccx"):
            ccx.submit(InputArtifact(path=inp))


# Gerçek bir CalculiX çalıştırmasından alınmış (box.step, 18 düğüm) örnek
# .frd içeriği — sabit sütun genişlikli format, negatif sayılarda boşluk
# YOK (ör. "3.50000E+00-1.00000E-07"). Bu, hermetik (ccx kurulu olmadan da
# çalışan) parser testleri için kullanılıyor.
_SAMPLE_FRD_CONTENT = """    1C
    2C                            18                                     1
 -1        10 3.50000E+00-1.00000E-07-1.00000E-07
 -1        12 6.50000E+00-1.00000E-07-1.00000E-07
 -3
    1PSTEP                         1           1           1          
  100CL  101 1.000000000          18                     0    1           1
 -4  DISP        4    1
 -5  D1          1    2    1    0
 -5  D2          1    2    2    0
 -5  D3          1    2    3    0
 -5  ALL         1    2    0    0    1ALL
 -1        10 1.00000E-02 2.00000E-02 3.00000E-02
 -1        12 0.00000E+00 0.00000E+00 0.00000E+00
 -3
    1PSTEP                         2           1           1          
  100CL  101 1.000000000          18                     0    1           1
 -4  STRESS      6    1
 -5  SXX         1    4    1    1
 -5  SYY         1    4    2    2
 -5  SZZ         1    4    3    3
 -5  SXY         1    4    1    2
 -5  SYZ         1    4    2    3
 -5  SZX         1    4    3    1
 -1        10 1.00000E+02 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
 -1        12 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
 -3
 9999
"""


def test_frd_data_line_parses_columns_without_spaces_between_negatives():
    """KRİTİK: negatif sayılar arasında boşluk olmayan gerçek .frd satırları
    (`split()` ile YANLIŞ parse edilir) — sabit sütun genişliğiyle doğru
    ayrıştırıldığı gerçek bir örnekle doğrulandı.
    """
    from app.solvers.calculix import _frd_data_line

    line = " -1        10 3.50000E+00-1.00000E-07-1.00000E-07"
    result = _frd_data_line(line)
    assert result is not None
    node_id, values = result
    assert node_id == 10
    assert values == pytest.approx([3.5, -1e-7, -1e-7])


def test_parse_frd_extracts_node_coords_displacement_and_stress(tmp_path):
    from app.solvers.calculix import _parse_frd

    frd_path = tmp_path / "sample.frd"
    frd_path.write_text(_SAMPLE_FRD_CONTENT, encoding="utf-8")

    result = _parse_frd(frd_path)

    assert result["node_coords"][10] == pytest.approx((3.5, -1e-7, -1e-7))
    assert result["node_coords"][12] == pytest.approx((6.5, -1e-7, -1e-7))

    assert result["displacement"][10] == pytest.approx((0.01, 0.02, 0.03))
    assert result["displacement"][12] == pytest.approx((0.0, 0.0, 0.0))

    assert result["stress"][10] == pytest.approx((100.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    assert result["stress"][12] == pytest.approx((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))


def test_von_mises_stress_uniaxial_case():
    """Saf tek eksenli gerilmede (sadece SXX) von Mises = SXX olmalı —
    ders kitabı doğrulaması.
    """
    from app.solvers.calculix import _von_mises_stress

    assert _von_mises_stress(100.0, 0, 0, 0, 0, 0) == pytest.approx(100.0)
    assert _von_mises_stress(0, 0, 0, 0, 0, 0) == pytest.approx(0.0)


def test_parse_results_writes_results_preview_json_aligned_with_node_order(tmp_path):
    """KRİTİK: parse_results, .frd'nin `2C` bloğundaki node sırasını koruyarak
    (mesh önizlemesiyle aynı sıra) bir results.json üretmeli — frontend'in
    node-index bazlı renklendirmesi için gerekli.
    """
    from app.solvers.base import InputArtifact, JobHandle

    frd_path = tmp_path / "job.frd"
    frd_path.write_text(_SAMPLE_FRD_CONTENT, encoding="utf-8")

    artifact = InputArtifact(path=tmp_path / "job.inp")
    handle = JobHandle(job_id="test", work_dir=tmp_path, artifact=artifact)

    adapter = CalculiXAdapter()
    result_set = adapter.parse_results(handle)

    assert result_set.results_preview_path is not None
    assert result_set.results_preview_path.exists()

    import json

    preview = json.loads(result_set.results_preview_path.read_text())
    assert preview["node_ids"] == [10, 12]
    assert preview["nodes"][0] == pytest.approx([3.5, -1e-7, -1e-7])
    assert preview["displacement_magnitude"][0] == pytest.approx(
        (0.01**2 + 0.02**2 + 0.03**2) ** 0.5
    )
    assert preview["displacement_vectors"][0] == pytest.approx([0.01, 0.02, 0.03])
    assert preview["displacement_vectors"][1] == pytest.approx([0.0, 0.0, 0.0])
    assert preview["von_mises"][0] == pytest.approx(100.0)
    assert preview["von_mises"][1] == pytest.approx(0.0)
    # Kritik node: von_mises'in en yüksek olduğu node_id (10, index 0 — 100.0)
    assert preview["critical_node_id"] == 10
    assert preview["max_von_mises"] == pytest.approx(100.0)

    assert result_set.scalars["max_von_mises"] == pytest.approx(100.0)
    assert result_set.scalars["node_count"] == 2.0


@pytest.mark.skipif(
    __import__("shutil").which("ccx") is None,
    reason="CalculiX (ccx) kurulu değil - gerçek çözüm testi atlanıyor",
)
def test_end_to_end_solve_produces_nonzero_results(tmp_path):
    """UÇTAN UCA (gerçek ccx ile): dejenere olmayan bir kiriş senaryosu
    (bir kenar sabit, tüm yüzeye yük) gerçekten sıfır olmayan von Mises
    üretmeli — gerçek bir kullanıcı senaryosunda doğrulandı.
    """
    import gmsh

    from app.mesh.gmsh_adapter import GmshMesherAdapter
    from app.mesh.base import MeshParams
    from app.solvers.base import InputArtifact

    fixture = BOX
    test_file = tmp_path / "beam_test.step"
    test_file.write_bytes(fixture.read_bytes())

    mesh_adapter = GmshMesherAdapter()
    geom = mesh_adapter.import_geometry(test_file)
    new_face_id = mesh_adapter.create_midsurface(geom, 1, 2)

    geom2 = mesh_adapter.import_geometry(test_file)
    mesh_result = mesh_adapter.generate_mesh(
        geom2,
        MeshParams(dimension=2, element_size=2.0, element_scheme="quad"),
    )

    ccx_adapter = CalculiXAdapter()
    artifact = ccx_adapter.build_input(
        {
            "mesh_path": mesh_result.mesh_path,
            "dimension": 2,
            "output_dir": tmp_path / "run",
            "job_name": "beam",
            "materials": [
                {
                    "part_id": 0,
                    "name": "TestSteel",
                    "density": 7850.0,
                    "youngs_modulus": 2.1e11,
                    "poisson_ratio": 0.3,
                }
            ],
            "shell_thickness": 3.0,
            "bcs": [
                {"type": "fixed", "edge_ids": [13]},
                {"type": "cload", "face_ids": [new_face_id], "fx": 0, "fy": 0, "fz": -50},
            ],
        }
    )
    handle = ccx_adapter.submit(artifact)
    ccx_adapter.poll_status(handle)
    result_set = ccx_adapter.parse_results(handle)

    assert result_set.scalars["max_von_mises"] > 0.0
    assert result_set.results_preview_path is not None
    assert result_set.results_preview_path.exists()
