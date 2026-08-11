"""Generate the worked example: a confounded coincidence.

Two layers, A and B, that both cluster where a third variable C is high, and are
otherwise independent of each other. There is no relationship between A and B beyond
the one C creates.

A naive overlay shows them coinciding, strikingly. Against a uniform null the
association is overwhelmingly "significant". Condition on C and it disappears.

This is the whole thesis in three CSV files, and it is why the tool exists.

    python3 examples/make_synthetic.py
    python3 -m coincidence test examples/layer_a.csv examples/layer_b.csv
    python3 -m coincidence test examples/layer_a.csv examples/layer_b.csv \
        --confound examples/confound_c.csv
"""

from __future__ import annotations

import csv
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

# Hotspots of the confound: where the underlying driver is concentrated.
HOTSPOTS = [
    (-84.0, 37.2),   # Appalachian / Kentucky karst
    (-92.5, 36.5),   # Ozarks
    (-104.5, 43.6),  # Black Hills
    (-105.5, 32.2),  # Guadalupe / southern New Mexico
    (-121.5, 44.0),  # Cascades
    (-87.5, 20.5),   # Yucatan
]


def draw(rng: random.Random, n: int, spread: float) -> list[tuple[float, float]]:
    """Sample points around the confound hotspots. Both A and B use this, with
    independent randomness — so any association between them comes only from the
    shared hotspots."""
    out = []
    for _ in range(n):
        lon0, lat0 = HOTSPOTS[rng.randrange(len(HOTSPOTS))]
        out.append((rng.gauss(lon0, spread), rng.gauss(lat0, spread * 0.7)))
    return out


def write(path: str, rows: list[tuple[float, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "longitude", "latitude"])
        for i, (lon, lat) in enumerate(rows, 1):
            w.writerow([f"obs_{i}", f"{lon:.5f}", f"{lat:.5f}"])
    print(f"wrote {path} ({len(rows)} rows)")


def main() -> None:
    rng = random.Random(20260811)
    write(os.path.join(HERE, "layer_a.csv"), draw(rng, 220, 1.6))
    write(os.path.join(HERE, "layer_b.csv"), draw(rng, 260, 1.9))
    write(os.path.join(HERE, "confound_c.csv"), draw(rng, 900, 2.0))
    print(
        "\nNow run both tests and compare:\n"
        "  python3 -m coincidence test examples/layer_a.csv examples/layer_b.csv\n"
        "  python3 -m coincidence test examples/layer_a.csv examples/layer_b.csv "
        "--confound examples/confound_c.csv\n"
    )


if __name__ == "__main__":
    main()
