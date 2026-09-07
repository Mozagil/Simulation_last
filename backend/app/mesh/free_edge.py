"""Shell mesh serbest kenar (free edge) tespiti.

Bir kenar tam bir elemana aitse serbesttir. Kapalı bir kabukta beklenen
serbest kenarlar yalnızca dış çevre / deliklerdir.
"""

from __future__ import annotations

from collections import defaultdict


def free_edges_from_connectivity(
    elements: list[list[int]],
) -> list[tuple[int, int]]:
    """Eleman bağlanırlığı (üçgen 3, quad 4 düğüm indeksi) → serbest kenarlar.

    Kenar (min, max) olarak kanonikleştirilir. Dönen liste sıralı, tekrarsız.
    """
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for conn in elements:
        n = len(conn)
        if n < 3:
            continue
        for i in range(n):
            a, b = conn[i], conn[(i + 1) % n]
            if a == b:
                continue
            key = (a, b) if a < b else (b, a)
            counts[key] += 1
    return sorted(edge for edge, c in counts.items() if c == 1)
