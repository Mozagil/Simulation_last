"""V-P1 — klasik laminat kabuk plaka (Faz 3.10): CLT vs CalculiX.

Kesit kartları uygulamanın `write_composite_section` yazıcısından gelir
(`*SHELL SECTION, COMPOSITE`); ağ, BC ve yük bu betikte düzenli S8R ızgarası
olarak yazılır (Gmsh / `/composite/solve` zinciri bu vakada yok). Malzeme
tipik T300/epoxy (`composite_materials` seed'i ile aynı; mill test değil).

Vakalar:
- a: [0/90]s şerit, kenarda Nx → εx, εy ↔ A⁻¹
- b: [30]₄ şerit, kenarda Nx → εx, εy, γxy ↔ A⁻¹ (A16 ≠ 0; açı işaret kuralı)
- c: [0/90]s kare plaka, dört kenar basit mesnetli (w = 0), düzgün basınç
     → merkez sehimi ↔ Navier serisi (kayma yok; a/h = 200)

Sonuç: ``uploads/reports/composite_validation_vp1.json`` ve ekrana tablo.
Değerler veridir; kabul ölçütü mühendisin.

Kullanım (backend klasöründen; ccx: CCX_PATH → PATH → vendor):
    .venv/Scripts/python.exe scripts/composite_validation_vp1.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.composite.layup import Ply, abd_matrix  # noqa: E402
from app.composite.reference import midplane_response, navier_deflection  # noqa: E402
from app.composite.section_writer import write_composite_section  # noqa: E402
from app.solvers.calculix import _ccx_executable, _ccx_run_env  # noqa: E402

T300 = {
    "name": "T300_epoxy",
    "e1": 135e9,
    "e2": 10e9,
    "e3": 10e9,
    "nu12": 0.3,
    "nu13": 0.3,
    "nu23": 0.45,
    "g12": 5.2e9,
    "g13": 5.2e9,
    "g23": 3.4e9,
    "density": 1600.0,
}
PLY_T_MM = 0.25


@dataclass(frozen=True)
class Case:
    key: str
    angles: tuple[float, ...]
    a_mm: float
    b_mm: float
    nx: int
    ny: int
    load: str  # "nx" (N/mm) | "pressure" (MPa)
    value: float


CASES = (
    Case("a", (0.0, 90.0, 90.0, 0.0), 200.0, 50.0, 20, 6, "nx", 10.0),
    Case("b", (30.0, 30.0, 30.0, 30.0), 200.0, 50.0, 20, 6, "nx", 10.0),
    Case("c", (0.0, 90.0, 90.0, 0.0), 200.0, 200.0, 20, 20, "pressure", 1e-4),
)


def _plies(angles: tuple[float, ...]) -> list[dict]:
    return [{**T300, "thickness_mm": PLY_T_MM, "angle_deg": ang} for ang in angles]


def clt_reference(case: Case) -> dict[str, float]:
    abd = abd_matrix(
        [
            Ply(T300["e1"], T300["e2"], T300["g12"], T300["nu12"], PLY_T_MM, ang)
            for ang in case.angles
        ]
    )
    if case.load == "nx":
        eps = midplane_response(abd, n=(case.value, 0.0, 0.0))["eps0"]
        return {"eps_x": eps[0], "eps_y": eps[1], "gamma_xy": eps[2]}
    return {"w_center_mm": navier_deflection(abd, case.a_mm, case.b_mm, case.value)}


class _Grid:
    """S8R düzenli ızgara: (2nx+1)×(2ny+1) düğüm, eleman içi merkez düğümü yok."""

    def __init__(self, case: Case) -> None:
        self.case = case
        self.ids: dict[tuple[int, int], int] = {}
        nid = 0
        for j in range(2 * case.ny + 1):
            for i in range(2 * case.nx + 1):
                if i % 2 and j % 2:
                    continue
                nid += 1
                self.ids[(i, j)] = nid

    def xy(self, i: int, j: int) -> tuple[float, float]:
        c = self.case
        return (c.a_mm * i / (2 * c.nx), c.b_mm * j / (2 * c.ny))

    def elements(self) -> list[list[int]]:
        out = []
        for ey in range(self.case.ny):
            for ex in range(self.case.nx):
                i, j = 2 * ex, 2 * ey
                g = self.ids
                out.append(
                    [
                        g[(i, j)], g[(i + 2, j)], g[(i + 2, j + 2)], g[(i, j + 2)],
                        g[(i + 1, j)], g[(i + 2, j + 1)], g[(i + 1, j + 2)], g[(i, j + 1)],
                    ]
                )
        return out


def build_deck(case: Case) -> tuple[str, dict[str, int]]:
    """CalculiX girdi destesi + ölçüm düğümleri {ad: düğüm id}."""
    g = _Grid(case)
    imax, jmax = 2 * case.nx, 2 * case.ny
    lines = ["*HEADING", f"V-P1{case.key} composite plate", "*NODE"]
    for (i, j), nid in g.ids.items():
        x, y = g.xy(i, j)
        lines.append(f"{nid}, {x:.6f}, {y:.6f}, 0.0")
    lines.append("*ELEMENT, TYPE=S8R, ELSET=PLATE")
    for eid, conn in enumerate(g.elements(), start=1):
        lines.append(f"{eid}, " + ", ".join(str(n) for n in conn))
    lines.append(
        write_composite_section(
            {"part_id": 0, "elset": "PLATE", "plies": _plies(case.angles)}
        ).rstrip()
    )

    probes: dict[str, int]
    bc: list[str] = []
    load: list[str] = []
    if case.load == "nx":
        # x = 0 kenarı u = 0; (0,0) v = 0; tüm düğümler w = 0 (yalnız zar).
        # Düzgün şekil değiştirme alanı bu BC ile tam uyumlu: u = εx·x,
        # v = εy·y + γxy·x.
        for j in range(jmax + 1):
            bc.append(f"{g.ids[(0, j)]}, 1, 1")
        bc.append(f"{g.ids[(0, 0)]}, 2, 2")
        for nid in g.ids.values():
            bc.append(f"{nid}, 3, 3")
        # x = a kenarında tutarlı düğüm yükü (kuadratik kenar: 1/6, 2/3, 1/6)
        forces: dict[int, float] = {}
        edge_len = case.b_mm / case.ny
        for ey in range(case.ny):
            f_e = case.value * edge_len
            for jj, frac in ((2 * ey, 1 / 6), (2 * ey + 1, 2 / 3), (2 * ey + 2, 1 / 6)):
                nid = g.ids[(imax, jj)]
                forces[nid] = forces.get(nid, 0.0) + f_e * frac
        load = ["*CLOAD"] + [f"{nid}, 1, {f:.9g}" for nid, f in forces.items()]
        probes = {"o": g.ids[(0, 0)], "ax": g.ids[(imax, 0)], "ay": g.ids[(imax, jmax)]}
    else:
        # Dört kenar w = 0 (dönmeler serbest); rijit cisim için köşe u, v.
        edge = {
            nid
            for (i, j), nid in g.ids.items()
            if i in (0, imax) or j in (0, jmax)
        }
        for nid in sorted(edge):
            bc.append(f"{nid}, 3, 3")
        bc.append(f"{g.ids[(0, 0)]}, 1, 2")
        bc.append(f"{g.ids[(imax, 0)]}, 2, 2")
        load = ["*DLOAD", f"PLATE, P, {case.value:.9g}"]
        probes = {"center": g.ids[(case.nx, case.ny)]}

    lines.append("*NSET, NSET=PROBE")
    lines.append(", ".join(str(n) for n in probes.values()))
    lines += ["*BOUNDARY", *bc]
    lines += ["*STEP", "*STATIC", *load, "*NODE PRINT, NSET=PROBE", "U", "*END STEP"]
    return "\n".join(lines) + "\n", probes


def parse_dat_displacements(text: str) -> dict[int, tuple[float, float, float]]:
    out: dict[int, tuple[float, float, float]] = {}
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("displacements"):
            in_block = True
            continue
        if in_block:
            parts = line.split()
            try:
                nid = int(parts[0])
                out[nid] = (float(parts[1]), float(parts[2]), float(parts[3]))
            except (ValueError, IndexError):
                in_block = False
    return out


def run_ccx(case: Case, ccx: str, workdir: Path) -> dict[int, tuple[float, float, float]]:
    deck, _ = build_deck(case)
    job = f"vp1{case.key}"
    (workdir / f"{job}.inp").write_text(deck, encoding="utf-8")
    proc = subprocess.run(
        [ccx, job],
        cwd=workdir,
        env=_ccx_run_env(ccx),
        capture_output=True,
        text=True,
        timeout=600,
    )
    dat = workdir / f"{job}.dat"
    if proc.returncode != 0 or not dat.exists():
        raise RuntimeError(f"ccx V-P1{case.key} başarısız:\n{proc.stdout[-2000:]}")
    return parse_dat_displacements(dat.read_text(encoding="utf-8", errors="replace"))


def ccx_measure(case: Case, ccx: str, workdir: Path) -> dict[str, float]:
    _, probes = build_deck(case)
    u = run_ccx(case, ccx, workdir)
    if case.load == "nx":
        o, ax, ay = u[probes["o"]], u[probes["ax"]], u[probes["ay"]]
        return {
            "eps_x": (ax[0] - o[0]) / case.a_mm,
            "eps_y": (ay[1] - ax[1]) / case.b_mm,
            "gamma_xy": (ax[1] - o[1]) / case.a_mm,
        }
    return {"w_center_mm": abs(u[probes["center"]][2])}


def main() -> int:
    ccx = _ccx_executable()
    if ccx is None:
        print("ccx bulunamadı (CCX_PATH / PATH / vendor).")
        return 1
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in CASES:
            ref = clt_reference(case)
            got = ccx_measure(case, ccx, Path(tmp))
            for key, r in ref.items():
                c = got[key]
                diff = (c - r) / abs(r) * 100.0 if abs(r) > 0 else float("nan")
                rows.append(
                    {
                        "case": case.key,
                        "layup": "/".join(f"{a:g}" for a in case.angles),
                        "quantity": key,
                        "clt": r,
                        "ccx": c,
                        "diff_pct": diff,
                    }
                )
                print(f"V-P1{case.key} {key:12s} CLT {r: .6e}  ccx {c: .6e}  fark {diff:+.3f} %")
    out = Path(__file__).resolve().parents[1] / "uploads" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / "composite_validation_vp1.json").write_text(
        json.dumps({"ccx": ccx, "rows": rows}, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
