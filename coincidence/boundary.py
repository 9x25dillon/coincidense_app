"""A declared study boundary.

The observation window is the single largest source of systematic error in this tool.
Absent a real boundary the engine infers one from the convex hull of the data, and a
hull over-covers any concave region — a watershed, a coastline, a survey extent, a
mountain range — by scattering surrogates into territory no observation could have come
from. That inflation is what the 10% noise floor is paying for, and it is paid on every
result whether or not the user could have supplied the real thing.

So: supply the real thing. A boundary here is a polygon in longitude/latitude, holes
included, and it replaces the hull outright.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

# Maximum segment length, in degrees, before a boundary edge is subdivided prior to
# projection. A straight line in lon/lat is a curve in an equal-area projection, and a
# county boundary drawn with four vertices would otherwise cut corners off the study
# region after projection. Subdividing is cheaper than being wrong at the edges.
MAX_SEGMENT_DEG = 0.25


class BoundaryError(Exception):
    pass


@dataclass
class Boundary:
    """Rings in (lon, lat). Exteriors and holes are held together and resolved by the
    even-odd rule, which handles both without either being labelled."""

    rings: list[list[tuple[float, float]]] = field(default_factory=list)
    source: str | None = None

    def __len__(self) -> int:
        return len(self.rings)

    @property
    def n_vertices(self) -> int:
        return sum(len(r) for r in self.rings)

    def bbox(self) -> tuple[float, float, float, float]:
        xs = [x for r in self.rings for x, _ in r]
        ys = [y for r in self.rings for _, y in r]
        return min(xs), min(ys), max(xs), max(ys)

    def describe(self) -> dict:
        lo_x, lo_y, hi_x, hi_y = self.bbox()
        return {
            "source": self.source,
            "n_rings": len(self.rings),
            "n_vertices": self.n_vertices,
            "extent": {"lon": [lo_x, hi_x], "lat": [lo_y, hi_y]},
        }


def load_boundary(path: str) -> Boundary:
    """Read a study boundary from GeoJSON.

    Accepts a FeatureCollection, a Feature, or a bare geometry, and takes every
    Polygon and MultiPolygon it finds — so a file holding the three counties of a
    survey area works without merging them first. Non-areal geometries are ignored
    rather than guessed at: a LineString is not a study region, and quietly closing it
    into one would invent a boundary the user did not draw.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".geojson", ".json"):
        raise BoundaryError(
            f"unsupported boundary format {ext!r} for {path}. "
            f"Supply a study boundary as .geojson (Polygon or MultiPolygon)."
        )
    with open(path, "r", encoding="utf-8-sig") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise BoundaryError(f"{path}: not valid JSON — {exc}") from exc

    rings: list[list[tuple[float, float]]] = []
    for geom in _geometries(data):
        _collect_rings(geom, rings)

    rings = [r for r in (_clean_ring(r) for r in rings) if len(r) >= 3]
    if not rings:
        raise BoundaryError(
            f"{path}: no Polygon or MultiPolygon geometry found. A study boundary has "
            f"to enclose an area; points and lines cannot define one."
        )
    return Boundary(rings=rings, source=path)


def _geometries(node):
    """Every geometry in a GeoJSON document, whatever it is wrapped in."""
    if not isinstance(node, dict):
        return
    kind = node.get("type")
    if kind == "FeatureCollection":
        for feat in node.get("features") or []:
            yield from _geometries(feat)
    elif kind == "Feature":
        yield from _geometries(node.get("geometry") or {})
    elif kind == "GeometryCollection":
        for geom in node.get("geometries") or []:
            yield from _geometries(geom)
    elif kind:
        yield node


def _collect_rings(geom: dict, out: list) -> None:
    kind, coords = geom.get("type"), geom.get("coordinates")
    if coords is None:
        return
    if kind == "Polygon":
        out.extend(coords)
    elif kind == "MultiPolygon":
        for poly in coords:
            out.extend(poly)


def _clean_ring(ring) -> list[tuple[float, float]]:
    """Coerce to (lon, lat) floats and drop the repeated closing vertex."""
    pts = []
    for pos in ring:
        try:
            pts.append((float(pos[0]), float(pos[1])))
        except (TypeError, ValueError, IndexError):
            continue
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def densify(ring: list[tuple[float, float]], max_deg: float = MAX_SEGMENT_DEG):
    """Subdivide long edges so the ring survives projection with its shape intact."""
    if max_deg <= 0 or len(ring) < 2:
        return list(ring)
    out = []
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % len(ring)]
        out.append((x1, y1))
        steps = int(math.hypot(x2 - x1, y2 - y1) / max_deg)
        for k in range(1, steps):
            t = k / steps
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    return out


def project_rings(boundary: Boundary, projection) -> list[list[tuple[float, float]]]:
    """The boundary in projected metres, on the same projection as the layers."""
    return [
        [projection.forward(lon, lat) for lon, lat in densify(ring)]
        for ring in boundary.rings
    ]


def rings_contain(rings: list[list[tuple[float, float]]], x: float, y: float) -> bool:
    """Even-odd ray casting across every ring at once.

    Accumulating crossings over exteriors and holes together and taking the parity
    resolves holes and disjoint parts without either being declared: a point inside a
    hole crosses its exterior once and the hole once, and comes out even.
    """
    inside = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < xin:
                    inside = not inside
    return inside
