"""T29 (.k içe aktarma) için küçük LS-DYNA keyword dosyası üretir — yalnız içe aktarma testinin girdisi.

Kare kesitli kutu (L 300 × h 50 × b 40, orta yüzey, 10 mm kabuk), birimler mm–t–s (kütle tonne),
*RIGIDWALL_PLANAR x = 0 (normal +x), *INITIAL_VELOCITY_GENERATION −x 10 m/s, *CONTROL_TERMINATION 20 ms.
Malzeme kartı seçilebilir: "024" (*MAT_PIECEWISE_LINEAR_PLASTICITY — çevrilir) ya da "003"
(*MAT_PLASTIC_KINEMATIC — belgedeki T29 metni; okuyucu atlar, `skipped` listesinde görünür).
"""

from __future__ import annotations

L, H, B, T, ES = 300.0, 50.0, 40.0, 3.0, 10.0


def _ring() -> list[tuple[float, float]]:
    """Kesit çevresi (y, z) — ES aralıklı, saat yönünün tersine."""
    pts: list[tuple[float, float]] = []
    corners = [(0.0, 0.0), (H, 0.0), (H, B), (0.0, B)]
    for (y0, z0), (y1, z1) in zip(corners, corners[1:] + corners[:1]):
        n = round(max(abs(y1 - y0), abs(z1 - z0)) / ES)
        pts += [(y0 + (y1 - y0) * i / n, z0 + (z1 - z0) * i / n) for i in range(n)]
    return pts


def simple_k(mat: str = "024") -> str:
    ring = _ring()
    nr, nx = len(ring), round(L / ES)
    out = ["*KEYWORD", "*TITLE", "egitim T29 kare kutu (mm-t-s)", "*NODE"]
    nid = lambda i, j: i * nr + j + 1  # noqa: E731
    for i in range(nx + 1):
        for j, (y, z) in enumerate(ring):
            out.append(f"{nid(i, j):8d}{i * ES:16.6f}{y:16.6f}{z:16.6f}")
    out.append("*ELEMENT_SHELL")
    eid = 0
    for i in range(nx):
        for j in range(nr):
            eid += 1
            j2 = (j + 1) % nr
            out.append(f"{eid:8d}{1:8d}{nid(i, j):8d}{nid(i + 1, j):8d}{nid(i + 1, j2):8d}{nid(i, j2):8d}")
    out += ["*PART", "kutu", f"{1:10d}{1:10d}{1:10d}",
            "*SECTION_SHELL", f"{1:10d}{2:10d}", f"{T:10.3f}{T:10.3f}{T:10.3f}{T:10.3f}"]
    if mat == "003":
        out += ["*MAT_PLASTIC_KINEMATIC", f"{1:10d}{7.85e-9:10.3e}{210000.0:10.1f}{0.3:10.2f}{235.0:10.1f}{0.0:10.1f}{0.0:10.1f}"]
    else:
        out += ["*MAT_PIECEWISE_LINEAR_PLASTICITY",
                f"{1:10d}{7.85e-9:10.3e}{210000.0:10.1f}{0.3:10.2f}{235.0:10.1f}{0.0:10.1f}{0.0:10.1f}{0.0:10.1f}",
                f"{0.0:10.1f}{0.0:10.1f}{0:10d}{0:10d}{0.0:10.1f}",
                "".join(f"{0.0:10.1f}" for _ in range(8)), "".join(f"{0.0:10.1f}" for _ in range(8))]
    out += ["*INITIAL_VELOCITY_GENERATION",
            f"{1:10d}{2:10d}{0.0:10.1f}{-10000.0:10.1f}{0.0:10.1f}{0.0:10.1f}{0:10d}{0:10d}",
            "".join(f"{0.0:10.1f}" for _ in range(6)) + f"{0:10d}{0:10d}",
            "*RIGIDWALL_PLANAR", f"{0:10d}{0:10d}{0:10d}{0:10d}{0:10d}",
            f"{0.0:10.1f}{25.0:10.1f}{20.0:10.1f}{1.0:10.1f}{25.0:10.1f}{20.0:10.1f}{0.0:10.1f}{0:10d}",
            "*CONTROL_TERMINATION", f"{0.02:10.4f}", "*END"]
    return "\n".join(out) + "\n"
