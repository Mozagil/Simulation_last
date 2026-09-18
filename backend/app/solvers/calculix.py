"""CalculiX (ccx) solver adaptörü — Faz 0 durability.

`build_input`: Gmsh .msh → Abaqus/CalculiX .inp + malzeme + BC kartları.
`submit`: `ccx` subprocess (CCX_PATH veya PATH). Kurulu değilse SolverError.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import gmsh

from app.mesh.gmsh_adapter import _gmsh_lock
from app.solvers.base import (
    InputArtifact,
    JobHandle,
    JobStatus,
    ResultSet,
    SolverAdapter,
    SolverError,
)

logger = logging.getLogger(__name__)

_GMSH_TO_CCX_3D = {
    4: "C3D4",  # tet4
    11: "C3D10",  # tet10
    5: "C3D8",  # hex8
}
_GMSH_TO_CCX_2D = {
    2: "S3",  # tri3 shell
    3: "S4",  # quad4 shell
}

# KRİTİK: Gmsh tet10 (tip 11) ile Abaqus/CalculiX C3D10 düğüm sıralaması
# kenar-ortası düğümlerin SON İKİSİNDE farklıdır. Gmsh sıralaması
# (dokümantasyondaki Tetrahedron10 şeması):
#   4=orta(0,1)  5=orta(1,2)  6=orta(0,2)  7=orta(0,3)  8=orta(2,3)  9=orta(1,3)
# CalculiX/Abaqus C3D10 sıralaması (1-based 5..10):
#   5=orta(1,2)  6=orta(2,3)  7=orta(3,1)  8=orta(1,4)  9=orta(2,4)  10=orta(3,4)
# 0-based karşılığı: 4=orta(0,1) 5=orta(1,2) 6=orta(0,2) 7=orta(0,3)
#                    8=orta(1,3) 9=orta(2,3)
# Yani Gmsh'in 8. ve 9. düğümleri YER DEĞİŞTİRMELİ. Bu yapılmazsa eleman
# jakobyeni bozulur ve CalculiX ya hata verir ya da tamamen yanlış sonuç
# üretir.
_GMSH_TO_CCX_TET10_ORDER = (0, 1, 2, 3, 4, 5, 6, 7, 9, 8)



#: CalculiX katı eleman yüz numaraları, KÖŞE düğüm indeksleriyle (0-tabanlı,
#: CalculiX sırasına göre). Yüzey yükü (*DSLOAD) uygulanırken bir sınır
#: üçgeninin hangi elemanın hangi yüzü olduğunu bulmak için kullanılır.
#:
#: NEDEN GEREKLİ — ölçtük: toplam kuvvet yüzey düğümlerine EŞİT bölünüyordu
#: (`fx / n`). Kuadratik elemanlarda (C3D10) bu YANLIŞ: düzgün bir yüzey
#: yükünün tutarlı düğüm kuvvetleri eşit değildir, köşe ve kenar-orta
#: düğümleri farklı ağırlık alır. Sonuç: yükleme yüzeyinde sahte yerel
#: salınım.
#:
#: Delikli plaka taramasında (study 10, 7 basamak) bu salınım u_max'ı
#: mesh'ten mesh'e %36 oynattı — beş mesh 0.0603–0.0609 mm'de uyuşurken
#: ikisi 0.0656 ve 0.0848 verdi. Mesh kaliteleri iyiydi (Jacobian 0.75 ve
#: 0.84; "sağlam" olanınki 0.60), yani sebep mesh değildi. σ etkilenmedi
#: çünkü tepe gerilme delikte, yükleme yüzeyinden uzakta.
#:
#: Kirişte fark edilmemişti: orada sehim 23 mm, aynı salınım yanında
#: görünmez kalıyor. Plakada gerçek deplasman 0.06 mm olunca baskın hale
#: geldi.
#: gmsh 2B eleman tipi -> düğüm sayısı. Sınır üçgenlerini ana katı
#: elemanla eşlerken bağlantı dizisini doğru adımlamak için.
_SURF_NODES_PER: dict[int, int] = {
    2: 3,   # tri3
    3: 4,   # quad4
    9: 6,   # tri6
    16: 8,  # quad8
}

_CCX_SOLID_FACES: dict[str, tuple[tuple[int, ...], ...]] = {
    # 4 ve 10 düğümlü tet: yüz köşeleri (CalculiX kılavuzu, C3D4/C3D10)
    "C3D4": ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)),
    "C3D10": ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)),
    # 8 düğümlü hex: C3D8 yüzleri
    "C3D8": (
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ),
}


def _solid_face_lookup(
    ccx_type: str, elem_id: int, conn: list[int]
) -> list[tuple[frozenset[int], int, int]]:
    """Bir katı elemanın her yüzü için (köşe kümesi, eleman id, yüz no).

    Yüz numarası CalculiX'in 1-tabanlı P1..P6 gösterimidir. Köşe kümesi
    sırasızdır; sınır üçgeni hangi sırayla gelirse gelsin eşleşsin diye.
    """
    faces = _CCX_SOLID_FACES.get(ccx_type)
    if not faces:
        return []
    out: list[tuple[frozenset[int], int, int]] = []
    for fi, idxs in enumerate(faces, start=1):
        try:
            corners = frozenset(conn[i] for i in idxs)
        except IndexError:
            continue
        out.append((corners, elem_id, fi))
    return out


def _reorder_connectivity(conn: list[int], gmsh_etype: int) -> list[int]:
    """Gmsh eleman bağlantısını CalculiX'in beklediği sıraya çevirir.

    Şimdilik yalnız tet10 (tip 11) yeniden sıralama gerektiriyor; diğer
    desteklenen tipler (tet4, hex8, tri3, quad4) iki formatta da aynı
    sıradadır.
    """
    if gmsh_etype == 11 and len(conn) == 10:
        return [conn[i] for i in _GMSH_TO_CCX_TET10_ORDER]
    return conn


def _frd_data_line(line: str) -> tuple[int, list[float]] | None:
    """CalculiX .frd sabit-sütun-genişlikli veri satırını parse eder.

    Format (gerçek bir .frd dosyasıyla doğrulandı): " -1" + node_id (10
    karakter) + N × değer (12 karakter). Negatif sayılarda boşluk OLMADIĞI
    için basit `split()` yanlış parse eder — sütun pozisyonuna göre dilimleme
    zorunlu.
    """
    if not line.startswith(" -1"):
        return None
    try:
        node_id = int(line[3:13])
    except ValueError:
        return None
    values: list[float] = []
    pos = 13
    while pos + 12 <= len(line):
        chunk = line[pos : pos + 12]
        try:
            values.append(float(chunk))
        except ValueError:
            break
        pos += 12
    return node_id, values


def _read_inp_nodes(inp_path: Path) -> list[tuple[float, float, float]]:
    """`.inp` içindeki `*NODE` bloğundan ORİJİNAL mesh düğüm koordinatları.

    Bu dosyayı biz yazdığımız için içerik kesin: düğümler `getNodes()`
    sırasında, 1-based ardışık numaralarla. Kabuk genişletmesini geri
    katlarken referans olarak kullanılır — `parse_results`'a mesh yolu
    ayrıca taşınmasın diye.
    """
    nodes: list[tuple[float, float, float]] = []
    in_node = False
    try:
        with inp_path.open(encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("*"):
                    in_node = line.upper().startswith("*NODE") and "FILE" not in line.upper()
                    continue
                if not in_node:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 4:
                    continue
                try:
                    nodes.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    continue
    except OSError:
        return []
    return nodes



def _collapse_shell_expansion(
    node_coords: dict[int, tuple[float, ...]],
    displacement: dict[int, tuple[float, ...]],
    stress: dict[int, tuple[float, ...]],
    mesh_nodes: list[tuple[float, float, float]],
) -> tuple[list[int], list[list[float]], dict[int, tuple[float, ...]], dict[int, tuple[float, ...]]] | None:
    """Kabuk genişletmesini orta yüzeye geri katlar.

    CalculiX kabuk elemanlarını içeride 3B hacme genişletir: her kabuk
    düğümü üst/alt yüzey için ikiye katlanır ve `.frd` bu genişletilmiş
    düğümleri yazar. Sonuç `.frd` düğüm sayısının mesh'in İKİ KATI olması,
    ikisinin hizalanamaması ve arayüzün düzgün yüzey konturu yerine kaba
    bir nokta bulutuna düşmesiydi.

    Burada her genişletilmiş düğüm, koordinatça en yakın ORİJİNAL mesh
    düğümüne atanır (üst/alt kopya orijinalin ±t/2 normal ötesindedir,
    yani en yakın orijinal düğüm daima kendi orta yüzey düğümüdür).
    Sonra her grup tek bir değere indirilir:

      * von Mises  -> MAKSİMUM. Eğilmede gerilme kalınlık boyunca lineerdir
        ve tasarımda aranan YÜZEY gerilmesidir; ortalama alınsaydı eğilme
        bileşeni sıfırlanırdı (OUTPUT=2D denemesinde tam olarak bu oldu:
        300 MPa yerine 79.8 MPa).
      * deplasman  -> ORTALAMA. Kalınlık boyunca neredeyse sabittir; ortalama
        orta yüzey değerini verir.

    Genişletme yoksa (3D solid) veya eşleşme güvenilir değilse None döner
    ve çağıran eski yola devam eder.
    """
    if not node_coords or not mesh_nodes:
        return None
    # Genişletme yoksa dokunma.
    if len(node_coords) <= len(mesh_nodes):
        return None

    # Uzamsal ızgara — O(n*m) mesafe hesabından kaçınmak için.
    xs = [p[0] for p in mesh_nodes]
    ys = [p[1] for p in mesh_nodes]
    zs = [p[2] for p in mesh_nodes]
    span = max(
        max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1e-9
    )
    cell = span / 64.0 or 1.0

    def key(x: float, y: float, z: float) -> tuple[int, int, int]:
        return (int(x // cell), int(y // cell), int(z // cell))

    grid: dict[tuple[int, int, int], list[int]] = {}
    for i, (x, y, z) in enumerate(mesh_nodes):
        grid.setdefault(key(x, y, z), []).append(i)

    def nearest(x: float, y: float, z: float) -> int | None:
        """Genişleyen halka araması.

        Sabit ±1 komşuluk YETMEZ: genişletilmiş düğüm orta yüzeyden
        ±kalınlık/2 kadar uzaktadır ve bu mesafe ızgara hücresinden büyük
        olabilir (t=10 kabukta ofset 5mm iken hücre 1.6mm çıkıyordu —
        eşleşme bulunamayıp katlama sessizce devre dışı kalıyordu).
        Bu yüzden yarıçap, bir aday bulunana kadar büyütülür.
        """
        kx, ky, kz = key(x, y, z)
        for r in range(1, 33):
            best_i: int | None = None
            best_d2 = float("inf")
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        # Yalnız kabuğun yüzeyindeki yeni hücreler
                        if max(abs(dx), abs(dy), abs(dz)) != r and r > 1:
                            continue
                        for i in grid.get((kx + dx, ky + dy, kz + dz), ()):
                            mx, my, mz = mesh_nodes[i]
                            d2 = (mx - x) ** 2 + (my - y) ** 2 + (mz - z) ** 2
                            if d2 < best_d2:
                                best_d2 = d2
                                best_i = i
            if best_i is not None:
                return best_i
        return None

    groups: dict[int, list[int]] = {}
    for nid, c in node_coords.items():
        x, y, z = float(c[0]), float(c[1]), float(c[2])
        best_i = nearest(x, y, z)
        if best_i is None:
            return None  # eşleşmeyen düğüm var — güvenli tarafta kal
        groups.setdefault(best_i, []).append(nid)

    # Her orijinal düğüme en az bir sonuç düşmeli.
    if len(groups) != len(mesh_nodes):
        return None

    new_order: list[int] = []
    new_nodes: list[list[float]] = []
    new_disp: dict[int, tuple[float, ...]] = {}
    new_stress: dict[int, tuple[float, ...]] = {}

    for i in range(len(mesh_nodes)):
        members = groups[i]
        out_id = min(members)  # kararlı, tekrarlanabilir bir kimlik
        new_order.append(out_id)
        new_nodes.append([float(v) for v in mesh_nodes[i]])

        dvals = [displacement[m] for m in members if m in displacement]
        if dvals:
            n = len(dvals)
            new_disp[out_id] = tuple(
                sum(d[k] for d in dvals) / n for k in range(3)
            )

        svals = [stress[m] for m in members if m in stress]
        if svals:
            # von Mises'i maksimize eden bileşen setini seç — ortalama
            # almak eğilme bileşenini yok ederdi.
            best = max(
                svals,
                key=lambda v: _von_mises_stress(v[0], v[1], v[2], v[3], v[4], v[5]),
            )
            new_stress[out_id] = best

    return new_order, new_nodes, new_disp, new_stress



def _parse_frd(frd_path: Path) -> dict[str, dict[int, tuple[float, ...]]]:
    """CalculiX .frd (ASCII) sonuç dosyasını parse eder.

    Döndürür: node_coords (id -> (x,y,z)), displacement (id -> (dx,dy,dz)),
    stress (id -> (sxx,syy,szz,sxy,syz,szx)). Dict sırası dosyadaki sıraya
    göre korunur (Python 3.7+) — bu, mesh'in kanonik node sırasıyla aynıdır
    (CalculiX, .inp'teki *NODE sırasını aynen yansıtır).
    """
    lines = frd_path.read_text(encoding="utf-8", errors="replace").splitlines()

    node_coords: dict[int, tuple[float, ...]] = {}
    displacement: dict[int, tuple[float, ...]] = {}
    # STRESS, CalculiX'te *EL FILE ile elemana özgü (integration point'ten
    # node'a extrapole edilmiş) çıkar: aynı node ID, çevresindeki her
    # elemandan AYRI bir değerle birden fazla kez gelir. Node başına TEK
    # değer değil, gelen tüm değerlerin toplamı+sayacı tutulur; sonda
    # componentwise ortalama alınır (cgx/Abaqus'un yaptığı "nodal averaging").
    stress_sum: dict[int, list[float]] = {}
    stress_count: dict[int, int] = {}
    disp_increments: list[dict[int, tuple[float, ...]]] = []
    current_disp: dict[int, tuple[float, ...]] = {}

    in_node_block = False
    current_result_type: str | None = None

    def flush_disp() -> None:
        nonlocal current_disp, displacement
        if not current_disp:
            return
        disp_increments.append(current_disp)
        displacement = current_disp
        current_disp = {}

    for line in lines:
        stripped_start = line[:6] if len(line) >= 6 else line
        if stripped_start.strip() == "2C" or line.lstrip().startswith("2C "):
            in_node_block = True
            current_result_type = None
            continue
        if line.startswith(" -4"):
            # örn: " -4  DISP        4    1" / " -4  STRESS      6    1"
            if current_result_type == "DISP":
                flush_disp()
            rest = line[4:].split()
            current_result_type = rest[0] if rest else None
            in_node_block = False
            if current_result_type == "DISP":
                current_disp = {}
            continue
        if line.startswith(" -3"):
            if current_result_type == "DISP":
                flush_disp()
            in_node_block = False
            current_result_type = None
            continue
        if line.startswith(" -5"):
            continue  # component tanım satırı, veri değil

        if in_node_block:
            parsed = _frd_data_line(line)
            if parsed and len(parsed[1]) >= 3:
                nid, vals = parsed
                node_coords[nid] = (vals[0], vals[1], vals[2])
            continue

        if current_result_type == "DISP":
            parsed = _frd_data_line(line)
            if parsed and len(parsed[1]) >= 3:
                nid, vals = parsed
                current_disp[nid] = (vals[0], vals[1], vals[2])
        elif current_result_type == "STRESS":
            parsed = _frd_data_line(line)
            if parsed and len(parsed[1]) >= 6:
                nid, vals = parsed
                acc = stress_sum.setdefault(nid, [0.0] * 6)
                for i in range(6):
                    acc[i] += vals[i]
                stress_count[nid] = stress_count.get(nid, 0) + 1

    if current_result_type == "DISP":
        flush_disp()

    stress: dict[int, tuple[float, ...]] = {
        nid: tuple(v / stress_count[nid] for v in acc) for nid, acc in stress_sum.items()
    }

    return {
        "node_coords": node_coords,
        "displacement": displacement,
        "disp_increments": disp_increments,
        "stress": stress,
    }


def _von_mises_stress(
    sxx: float, syy: float, szz: float, sxy: float, syz: float, szx: float
) -> float:
    """Standart von Mises eşdeğer gerilme formülü (gerilme tensöründen)."""
    return math.sqrt(
        0.5
        * (
            (sxx - syy) ** 2
            + (syy - szz) ** 2
            + (szz - sxx) ** 2
            + 6 * (sxy**2 + syz**2 + szx**2)
        )
    )


def _vendor_ccx_candidates() -> list[Path]:
    vendor = Path(__file__).resolve().parent.parent.parent / "vendor" / "ccx"
    return [
        vendor / "ccx.exe",
        vendor / "ccx_static.exe",
        vendor / "ccx",
    ]


def _ccx_executable() -> str | None:
    env = os.environ.get("CCX_PATH")
    if env:
        env_path = Path(env)
        if env_path.exists():
            return str(env_path)
    for name in ("ccx", "ccx.exe", "ccx_static", "ccx_static.exe"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in _vendor_ccx_candidates():
        if candidate.exists():
            return str(candidate)
    return None


def _ccx_run_env(ccx: str) -> dict[str, str]:
    """conda-forge Windows ccx: libgfortran DLL'leri mingw-w64/bin'de."""
    env = os.environ.copy()
    exe = Path(ccx).resolve()
    extras: list[str] = [str(exe.parent)]
    mingw = exe.parent.parent / "mingw-w64" / "bin"
    if mingw.is_dir():
        extras.append(str(mingw))
    prefix = exe.parent.parent.parent
    if (prefix / "conda-meta").is_dir():
        extras.append(str(prefix))
    env["PATH"] = os.pathsep.join(extras + [env.get("PATH", "")])
    return env


def _sanitize_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:64] or "MAT"


class CalculiXAdapter(SolverAdapter):
    def build_input(self, params: dict[str, Any]) -> InputArtifact:
        """params anahtarları:
        - mesh_path: Path
        - dimension: 2|3
        - output_dir: Path
        - job_name: str
        - materials: list[{name, density, youngs_modulus, poisson_ratio, part_id}]
        - shell_thickness: float (dim=2)
        - bcs: list[dict]  fixed/cload/pressure/displacement/gravity/bearing
        - analysis_type: "static" (varsayılan) | "modal"
        - n_modes: int (modal; varsayılan 10)
        - freq_min / freq_max: isteğe bağlı Hz aralığı (modal)
        """
        mesh_path = Path(params["mesh_path"])
        if not mesh_path.exists():
            raise SolverError(f"Mesh yok: {mesh_path}")

        dimension = int(params["dimension"])
        output_dir = Path(params["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        job_name = params.get("job_name", "job")
        inp_path = output_dir / f"{job_name}.inp"

        materials = params.get("materials") or []
        shell_thickness = float(params.get("shell_thickness", 1.0))
        bcs = params.get("bcs") or []
        analysis_type = str(params.get("analysis_type") or "static").lower()

        mesh_block, nsets, elsets, face_weights = _mesh_to_inp_blocks(
            mesh_path, dimension, materials, shell_thickness
        )
        mat_block = _materials_inp_block(materials, dimension, shell_thickness)
        # model_bc_block: *BOUNDARY/*TRANSFORM (STEP DIŞINDA kalabilir).
        # step_bc_block: *CLOAD/*DLOAD (SADECE STEP İÇİNDE geçerli — gerçek
        # bir çalıştırmada dışarıda kalınca CalculiX "*CLOAD should only be
        # used within a STEP" hatasıyla durduğu doğrulandı).
        model_bc_block, step_bc_block = _bcs_inp_block(
            bcs, nsets, elsets, dimension, face_weights
        )
        if analysis_type == "modal":
            # Modal'da yükler (*CLOAD/*DLOAD) yazılmaz — özdeğer problemi
            # mesnet + kütle/rijitlik ister, kuvvet değil.
            step_block = _frequency_step_block(
                n_modes=params.get("n_modes", 10),
                freq_min=params.get("freq_min"),
                freq_max=params.get("freq_max"),
                dimension=dimension,
            )
        elif analysis_type == "static":
            step_block = _static_step_block(
                step_bc_block,
                dimension,
                nlgeom=bool(params.get("nlgeom")),
                n_increments=int(params.get("n_increments") or 20),
            )
        else:
            raise SolverError(
                f"Bilinmeyen analysis_type={analysis_type!r} (static|modal)."
            )

        inp_path.write_text(
            mesh_block + mat_block + model_bc_block + step_block,
            encoding="utf-8",
        )
        logger.info("CalculiX .inp yazıldı: %s", inp_path)

        # Surrogate eğitim GİRDİLERİ burada yazılır: sınır koşulu -> düğüm
        # eşlemesi (`nsets`) yalnız bu noktada elde. Çözüm sonrası yeniden
        # hesaplamak hem yavaş olurdu hem de iki yol arasında sessiz
        # tutarsızlık riski taşırdı.
        try:
            from app.dataset import training_data as _td

            _coords = _read_inp_nodes(inp_path)
            _X = _td.build_node_inputs(
                _coords,
                bcs,
                nsets,
                materials,
                dimension,
                shell_thickness,
                _resolve_bc_node_ids,
            )
            _td.write_inputs(
                inp_path.with_suffix(".inputs.npz"), _X, None
            )
        except Exception as exc:  # noqa: BLE001 — veri seti üretimi çözümü bozmasın
            logger.warning("Eğitim girdileri yazılamadı: %s", exc)

        return InputArtifact(path=inp_path, kind="file")

    def submit(self, artifact: InputArtifact) -> JobHandle:
        ccx = _ccx_executable()
        if ccx is None:
            raise SolverError(
                "CalculiX (ccx) bulunamadı. CCX_PATH ayarlayın veya PATH'e ekleyin. "
                f".inp hazır: {artifact.path}"
            )

        work_dir = artifact.path.parent
        job_name = artifact.path.stem
        job_id = str(uuid.uuid4())
        log_path = work_dir / f"{job_name}.ccx.log"

        try:
            proc = subprocess.run(
                [ccx, job_name],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
                env=_ccx_run_env(ccx),
            )
        except subprocess.TimeoutExpired as exc:
            raise SolverError("CalculiX zaman aşımı (600s).") from exc

        log_path.write_text(
            (proc.stdout or "") + "\n" + (proc.stderr or ""),
            encoding="utf-8",
        )
        handle = JobHandle(job_id=job_id, work_dir=work_dir, artifact=artifact)
        handle._exit_code = proc.returncode  # type: ignore[attr-defined]
        handle._log_path = log_path  # type: ignore[attr-defined]
        if proc.returncode != 0:
            raise SolverError(
                f"CalculiX hata (exit={proc.returncode}). Log: {log_path}"
            )
        return handle

    def poll_status(self, job: JobHandle) -> JobStatus:
        exit_code = getattr(job, "_exit_code", None)
        if exit_code is None:
            frd = job.work_dir / f"{job.artifact.path.stem}.frd"
            if frd.exists():
                return JobStatus(state="done", exit_code=0)
            return JobStatus(state="pending")
        if exit_code == 0:
            return JobStatus(state="done", exit_code=0)
        return JobStatus(state="failed", exit_code=exit_code, message="ccx failed")

    def parse_results(self, job: JobHandle) -> ResultSet:
        frd = job.work_dir / f"{job.artifact.path.stem}.frd"
        if not frd.exists():
            return ResultSet(raw_result_path=None, scalars={"frd_exists": 0.0})

        try:
            parsed = _parse_frd(frd)
        except Exception as exc:  # noqa: BLE001 — parse hatası çözümü bozmasın
            logger.warning("FRD parse edilemedi: %s", exc)
            return ResultSet(
                scalars={"frd_bytes": float(frd.stat().st_size)},
                raw_result_path=frd,
            )

        node_coords = parsed["node_coords"]
        displacement = parsed["displacement"]
        stress = parsed["stress"]

        # KABUK GENİŞLETMESİNİ GERİ KATLA.
        # CalculiX kabuk elemanlarını 3B hacme genişletir; .frd düğüm sayısı
        # mesh'in iki katı olur ve arayüz hizalayamadığı için düzgün yüzey
        # konturu yerine nokta bulutuna düşer. Aşağıdaki adım üst/alt yüzey
        # çiftlerini orta yüzeye katlar (von Mises: maksimum = yüzey
        # gerilmesi; deplasman: ortalama). 3D solid'de genişletme olmadığı
        # için fonksiyon None döner ve hiçbir şey değişmez.
        _mesh_nodes = _read_inp_nodes(job.artifact.path)
        _collapsed = _collapse_shell_expansion(
            node_coords, displacement, stress, _mesh_nodes
        )
        _forced_order: list[int] | None = None
        _forced_nodes: list[list[float]] | None = None
        if _collapsed is not None:
            _forced_order, _forced_nodes, displacement, stress = _collapsed
            logger.info(
                "Kabuk genişletmesi katlandı: %d -> %d düğüm",
                len(node_coords),
                len(_forced_order),
            )

        # Dosyadaki (2C bloğundaki) node sırası = mesh'in kanonik sırası —
        # aynı sıralama frontend'in mesh önizlemesindeki `nodes[]` dizisiyle
        # birebir eşleşir (ikisi de aynı Gmsh `getNodes()` çağrısından gelir).
        node_order = (
            _forced_order if _forced_order is not None else list(node_coords.keys())
        )

        nodes_array = (
            _forced_nodes
            if _forced_nodes is not None
            else [list(node_coords[nid]) for nid in node_order]
        )

        disp_mag: dict[int, float] = {}
        for nid, (dx, dy, dz) in displacement.items():
            disp_mag[nid] = math.sqrt(dx * dx + dy * dy + dz * dz)

        von_mises: dict[int, float] = {}
        for nid, (sxx, syy, szz, sxy, syz, szx) in stress.items():
            von_mises[nid] = _von_mises_stress(sxx, syy, szz, sxy, syz, szx)

        von_mises_array = [von_mises.get(nid, 0.0) for nid in node_order]

        dat_path = job.work_dir / f"{job.artifact.path.stem}.dat"
        frequencies = _parse_dat_frequencies(dat_path)
        increments = parsed.get("disp_increments") or (
            [displacement] if displacement else []
        )
        modes: list[dict[str, Any]] = []
        for i, inc in enumerate(increments):
            vecs = [list(inc.get(nid, (0.0, 0.0, 0.0))) for nid in node_order]
            mags = [math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) for v in vecs]
            modes.append(
                {
                    "index": i + 1,
                    "frequency_hz": frequencies[i] if i < len(frequencies) else None,
                    "displacement_vectors": vecs,
                    "displacement_magnitude": mags,
                    "max_displacement": max(mags, default=0.0),
                }
            )

        # Varsayılan görüntü: ilk increment (modal'da 1. mod).
        if modes:
            disp_mag_array = modes[0]["displacement_magnitude"]
            disp_vector_array = modes[0]["displacement_vectors"]
            max_disp = float(modes[0]["max_displacement"])
        else:
            disp_mag_array = [disp_mag.get(nid, 0.0) for nid in node_order]
            disp_vector_array = [
                list(displacement.get(nid, (0.0, 0.0, 0.0))) for nid in node_order
            ]
            max_disp = max(disp_mag_array, default=0.0)
        max_vm = max(von_mises_array, default=0.0)
        # Kritik node: maksimum von Mises'e sahip düğümün gerçek CalculiX
        # node ID'si (frontend'de "CRITICAL NODE: #8421" gibi göstermek
        # için — index değil, gerçek node numarası).
        critical_node_id: int | None = None
        if von_mises:
            critical_node_id = max(von_mises, key=lambda nid: von_mises[nid])

        results_preview_path = job.work_dir / f"{job.artifact.path.stem}.results.json"
        results_preview_path.write_text(
            json.dumps(
                {
                    "node_ids": node_order,
                    "nodes": nodes_array,
                    "displacement_magnitude": disp_mag_array,
                    "displacement_vectors": disp_vector_array,
                    "von_mises": von_mises_array,
                    "max_displacement": max_disp,
                    "max_von_mises": max_vm,
                    "critical_node_id": critical_node_id,
                    "modes": modes,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        # Eğitim örneğini tamamla (girdiler + çıktılar) ve `.frd`'yi arşivle.
        #
        # MODAL VE STATİK AYRI ŞEMA KULLANIR. Modal `.frd`'de gerilme bloğu
        # yoktur (`*FREQUENCY` adımı yalnız U yazar) ve `displacement` son
        # artışı, yani SON MODUN ŞEKLİNİ tutar. Statik şemaya sığdırılırsa
        # "sıfır gerilmeli statik çözüm" gibi görünen, deplasman alanı
        # aslında bir mod şekli olan anlamsız bir örnek çıkar — hiçbir yerde
        # hata vermeden. Bu yüzden modal kendi şemasına yazılır: mod başına
        # normalize edilmiş şekil + frekans.
        _is_modal = bool(frequencies) or len(increments) > 1
        try:
            from app.dataset import training_data as _td

            if _is_modal:
                # Modal örnek: mod başına şekil + frekans. Statik şemaya
                # sığmaz çünkü modal `.frd`'de gerilme yoktur ve tek bir
                # deplasman alanı değil, mod başına bir alan vardır.
                _td.write_modal_sample(
                    job.artifact.path.with_suffix(".inputs.npz"),
                    job.work_dir / f"{job.artifact.path.stem}.train.npz",
                    node_order,
                    modes,
                )
            else:
                _td.write_training_sample(
                    job.artifact.path.with_suffix(".inputs.npz"),
                    job.work_dir / f"{job.artifact.path.stem}.train.npz",
                    node_order,
                    disp_vector_array,
                    von_mises_array,
                )
            # `.frd` arşivlemesi modal için de geçerli — ham veri saklanır,
            # şema netleşince yeniden çözmeye gerek kalmaz.
            _gz = _td.gzip_frd(frd)
            if _gz is not None:
                # gzip orijinali SİLER. Aşağıda `frd.stat()` okunduğu ve
                # `raw_result_path` veritabanına yazıldığı için referansın
                # yeni dosyaya taşınması şart — aksi halde çözüm biter ama
                # sonuç kaydı var olmayan bir yolu gösterir.
                frd = _gz
        except Exception as exc:  # noqa: BLE001
            logger.warning("Eğitim örneği yazılamadı: %s", exc)

        logger.info(
            "FRD parse edildi: %s, node_sayisi=%d, max_disp=%.6g, max_von_mises=%.6g",
            frd,
            len(node_order),
            max_disp,
            max_vm,
        )

        freq_scalars = {
            f"freq_{i}": f_hz for i, f_hz in enumerate(frequencies, start=1)
        }
        if frequencies:
            freq_scalars["n_frequencies"] = float(len(frequencies))
            freq_scalars["freq_min"] = frequencies[0]
            freq_scalars["freq_max"] = frequencies[-1]

        return ResultSet(
            scalars={
                # NOT: gzip'lendikten sonra bu SIKIŞTIRILMIŞ boyuttur.
                # Ham boyut için `node_count` ile birlikte değerlendirin.
                "frd_bytes": float(frd.stat().st_size) if frd.is_file() else 0.0,
                "node_count": float(len(node_order)),
                "max_displacement": max_disp,
                "max_von_mises": max_vm,
                **(
                    {"critical_node_id": float(critical_node_id)}
                    if critical_node_id is not None
                    else {}
                ),
                **freq_scalars,
            },
            curves={"frequencies": frequencies} if frequencies else {},
            raw_result_path=frd,
            results_preview_path=results_preview_path,
        )


def _parse_dat_frequencies(dat_path: Path) -> list[float]:
    """CalculiX .dat içinden doğal frekansları (cycles/time = Hz) okur."""
    if not dat_path.exists():
        return []
    text = dat_path.read_text(encoding="utf-8", errors="replace")
    found = [
        float(m.group(1))
        for m in re.finditer(
            r"FREQUENCY\s*\(\s*CYCLES/TIME\s*\)\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?)",
            text,
            flags=re.IGNORECASE,
        )
    ]
    if found:
        return found
    rows: list[float] = []
    in_table = False
    for line in text.splitlines():
        upper = line.upper()
        if "E I G E N V A L U E" in upper or (
            "MODE NO" in upper and "EIGENVALUE" in upper
        ):
            in_table = True
            continue
        if in_table and (
            "P A R T I C I P A T I O N" in upper or "PARTICIPATION FACTOR" in upper
        ):
            break
        if not in_table:
            continue
        parts = line.split()
        # MODE  EIGENVALUE  ω(rad)  f(cycles/time)  imag
        if len(parts) < 4:
            continue
        try:
            mode_no = int(float(parts[0]))
            freq_hz = float(parts[3] if len(parts) >= 4 else parts[-1])
        except ValueError:
            continue
        if mode_no >= 1:
            rows.append(freq_hz)
    return rows


def _mesh_to_inp_blocks(
    mesh_path: Path,
    dimension: int,
    materials: list[dict[str, Any]],
    shell_thickness: float,
) -> tuple[
    str,
    dict[str, list[int]],
    dict[str, list[int]],
    dict[int, dict[int, float]],
]:
    """Gmsh mesh'ten *NODE / *ELEMENT / *NSET / *ELSET blokları.

    Dördüncü dönüş: yüzey tag -> {düğüm: ağırlık}. Yüzey yükünü tutarlı
    dağıtmak için; eşit bölme kuadratik elemanlarda yanlış sonuç veriyor.
    """
    _gmsh_lock.acquire()
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        tag_to_idx = {int(t): i + 1 for i, t in enumerate(node_tags)}  # 1-based inp
        # Yüzey üçgeni alanı için düğüm koordinatları (1-based indekse göre).
        coords_by_idx: dict[int, tuple[float, float, float]] = {
            i + 1: (float(coords[3 * i]), float(coords[3 * i + 1]), float(coords[3 * i + 2]))
            for i in range(len(node_tags))
        }
        # Yüzey tag -> {düğüm indeksi: ağırlık}. Yüzey yükünü tutarlı
        # dağıtmak için; eşit bölme kuadratik elemanlarda yanlış.
        face_weights: dict[int, dict[int, float]] = {}
        lines: list[str] = ["*HEADING", "CAE platform CalculiX job", "*NODE"]
        for i, tag in enumerate(node_tags):
            nid = i + 1
            x, y, z = coords[3 * i : 3 * i + 3]
            lines.append(f"{nid}, {x:.8g}, {y:.8g}, {z:.8g}")

        nsets: dict[str, list[int]] = {}
        elsets: dict[str, list[int]] = {}
        elem_id = 1

        type_map = _GMSH_TO_CCX_2D if dimension == 2 else _GMSH_TO_CCX_3D
        elem_dim = dimension

        # Volume/yüzey bazlı ELSET: part_id ↔ entity sırası
        entities = gmsh.model.getEntities(elem_dim)
        if not entities:
            # Tüm elemanlar tek set
            entities = [(-1, -1)]

        part_materials = {int(m["part_id"]): m for m in materials}

        if entities == [(-1, -1)]:
            etypes, etags_list, enodes_list = gmsh.model.mesh.getElements(dim=elem_dim)
            all_eids: list[int] = []
            for etype, etags, enodes in zip(etypes, etags_list, enodes_list):
                ccx_type = type_map.get(int(etype))
                if not ccx_type:
                    continue
                n_per = len(enodes) // max(len(etags), 1) if len(etags) else 0
                lines.append(f"*ELEMENT, TYPE={ccx_type}, ELSET=PART_0")
                for ei, _etag in enumerate(etags):
                    conn = [
                        tag_to_idx[int(enodes[ei * n_per + k])]
                        for k in range(n_per)
                    ]
                    conn = _reorder_connectivity(conn, int(etype))
                    lines.append(f"{elem_id}, " + ", ".join(str(c) for c in conn))
                    all_eids.append(elem_id)
                    elem_id += 1
            elsets["PART_0"] = all_eids
        else:
            # 2D: PART_n = kenar paylaşan kabuk (preview triangle_to_part ile aynı).
            # 3D: PART_n = volume sırası. FACE_EL_* her yüzey için ayrı kalır (DLOAD).
            face_to_part: dict[int, int] = {}
            # köşe kümesi -> (eleman id, yerel yüz no). 3B katıda yüzey
            # yükünü *DSLOAD ile yazabilmek için gerekli.

            if elem_dim == 2:
                from app.mesh.gmsh_adapter import _surface_parts_by_coincident_nodes

                face_to_part = _surface_parts_by_coincident_nodes()

            for entity_index, (edim, etag) in enumerate(entities):
                part_id = (
                    face_to_part.get(etag, 0) if elem_dim == 2 else entity_index
                )
                etypes, etags_list, enodes_list = gmsh.model.mesh.getElements(
                    dim=edim, tag=etag
                )
                elset = f"PART_{part_id}"
                part_eids: list[int] = []
                for etype, etags, enodes in zip(etypes, etags_list, enodes_list):
                    ccx_type = type_map.get(int(etype))
                    if not ccx_type:
                        continue
                    n_per = len(enodes) // max(len(etags), 1) if len(etags) else 0
                    if len(etags) == 0:
                        continue
                    lines.append(f"*ELEMENT, TYPE={ccx_type}, ELSET={elset}")
                    for ei, _ in enumerate(etags):
                        conn = [
                            tag_to_idx[int(enodes[ei * n_per + k])]
                            for k in range(n_per)
                        ]
                        conn = _reorder_connectivity(conn, int(etype))
                        lines.append(f"{elem_id}, " + ", ".join(str(c) for c in conn))
                        part_eids.append(elem_id)
                        elem_id += 1
                elsets.setdefault(elset, []).extend(part_eids)
                if elem_dim == 2:
                    # Shell yüzey eleman seti → *DLOAD P için
                    elsets[f"FACE_EL_{etag}"] = list(part_eids)

                # Yüzey düğüm setleri (BC için): bu volume'un sınır yüzleri
                if elem_dim == 3:
                    for bdim, btag in gmsh.model.getBoundary(
                        [(edim, etag)], oriented=False, recursive=False
                    ):
                        if bdim != 2:
                            continue
                        nset = f"FACE_{btag}"
                        if nset in nsets:
                            continue
                        nt, _, _ = gmsh.model.mesh.getNodes(2, btag)
                        nsets[nset] = [tag_to_idx[int(t)] for t in nt if int(t) in tag_to_idx]
                        # Yüzey yükü için: bu sınır yüzeyinin üçgenlerini
                        # ana katı elemanla eşle. gmsh sınır yüzeyini
                        # meshlememiş olabilir (2B eleman üretilmemiş) —
                        # o durumda liste boş kalır ve yük eski yoldan
                        # (düğümlere bölünmüş CLOAD) uygulanır.
                        # Yüzey yükünün TUTARLI düğüm ağırlıkları.
                        # tri6'da düzgün yayılı yük için: köşeler 0,
                        # kenar-ortaları A/3. tri3'te üçü de A/3.
                        # Bu ağırlıklar yön bağımsızdır; teğet yükte de
                        # geçerli (bkz. _bcs_inp_block cload dalı).
                        try:
                            s_types, _s_tags, s_nodes = gmsh.model.mesh.getElements(
                                dim=2, tag=btag
                            )
                        except Exception:  # noqa: BLE001
                            s_types, s_nodes = [], []
                        w_map: dict[int, float] = {}
                        for s_type, s_conn in zip(s_types, s_nodes):
                            per = _SURF_NODES_PER.get(int(s_type))
                            if per not in (3, 6):
                                continue  # quad yüzler: şimdilik eşit bölme
                            total = len(s_conn) // per
                            for si in range(total):
                                base = si * per
                                tags = [int(s_conn[base + k]) for k in range(per)]
                                if any(t not in tag_to_idx for t in tags):
                                    continue
                                idxs = [tag_to_idx[t] for t in tags]
                                area = _tri_area(
                                    coords_by_idx[idxs[0]],
                                    coords_by_idx[idxs[1]],
                                    coords_by_idx[idxs[2]],
                                )
                                if area <= 0:
                                    continue
                                if per == 6:
                                    # Kuadratik: yalnız kenar-orta düğümler
                                    for k in (3, 4, 5):
                                        w_map[idxs[k]] = (
                                            w_map.get(idxs[k], 0.0) + area / 3.0
                                        )
                                else:
                                    for k in (0, 1, 2):
                                        w_map[idxs[k]] = (
                                            w_map.get(idxs[k], 0.0) + area / 3.0
                                        )
                        if w_map:
                            face_weights[int(btag)] = w_map
                else:
                    # 2D: yüzey kendisi
                    nset = f"FACE_{etag}"
                    nt, _, _ = gmsh.model.mesh.getNodes(2, etag)
                    nsets[nset] = [tag_to_idx[int(t)] for t in nt if int(t) in tag_to_idx]

        # Kenar NSET (displacement/sliding)
        for _d, ctag in gmsh.model.getEntities(1):
            nset = f"EDGE_{ctag}"
            nt, _, _ = gmsh.model.mesh.getNodes(1, ctag)
            ids = [tag_to_idx[int(t)] for t in nt if int(t) in tag_to_idx]
            if ids:
                nsets[nset] = ids

        for _d, ptag in gmsh.model.getEntities(0):
            nset = f"POINT_{ptag}"
            nt, _, _ = gmsh.model.mesh.getNodes(0, ptag)
            ids = [tag_to_idx[int(t)] for t in nt if int(t) in tag_to_idx]
            if ids:
                nsets[nset] = ids

        for nset, ids in nsets.items():
            if not ids:
                continue
            lines.append(f"*NSET, NSET={nset}")
            lines.extend(_chunk_csv(ids))

        # FACE_EL_* (PART_* dışında) — DLOAD için ek ELSET
        for es_name, eids in elsets.items():
            if not es_name.startswith("FACE_EL_") or not eids:
                continue
            lines.append(f"*ELSET, ELSET={es_name}")
            lines.extend(_chunk_csv(eids))

        # Kullanılmayan part_materials uyarısı yok — section'lar materials bloğunda
        _ = part_materials
        _ = shell_thickness
        return "\n".join(lines) + "\n", nsets, elsets, face_weights
    finally:
        gmsh.finalize()
        _gmsh_lock.release()


def _materials_inp_block(
    materials: list[dict[str, Any]], dimension: int, shell_thickness: float
) -> str:
    lines: list[str] = []
    if not materials:
        # Varsayılan çelik
        materials = [
            {
                "part_id": 0,
                "name": "DEFAULT_STEEL",
                "youngs_modulus": 210e9,
                "poisson_ratio": 0.3,
                "density": 7850.0,
            }
        ]

    seen_mat: set[str] = set()
    for m in materials:
        mname = _sanitize_name(str(m["name"]))
        if mname not in seen_mat:
            # KRİTİK BİRİM DÖNÜŞÜMÜ: malzeme kütüphanesi SI birimlerinde
            # saklıyor (Young modülü Pa, yoğunluk kg/m³ — bkz.
            # ARCHITECTURE.md#malzeme-kütüphanesi). Ama geometri mm, yükler
            # N cinsinden — CalculiX tutarlı bir birim sistemi gerektiriyor
            # (mm/N/MPa/tonne). Dönüştürmeden E'yi Pa olarak göndermek,
            # malzemeyi 1.000.000 kat daha sert gösteriyordu — gerçek bir
            # ankastre kiriş testinde elle hesapla (25.5mm) karşılaştırılıp
            # kanıtlandı: dönüşümsüz sonuç 0.0000226mm çıkıyordu (beklenenin
            # ~1 milyonda biri).
            #   E: Pa -> MPa (1 MPa = 1e6 Pa)
            #   yoğunluk: kg/m³ -> tonne/mm³ (1 kg/m³ = 1e-12 tonne/mm³)
            E_pa = float(m["youngs_modulus"])
            nu = float(m["poisson_ratio"])
            rho_kg_m3 = float(m["density"])
            E = E_pa / 1e6
            rho = rho_kg_m3 * 1e-12
            lines.append(f"*MATERIAL, NAME={mname}")
            lines.append("*ELASTIC")
            lines.append(f"{E:.6e}, {nu:.6g}")
            lines.append("*DENSITY")
            lines.append(f"{rho:.6e}")
            seen_mat.add(mname)
        elset = f"PART_{int(m['part_id'])}"
        if dimension == 2:
            lines.append(
                f"*SHELL SECTION, ELSET={elset}, MATERIAL={mname}"
            )
            lines.append(f"{shell_thickness:.6g}")
        else:
            lines.append(
                f"*SOLID SECTION, ELSET={elset}, MATERIAL={mname}"
            )
    return "\n".join(lines) + "\n"


def _resolve_bc_node_ids(
    bc: dict[str, Any], nsets: dict[str, list[int]]
) -> list[int]:
    """Bir BC'nin hedeflediği MESH DÜĞÜM numaralarını döndürür.

    İki ayrı kaynak vardır ve karıştırılmamalıdır:

    * `node_ids` — CAD VERTEX (köşe) id'leri. Bunlar geometrinin kalıcı
      tutamaklarıdır: mesh yeniden üretilince değişmezler. `POINT_{id}`
      nset'i üzerinden gerçek mesh düğümlerine çevrilirler.
    * `mesh_node_ids` — doğrudan MESH DÜĞÜM numaraları. Kullanıcı mesh
      üzerinde bir düğüme tıklayıp seçtiğinde kullanılır. Bu numaralar o
      mesh'e özgüdür; element size değişip mesh yeniden üretilirse
      ANLAMINI YİTİRİR.

    KRİTİK BUG DÜZELTMESİ: eskiden `node_ids` doğrudan mesh düğüm numarası
    olarak yazılıyordu (`f"{int(nid)}, 1, 3"`). Frontend ise Nokta modunda
    CAD vertex id gönderiyordu — yani CAD köşe #7 seçilince alakasız mesh
    düğümü #7 sabitleniyordu. Aynı dosyadaki `rigid_body` bunu zaten DOĞRU
    yapıyordu (`nsets.get(f"POINT_{raw_ref}")`), yani kod kendi içinde
    tutarsızdı — bu bir tasarım tercihi değil, hataydı.

    Geriye dönük uyum: `POINT_{id}` nset'i bulunamazsa (ör. mesh o vertex'e
    düğüm düşürmemişse) ham id'ye düşülür — eski davranış korunur, ama
    yalnızca son çare olarak.
    """
    resolved: list[int] = []
    for nid in bc.get("node_ids") or []:
        point_set = nsets.get(f"POINT_{int(nid)}") or []
        if point_set:
            resolved.extend(point_set)
        else:
            resolved.append(int(nid))
    for nid in bc.get("mesh_node_ids") or []:
        resolved.append(int(nid))
    # Sıra korunarak tekilleştir
    return list(dict.fromkeys(resolved))



def _tri_area(p0: tuple[float, float, float],
              p1: tuple[float, float, float],
              p2: tuple[float, float, float]) -> float:
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def _consistent_face_weights(
    bc: dict[str, Any],
    face_weights: dict[int, dict[int, float]] | None,
) -> dict[int, float]:
    """BC'nin dokunduğu yüzeylerin tutarlı düğüm ağırlıklarını toplar.

    Birden çok yüzey seçiliyse ağırlıklar toplanır — ortak kenardaki
    düğüm iki yüzeyden de pay alır, doğrusu bu.
    """
    if not face_weights:
        return {}
    out: dict[int, float] = {}
    for fid in bc.get("face_ids") or []:
        for nid, w in (face_weights.get(int(fid)) or {}).items():
            out[nid] = out.get(nid, 0.0) + w
    return out


def _bcs_inp_block(
    bcs: list[dict[str, Any]],
    nsets: dict[str, list[int]],
    elsets: dict[str, list[int]],
    dimension: int,
    face_weights: dict[int, dict[int, float]] | None = None,
) -> tuple[str, str]:
    """BC kartlarını üretir — döndürür: (model_seviyesi, step_seviyesi).

    CalculiX/Abaqus format kuralı: `*BOUNDARY`/`*TRANSFORM` gibi kalıcı model
    tanımı kartları `*STEP`'in DIŞINDA kalabilir, ama `*CLOAD`/`*DLOAD` gibi
    yük kartları SADECE `*STEP` İÇİNDE olabilir — gerçek bir çalıştırmada
    `*CLOAD` dışarıda kalınca CalculiX "*CLOAD should only be used within a
    STEP" hatasıyla durduğu doğrulandı. Bu yüzden ikisi ayrı listelerde
    tutulup, step-seviyesi olanlar çağıran tarafından `*STEP`/`*STATIC` ile
    `*NODE FILE` arasına yerleştiriliyor.
    """
    model_lines: list[str] = []
    step_lines: list[str] = []
    for bc in bcs:
        btype = str(bc.get("type", "")).lower()
        if btype == "fixed":
            # KRİTİK — SERBESTLİK DERECESİ ARALIĞI ELEMAN TİPİNE BAĞLI:
            #
            # 3D solid (C3D4/C3D10/C3D8): düğümde YALNIZ 3 öteleme DOF'u
            #   vardır, 1..3 doğru aralıktır.
            # 2D kabuk (S3/S4): düğümde 6 DOF vardır — 1..3 öteleme,
            #   4..6 DÖNME. Sadece 1..3'ü sabitlemek ankastre mesnedi
            #   TAM KISITLAMAZ: kısıtlanan düğümler bir doğru üzerindeyse
            #   (plakanın ankastre kenarı) kabuk o kenar etrafında serbestçe
            #   döner. Bu tam bir mekanizmadır — rijit cisim dönmesi.
            #
            # Gerçek bir testte doğrulandı: 50x10x500 midsurface kabukta
            # kenar düğümlerine "fixed" verilip 500N uygulanınca maksimum
            # deplasman 4.42e10 mm çıktı (aynı problem 3D solid'de 23.9 mm).
            # Eskiden `dimension` parametresi bu fonksiyona geçiliyor ama
            # `_ = dimension` ile ATILIYORDU.
            fixed_dofs = "1, 6" if dimension == 2 else "1, 3"
            for fid in bc.get("face_ids") or []:
                nset = f"FACE_{int(fid)}"
                if nset not in nsets or not nsets[nset]:
                    continue
                model_lines.append("*BOUNDARY")
                model_lines.append(f"{nset}, {fixed_dofs}")
            for eid in bc.get("edge_ids") or []:
                nset = f"EDGE_{int(eid)}"
                if nset not in nsets or not nsets[nset]:
                    continue
                model_lines.append("*BOUNDARY")
                model_lines.append(f"{nset}, {fixed_dofs}")
            for nid in _resolve_bc_node_ids(bc, nsets):
                model_lines.append("*BOUNDARY")
                model_lines.append(f"{nid}, {fixed_dofs}")
        elif btype == "cload":
            fx = float(bc.get("fx", 0.0))
            fy = float(bc.get("fy", 0.0))
            fz = float(bc.get("fz", 0.0))
            # Yük bir YÜZEYE uygulanıyorsa toplam kuvveti düğümlere EŞİT
            # bölmek yanlış. Kuadratik elemanlarda (C3D10 → yüzeyi tri6)
            # düzgün yayılı yükün TUTARLI düğüm kuvvetleri eşit değildir:
            # köşeler 0, kenar-ortaları A/3. Eşit bölmek yükleme yüzeyinde
            # sahte yerel salınım üretir.
            #
            # KONTROLLÜ A/B İLE ÖLÇÜLDÜ (delikli plaka H200 W100 t5 d20,
            # S235, 30 kN, aynı 5 mesh, tek fark yük dağıtımı):
            #
            #   es    eşit bölme   tutarlı ağırlık
            #   12    0.060882     0.059850
            #    7    0.060795     0.059905
            #    5    0.060623     0.059914
            #   3.6   0.065623     0.059905
            #   2.4   0.084794     0.059853
            #   yayılma  %39.9        %0.11
            #
            # σ iki kolda da aynı (187–192 MPa, ince meshler) çünkü tepe
            # gerilme delikte, yükleme yüzeyinden uzakta. Kirişte
            # görünmemişti: orada sehim 23 mm, salınım yanında önemsiz.
            #
            # Basınca (*DSLOAD) çevirmek genel çözüm DEĞİL: basınç yüzeye
            # daima diktir, ankastre kirişte ise uç yükü yüzeye TEĞET.
            # Tutarlı düğüm ağırlıkları yön bağımsızdır, o yüzden bu yol.
            node_ids = _resolve_bc_node_ids(bc, nsets)
            weights = _consistent_face_weights(bc, face_weights)
            # Tutarlı ağırlıkla yüklenen yüzeyler aşağıdaki eşit-bölme yüz
            # döngüsünde ATLANMALI. Atlanmadığında yük iki kez yazılıyordu —
            # ölçüldü: delikli plakada iki *CLOAD bloğu, her biri 30 000 N,
            # toplam 60 000 N; u_max ve σ tam iki katına çıktı (σ 187 → 384).
            weighted_faces = {
                int(fid)
                for fid in (bc.get("face_ids") or [])
                if face_weights and face_weights.get(int(fid))
            }
            if weights:
                total_w = sum(weights.values())
                if total_w > 0:
                    step_lines.append("*CLOAD")
                    for nid, w in sorted(weights.items()):
                        frac = w / total_w
                        if abs(fx) > 0:
                            step_lines.append(f"{nid}, 1, {fx * frac:.6g}")
                        if abs(fy) > 0:
                            step_lines.append(f"{nid}, 2, {fy * frac:.6g}")
                        if abs(fz) > 0:
                            step_lines.append(f"{nid}, 3, {fz * frac:.6g}")
            elif node_ids:
                # Kenar/nokta yükü ya da yüzey ağırlığı hesaplanamadı —
                # eşit bölme. Bu durumda yukarıdaki salınım riski var,
                # ama alternatifi yükü hiç uygulamamak olurdu.
                n = len(node_ids)
                step_lines.append("*CLOAD")
                for nid in node_ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{nid}, 1, {fx / n:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{nid}, 2, {fy / n:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{nid}, 3, {fz / n:.6g}")
            for fid in bc.get("face_ids") or []:
                if int(fid) in weighted_faces:
                    continue  # yukarıda tutarlı ağırlıkla yazıldı
                nset = f"FACE_{int(fid)}"
                ids = nsets.get(nset) or []
                if not ids:
                    continue
                n = len(ids)
                step_lines.append("*CLOAD")
                for nid in ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{nid}, 1, {fx / n:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{nid}, 2, {fy / n:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{nid}, 3, {fz / n:.6g}")
            for eid in bc.get("edge_ids") or []:
                nset = f"EDGE_{int(eid)}"
                ids = nsets.get(nset) or []
                if not ids:
                    continue
                n = len(ids)
                step_lines.append("*CLOAD")
                for nid in ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{nid}, 1, {fx / n:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{nid}, 2, {fy / n:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{nid}, 3, {fz / n:.6g}")
        elif btype == "pressure":
            mag = float(bc.get("magnitude", 0.0))
            if abs(mag) < 1e-30:
                continue
            for fid in bc.get("face_ids") or []:
                elset = f"FACE_EL_{int(fid)}"
                if elset in elsets and elsets[elset]:
                    step_lines.append("*DLOAD")
                    step_lines.append(f"{elset}, P, {mag:.6g}")
                    continue
                # 3D solid: yüzey ELSET yok → düğümlere dağıtılmış CLOAD
                nset = f"FACE_{int(fid)}"
                ids = nsets.get(nset) or []
                if not ids:
                    continue
                dx = float(bc.get("dx", 0.0))
                dy = float(bc.get("dy", 0.0))
                dz = float(bc.get("dz", -1.0))
                norm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                fx, fy, fz = mag * dx / norm, mag * dy / norm, mag * dz / norm
                n = len(ids)
                step_lines.append(f"** pressure face {fid} as distributed CLOAD (no FACE_EL)")
                step_lines.append("*CLOAD")
                for nid in ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{nid}, 1, {fx / n:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{nid}, 2, {fy / n:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{nid}, 3, {fz / n:.6g}")
        elif btype == "displacement":
            dofs = bc.get("dofs") or {"1": 0.0, "2": 0.0, "3": 0.0}
            targets: list[str] = []
            for eid in bc.get("edge_ids") or []:
                targets.append(f"EDGE_{int(eid)}")
            for fid in bc.get("face_ids") or []:
                targets.append(f"FACE_{int(fid)}")
            for nid in _resolve_bc_node_ids(bc, nsets):
                model_lines.append("*BOUNDARY")
                for dof, val in dofs.items():
                    model_lines.append(
                        f"{nid}, {int(dof)}, {int(dof)}, {float(val):.6g}"
                    )
            for nset in targets:
                if nset not in nsets:
                    continue
                model_lines.append("*BOUNDARY")
                for dof, val in dofs.items():
                    model_lines.append(f"{nset}, {int(dof)}, {int(dof)}, {float(val):.6g}")
        elif btype == "sliding":
            # Yerel eksen: normal = 1. DOF; teğet serbest. *TRANSFORM + *BOUNDARY
            normal = bc.get("normal") or [0.0, 0.0, 1.0]
            nx, ny, nz = float(normal[0]), float(normal[1]), float(normal[2])
            nlen = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx, ny, nz = nx / nlen, ny / nlen, nz / nlen
            # İkinci eksen: normal × dünya Z (veya X)
            if abs(nz) < 0.9:
                tx, ty, tz = -ny, nx, 0.0
            else:
                tx, ty, tz = 0.0, -nz, ny
            tlen = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
            tx, ty, tz = tx / tlen, ty / tlen, tz / tlen
            nsets_targets: list[str] = []
            for eid in bc.get("edge_ids") or []:
                nsets_targets.append(f"EDGE_{int(eid)}")
            for fid in bc.get("face_ids") or []:
                nsets_targets.append(f"FACE_{int(fid)}")
            for nset in nsets_targets:
                if nset not in nsets or not nsets[nset]:
                    continue
                model_lines.append(f"*TRANSFORM, NSET={nset}, TYPE=C")
                model_lines.append(
                    f"{nx:.6g}, {ny:.6g}, {nz:.6g}, {tx:.6g}, {ty:.6g}, {tz:.6g}"
                )
                model_lines.append("*BOUNDARY")
                # Local 1 (normal) sabit; 2-3 serbest (sliding)
                model_lines.append(f"{nset}, 1, 1")
        elif btype == "gravity":
            gx = float(bc.get("gx", 0.0))
            gy = float(bc.get("gy", 0.0))
            gz = float(bc.get("gz", -9810.0))
            mag = math.sqrt(gx * gx + gy * gy + gz * gz) or 1.0
            part_elsets = [
                name for name in elsets if name.startswith("PART_") and elsets[name]
            ]
            if not part_elsets:
                part_elsets = ["PART_0"]
            step_lines.append("*DLOAD")
            for pel in part_elsets:
                step_lines.append(
                    f"{pel}, GRAV, {mag:.6g}, {gx / mag:.6g}, {gy / mag:.6g}, {gz / mag:.6g}"
                )
        elif btype == "bearing":
            mag = float(bc.get("magnitude", 0.0))
            axis = bc.get("axis") or [0.0, 0.0, -1.0]
            ax, ay, az = float(axis[0]), float(axis[1]), float(axis[2])
            for fid in bc.get("face_ids") or []:
                nset = f"FACE_{int(fid)}"
                ids = nsets.get(nset) or []
                if len(ids) < 2 or abs(mag) < 1e-30:
                    continue
                weights = [
                    max(0.0, math.cos(math.pi * i / max(len(ids) - 1, 1)))
                    for i in range(len(ids))
                ]
                wsum = sum(weights) or 1.0
                step_lines.append(f"** bearing load face {fid}")
                step_lines.append("*CLOAD")
                for nid, w in zip(ids, weights):
                    f = mag * w / wsum
                    if abs(ax) > 0:
                        step_lines.append(f"{nid}, 1, {f * ax:.6g}")
                    if abs(ay) > 0:
                        step_lines.append(f"{nid}, 2, {f * ay:.6g}")
                    if abs(az) > 0:
                        step_lines.append(f"{nid}, 3, {f * az:.6g}")
        elif btype == "rigid_body":
            ref = bc.get("ref_node_id")
            if ref is None:
                model_lines.append("** rigid_body skipped: ref_node_id yok")
                continue
            raw_ref = int(ref)
            point_set = nsets.get(f"POINT_{raw_ref}") or []
            ref_id = point_set[0] if point_set else raw_ref
            slave: list[int] = []
            for fid in bc.get("face_ids") or []:
                slave.extend(nsets.get(f"FACE_{int(fid)}") or [])
            for eid in bc.get("edge_ids") or []:
                slave.extend(nsets.get(f"EDGE_{int(eid)}") or [])
            slave.extend(_resolve_bc_node_ids(bc, nsets))
            slave = [n for n in dict.fromkeys(slave) if n != ref_id]
            if not slave:
                continue
            nset = f"RB_{ref_id}"
            model_lines.append(f"*NSET, NSET={nset}")
            model_lines.extend(_chunk_csv(slave))
            model_lines.append(f"*RIGID BODY, NSET={nset}, REF NODE={ref_id}")
        else:
            model_lines.append(f"** unknown bc type: {btype}")

    model_block = ("\n".join(model_lines) + "\n") if model_lines else ""
    step_block = ("\n".join(step_lines) + "\n") if step_lines else ""
    return model_block, step_block


def _output_qualifier(dimension: int) -> str:
    """`*NODE FILE` / `*EL FILE` için çıktı niteleyicisi.

    KABUK (2D) İÇİN KRİTİK: CalculiX kabuk elemanlarını içeride 3B hacim
    elemanlarına GENİŞLETİR — her kabuk düğümü üst/alt yüzey için ikiye
    katlanır ve `.frd` varsayılan olarak bu genişletilmiş düğümleri yazar.
    Sonuç: `.frd` düğüm sayısı mesh önizlemesinin İKİ KATI olur, ikisi
    hizalanamaz ve arayüz düzgün yüzey konturu yerine nokta bulutuna
    düşer (gerçek bir ekran görüntüsünde "node node" görünen kaba
    küreler bu yüzdendi).

    `OUTPUT=2D` bunu kapatır: sonuçlar ORİJİNAL kabuk düğüm numaralarıyla
    yazılır. Böylece düğüm sayısı mesh ile birebir eşleşir ve düzgün
    (smooth) kontur çizilebilir. von Mises bir invaryant olduğu için
    kabuk yerel eksen dönüşümünden etkilenmez.

    3D solid'de genişletme yoktur; niteleyici yazılmaz.
    """
    # OUTPUT=2D DENENDİ VE GERİ ALINDI — gerilme yanlış oluyordu.
    #
    # OUTPUT=2D düğüm hizalamasını çözüyordu (sayılar mesh ile eşleşiyordu)
    # ama gerilmeyi kabuğun ORTA DÜZLEMİNDE veriyor, YÜZEYİNDE değil.
    # Eğilmede gerilme kalınlık boyunca lineerdir: yüzeyde ±sigma_max,
    # orta düzlemde SIFIR. Gerçek bir testte doğrulandı: 300 MPa olması
    # gereken kabuk gerilmesi 79.8 MPa'ya düştü (kalan kısım ankastre
    # köşedeki yerel etkiler + kayma), deplasman ise 23.6 mm'de kaldı
    # çünkü deplasman kalınlık boyunca değişmez.
    #
    # Bu yüzden genişletilmiş çıktı korunuyor; hizalama post-process'te
    # `_collapse_shell_expansion` ile çözülüyor: üst/alt yüzey çifti orta
    # yüzey düğümüne katlanır, von Mises için MAKSİMUM (yüzey gerilmesi,
    # tasarımda aranan bu), deplasman için ORTALAMA alınır.
    _ = dimension
    return ""


def _static_step_block(
    step_bc_lines: str = "",
    dimension: int = 3,
    nlgeom: bool = False,
    n_increments: int = 20,
) -> str:
    """Statik çözüm adımı. `nlgeom=True` ise büyük deformasyon.

    NEDEN GEREKLİ: Lineer (küçük deformasyon) çözüm, denge denklemlerini
    deforme OLMAMIŞ geometride kurar. u/L büyüdükçe bu varsayım bozulur;
    çözücü hata vermez, sessizce yanlış cevap verir. Korpus kapısı bu
    yüzden u/L > 0.10 olan run'ları eliyor (kirişte 23 run elendi).

    NLGEOM ile CalculiX denge denklemlerini deforme geometride kurar ve
    yükü artımlı uygular. Maliyeti: iterasyon gerektirir, lineer çözümden
    belirgin şekilde yavaştır — bu yüzden varsayılan KAPALI.

    `*STATIC` satırındaki dört alan: başlangıç artım, toplam adım süresi,
    min artım, max artım. NLGEOM'da artımlı yükleme şart; lineer çözümde
    tek artım yeterli olduğu için o satır sade bırakılıyor.
    """
    out = _output_qualifier(dimension)
    if nlgeom:
        inc = max(1, int(n_increments))
        first = 1.0 / inc
        head = (
            f"*STEP, NLGEOM, INC={max(100, inc * 5)}\n"
            f"*STATIC\n"
            f"{first:g}, 1.0, {first / 100:g}, {first:g}\n"
        )
    else:
        head = "*STEP\n*STATIC\n"
    return (
        f"{head}"
        f"{step_bc_lines}"
        f"*NODE FILE{out}\n"
        "U\n"
        f"*EL FILE{out}\n"
        "S\n"
        "*END STEP\n"
    )


def _frequency_step_block(
    n_modes: Any = 10,
    freq_min: Any = None,
    freq_max: Any = None,
    dimension: int = 3,
) -> str:
    """CalculiX Lanczos özdeğer adımı — `*FREQUENCY` (modal).

    STORAGE=YES: mod şekilleri .frd'ye yazılır. Yük kartı yoktur.
    """
    try:
        n = int(n_modes)
    except (TypeError, ValueError) as exc:
        raise SolverError("n_modes tam sayı olmalı.") from exc
    if n < 1 or n > 200:
        raise SolverError("n_modes 1 ile 200 arasında olmalı.")

    data_line = str(n)
    if freq_min is not None and freq_max is not None:
        try:
            lo = float(freq_min)
            hi = float(freq_max)
        except (TypeError, ValueError) as exc:
            raise SolverError("freq_min / freq_max sayı olmalı.") from exc
        if not (hi > lo >= 0):
            raise SolverError("freq_max, freq_min'den büyük olmalı (Hz).")
        data_line = f"{n}, {lo:.6g}, {hi:.6g}"

    # Kabukta OUTPUT=2D — statik adımdaki ile aynı gerekçe: mod şekilleri
    # de genişletilmiş düğümlerle yazılırsa mesh ile hizalanamaz.
    out = _output_qualifier(dimension)
    return (
        "*STEP\n"
        "*FREQUENCY, STORAGE=YES\n"
        f"{data_line}\n"
        f"*NODE FILE{out}\n"
        "U\n"
        "*END STEP\n"
    )


def _chunk_csv(ids: list[int], per_line: int = 10) -> list[str]:
    out: list[str] = []
    for i in range(0, len(ids), per_line):
        out.append(", ".join(str(x) for x in ids[i : i + per_line]))
    return out
