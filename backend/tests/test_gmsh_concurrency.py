"""GmshMesherAdapter'ın eşzamanlı (concurrent) çağrılara karşı güvenli olduğunu
doğrulayan test.

Arka plan: Frontend, upload sonrası edges + points endpoint'lerini
`Promise.all` ile PARALEL çağırıyor. FastAPI'nin sync endpoint'leri uvicorn
tarafından bir thread pool'da çalıştırıldığı için bu iki istek gerçekten aynı
anda farklı thread'lerde Gmsh'e dokunabiliyordu. Gmsh'in global C++ durumu
thread-safe olmadığından bu segmentation fault'a yol açıyordu (gerçek bir
testte doğrulandı, bu yüzden `_gmsh_lock` eklendi — bkz. gmsh_adapter.py).
"""

import threading
from pathlib import Path

from app.mesh.gmsh_adapter import GmshMesherAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_STEP_FILE = FIXTURES_DIR / "box.step"


def test_concurrent_geometry_operations_do_not_corrupt_state():
    """Aynı anda birden fazla thread'den import + list çağrıları yapılınca
    hiçbiri çökmemeli ve hepsi doğru sonuç vermeli.
    """
    results: dict[int, tuple[str, int]] = {}
    errors: dict[int, str] = {}
    results_lock = threading.Lock()

    expected_counts = {"edges": 12, "points": 8, "surfaces": 6}

    def worker(index: int, method: str) -> None:
        try:
            adapter = GmshMesherAdapter()
            geom = adapter.import_geometry(VALID_STEP_FILE)
            if method == "edges":
                items = adapter.list_edges(geom)
            elif method == "points":
                items = adapter.list_points(geom)
            else:
                items = adapter.list_surfaces(geom)
            with results_lock:
                results[index] = (method, len(items))
        except Exception as exc:  # noqa: BLE001 - testte tüm hataları yakala
            with results_lock:
                errors[index] = str(exc)

    methods = (["edges", "points", "surfaces"] * 4)  # 12 eşzamanlı çağrı
    threads = [
        threading.Thread(target=worker, args=(i, m)) for i, m in enumerate(methods)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == {}, f"Eşzamanlı çağrılarda hata oluştu: {errors}"
    assert len(results) == len(methods)
    for method, count in results.values():
        assert count == expected_counts[method]
