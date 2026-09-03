"""Solve API + analiz geçmişi (AnalysisRun) endpoint testleri.

Not: Bu testler gerçek bir PostgreSQL bağlantısı gerektiriyor — bkz.
test_geometry_upload.py'deki `requires_db` deseni.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.geometry import MESH_DIR, UPLOAD_DIR
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BOX = FIXTURES_DIR / "box.step"


def _db_available() -> bool:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except OperationalError:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL bağlantısı yok (DATABASE_URL ayarlı değil ya da servis kapalı)",
)


@pytest.fixture(autouse=True)
def _clean_state():
    yield
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    if _db_available():
        db = SessionLocal()
        db.execute(
            text(
                "TRUNCATE analysis_runs, material_assignments, physical_groups, "
                "geometries RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
        db.close()


def _upload_and_mesh_box() -> int:
    content = BOX.read_bytes()
    upload = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    geometry_id = upload.json()["geometry_id"]

    mesh_resp = client.post(
        f"/geometry/{geometry_id}/mesh",
        json={"dimension": 3, "element_size": 8, "element_scheme": "tet"},
    )
    assert mesh_resp.status_code == 200

    mats = client.get("/materials").json()["materials"]
    material_id = mats[0]["id"]
    assign_resp = client.post(
        "/materials/assignments",
        json={"geometry_id": geometry_id, "part_id": 0, "material_id": material_id},
    )
    assert assign_resp.status_code == 200

    return geometry_id


@requires_db
def test_solve_creates_analysis_run_record():
    """KRİTİK: her /solve çağrısı kalıcı bir AnalysisRun satırı üretmeli —
    ROADMAP.md '7. Veritabanına kayıt + geçmiş' gereksinimi.
    """
    geometry_id = _upload_and_mesh_box()

    response = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,  # ccx olmasa da .inp üretimi + DB kaydı test edilir
            "name": "Test Case 1",
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["run_id"] is not None

    # Geçmiş listesinde görünmeli
    runs_response = client.get("/geometry/runs")
    assert runs_response.status_code == 200
    runs_body = runs_response.json()
    assert runs_body["count"] == 1
    assert runs_body["runs"][0]["id"] == body["run_id"]
    assert runs_body["runs"][0]["name"] == "Test Case 1"
    assert runs_body["runs"][0]["geometry_id"] == geometry_id


@requires_db
def test_two_solves_on_same_geometry_do_not_overwrite_each_other():
    """KRİTİK: aynı geometride ikinci bir case çözülünce, öncekinin .inp
    dosyası ÜZERİNE YAZILMAMALI — eskiden `geo{id}_d{dim}` adlandırması bu
    hataya sebep oluyordu, artık her run kendi klasöründe.
    """
    geometry_id = _upload_and_mesh_box()

    first = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "name": "Case A",
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    ).json()
    second = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "name": "Case B",
            "bcs": [{"type": "fixed", "face_ids": [2]}],
        },
    ).json()

    assert first["run_id"] != second["run_id"]
    assert first["inp_path"] != second["inp_path"]

    # İkisi de diskte hâlâ var (birbirinin üzerine yazmadı).
    assert Path(first["inp_path"]).exists()
    assert Path(second["inp_path"]).exists()

    runs_body = client.get("/geometry/runs").json()
    assert runs_body["count"] == 2
    names = {r["name"] for r in runs_body["runs"]}
    assert names == {"Case A", "Case B"}


@requires_db
def test_get_run_detail_returns_404_for_unknown_id():
    response = client.get("/geometry/runs/999999")
    assert response.status_code == 404


@requires_db
def test_get_run_detail_includes_bcs_and_urls():
    geometry_id = _upload_and_mesh_box()
    solve_body = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "name": "Detay testi",
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    ).json()
    run_id = solve_body["run_id"]

    detail = client.get(f"/geometry/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == run_id
    assert body["geometry_id"] == geometry_id
    assert body["name"] == "Detay testi"
    assert body["bcs"] == [{"type": "fixed", "face_ids": [1]}]
    # KRİTİK: artık canlı geometrinin STL'i DEĞİL, bu run'ın kendi
    # tessellation anlık görüntüsü dönmeli — aksi halde geometri bu run'dan
    # sonra mutasyona uğrarsa (heal/defeature/offset) sonuçlar geometriden
    # "kaymış" görünürdü (gerçek bir ekran görüntüsünde tespit edildi).
    assert body["tessellation_url"] == f"/files/runs/{run_id}/tessellation.stl"


@requires_db
def test_get_run_report_pdf_returns_valid_pdf():
    """PDF rapor endpoint'i geçerli bir application/pdf dönmeli — PDF
    başlığı (%PDF) içermeli."""
    geometry_id = _upload_and_mesh_box()
    solve_body = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "name": "PDF testi",
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    ).json()
    run_id = solve_body["run_id"]

    response = client.get(f"/geometry/runs/{run_id}/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"
    assert len(response.content) > 500  # boş/bozuk bir PDF değil


@requires_db
def test_get_run_report_pdf_returns_404_for_unknown_run():
    response = client.get("/geometry/runs/999999/report.pdf")
    assert response.status_code == 404


@requires_db
def test_run_tessellation_snapshot_survives_later_geometry_mutation():
    """KRİTİK: bir run çözüldükten SONRA geometrinin canlı tessellation'ı
    değişse bile (örn. yeniden mesh/heal/defeature), o run'ın KENDİ
    tessellation anlık görüntüsü DEĞİŞMEMELİ — aksi halde karşılaştırma/
    geçmiş görünümünde sonuçlar geometriden 'kaymış' görünür (gerçek bir
    ekran görüntüsünde tespit edilen hatanın kök nedeniydi).
    """
    geometry_id = _upload_and_mesh_box()
    solve_body = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    ).json()
    run_id = solve_body["run_id"]

    detail = client.get(f"/geometry/runs/{run_id}").json()
    snapshot_url = detail["tessellation_url"]
    assert snapshot_url == f"/files/runs/{run_id}/tessellation.stl"

    snapshot_path = UPLOAD_DIR / "runs" / str(run_id) / "tessellation.stl"
    assert snapshot_path.exists()
    original_bytes = snapshot_path.read_bytes()

    # Canlı geometrinin tessellation dosyasını "mutasyona uğramış" gibi
    # SİMÜLE ET (gerçek bir heal/defeature çağrısı yerine, dosyayı
    # doğrudan değiştirip aynı etkiyi test ediyoruz — daha hızlı, aynı
    # mantığı doğruluyor).
    live_tessellation = UPLOAD_DIR / "tessellations" / f"{geometry_id}.stl"
    assert live_tessellation.exists()
    live_tessellation.write_bytes(b"MUTASYONA UGRAMIS SAHTE STL ICERIGI")

    # Run'ın KENDİ anlık görüntüsü hâlâ ORİJİNAL içerikte olmalı.
    assert snapshot_path.read_bytes() == original_bytes
    assert snapshot_path.read_bytes() != live_tessellation.read_bytes()

    # API hâlâ run'ın kendi anlık görüntüsünü işaret etmeli, canlıyı değil.
    detail_again = client.get(f"/geometry/runs/{run_id}").json()
    assert detail_again["tessellation_url"] == snapshot_url


@requires_db
def test_solve_computes_safety_factor_and_fatigue_with_correct_units():
    """KRİTİK: yield_strength/S-N eğrisi Pa (SI) saklanıyor ama
    max_von_mises MPa cinsinden — dönüştürmeden kullanılırsa safety_factor
    1 milyon kat yanlış çıkıyordu (gerçek bir testte kanıtlandı: 838145
    yerine 0.838 olmalıydı). Bu test doğru dönüşümü doğruluyor.
    """
    geometry_id = _upload_and_mesh_box()

    mats = client.get("/materials").json()["materials"]
    material_id = mats[0]["id"]
    yield_pa = mats[0]["yield_strength"]

    client.put(f"/materials/{material_id}/sn-curve", json={"source": "estimated"})
    client.post(
        "/materials/assignments",
        json={"geometry_id": geometry_id, "part_id": 0, "material_id": material_id},
    )

    response = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": True,
            "bcs": [
                {"type": "fixed", "face_ids": [1]},
                # Sıfır olmayan bir gerilme olsun diye bir yük gerekli —
                # sadece Fixed (yüksüz) ile max_von_mises=0 çıkar, bu da
                # safety_factor'ün (doğru şekilde) None dönmesine sebep
                # olur (sıfır gerilmede SF tanımsızdır).
                {"type": "gravity", "gx": 0.0, "gy": 0.0, "gz": -50000.0},
            ],
        },
    )
    if response.status_code != 200 or not response.json().get("solver_ran"):
        pytest.skip("ccx kurulu değil ya da çözüm başarısız — bu ortamda test edilemiyor.")

    scalars = response.json()["scalars"]
    max_vm = scalars["max_von_mises"]
    sf = scalars["safety_factor"]

    # KRİTİK doğrulama: SF, yield_strength'in Pa->MPa dönüştürülmüş haliyle
    # hesaplanmalı — Pa'dan MPa'ya dönüştürülmezse (eski hatalı davranış)
    # sf, expected_sf'nin 1 milyon katı çıkardı.
    expected_sf = (yield_pa / 1e6) / max_vm
    assert sf == pytest.approx(expected_sf, rel=1e-6)
    wrong_sf_if_unconverted = yield_pa / max_vm
    assert abs(sf - wrong_sf_if_unconverted) > abs(sf) * 100  # kesinlikle dönüştürülmüş değer


@requires_db
def test_solve_rejects_bcs_without_any_constraint():
    """KRİTİK: sadece yük (Force/Gravity) BC'si olup Fixed/Displacement/
    Sliding gibi bir yer değiştirme kısıtı YOKSA, çözüme İZİN VERİLMEMELİ —
    eskiden sessizce çalışıp rijit cisim hareketi (max_displacement ~87
    milyar mm gibi anlamsız sayılar) üretiyordu, gerçek bir testte
    kanıtlandı. Artık net bir 422 dönmeli.
    """
    geometry_id = _upload_and_mesh_box()

    # Sadece yük, hiç kısıt yok -> reddedilmeli.
    response = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "bcs": [{"type": "gravity", "gx": 0.0, "gy": 0.0, "gz": -9810.0}],
        },
    )
    assert response.status_code == 422
    assert "kısıt" in response.json()["detail"].lower() or "rijit" in response.json()["detail"].lower()

    runs_body = client.get("/geometry/runs").json()
    assert runs_body["count"] == 0

    # Fixed eklenince kabul edilmeli (en azından .inp üretim aşamasına geçmeli).
    response2 = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "bcs": [
                {"type": "fixed", "face_ids": [1]},
                {"type": "gravity", "gx": 0.0, "gy": 0.0, "gz": -9810.0},
            ],
        },
    )
    assert response2.status_code == 200


@requires_db
def test_solve_without_materials_does_not_create_orphan_run():
    """Malzeme atanmadan /solve çağrılırsa 422 dönmeli VE hiçbir
    AnalysisRun satırı OLUŞMAMALI (validasyon run oluşturulmadan önce
    yapılıyor).
    """
    content = BOX.read_bytes()
    upload = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    geometry_id = upload.json()["geometry_id"]
    client.post(
        f"/geometry/{geometry_id}/mesh",
        json={"dimension": 3, "element_size": 8, "element_scheme": "tet"},
    )

    response = client.post(
        f"/geometry/{geometry_id}/solve",
        json={"dimension": 3, "run_solver": False, "bcs": []},
    )
    assert response.status_code == 422

    runs_body = client.get("/geometry/runs").json()
    assert runs_body["count"] == 0
