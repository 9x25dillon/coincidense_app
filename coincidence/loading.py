"""Load a Layer from whatever the user has.

The point of this module is that nobody should have to reformat their data to ask an
honest question about it. CSV, TSV, JSON, JSON Lines, GeoJSON. Coordinate columns are
detected by name when possible and can always be named explicitly.

Rows that cannot be located are dropped and counted, never guessed at. The count is
reported in the layer's provenance, because silently discarding a third of someone's
data and then reporting a confident statistic is its own kind of dishonesty.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any, Iterable

from .layers import Layer

LAT_NAMES = (
    "lat", "latitude", "y", "lat_dd", "latdd", "lat_deg", "ycoord", "y_coord",
    "decimallatitude", "point_y", "centroid_lat",
)
LON_NAMES = (
    "lon", "long", "lng", "longitude", "x", "lon_dd", "londd", "lon_deg",
    "xcoord", "x_coord", "decimallongitude", "point_x", "centroid_lon",
)


class LoadError(Exception):
    pass


def load_layer(
    path: str,
    *,
    name: str | None = None,
    lat_field: str | None = None,
    lon_field: str | None = None,
    weight_field: str | None = None,
    tier: str = "D",
    custodian: str | None = None,
    confounds: Iterable[str] = (),
) -> Layer:
    """Load any supported file into a Layer.

    tier defaults to D — uncertain provenance. Declaring a better tier is the user's
    assertion to make explicitly, not something this function infers from a filename.
    """
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()

    if ext in (".geojson",):
        records = _geojson_records(text)
    elif ext in (".json",):
        records = _json_records(text)
    elif ext in (".jsonl", ".ndjson"):
        records = _jsonl_records(text)
    elif ext in (".csv", ".tsv", ".txt", ""):
        records = _delimited_records(text)
    else:
        raise LoadError(
            f"unsupported extension {ext!r} for {path}. Supported: "
            ".csv .tsv .json .jsonl .ndjson .geojson"
        )

    records = list(records)
    if not records:
        raise LoadError(f"{path}: no records found")

    points, weights, shapes, dropped = _extract(
        records, lat_field=lat_field, lon_field=lon_field, weight_field=weight_field,
        path=path,
    )
    if not points:
        raise LoadError(
            f"{path}: no usable coordinates in {len(records)} records. "
            f"Name the columns explicitly with --lat/--lon."
        )

    return Layer(
        name=name or os.path.splitext(os.path.basename(path))[0],
        points=points,
        weights=weights,
        shapes=shapes,
        tier=tier,
        custodian=custodian,
        source_path=path,
        confounds=list(confounds),
        dropped_rows=dropped,
    )


# ---------------------------------------------------------------- readers --


def _delimited_records(text: str) -> list[dict]:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def _json_records(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        if data.get("type") == "FeatureCollection":
            return _geojson_records(text)
        # A dict wrapping the actual array under some key — take the first list of
        # objects we find, which covers most API-shaped payloads.
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
        raise LoadError("JSON object contains no array of records")
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    raise LoadError("JSON must be an array of objects or an object wrapping one")


def _jsonl_records(text: str) -> list[dict]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LoadError(f"line {i}: {exc}") from exc
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _geojson_records(text: str) -> list[dict]:
    data = json.loads(text)
    features = data.get("features") if isinstance(data, dict) else None
    if features is None:
        raise LoadError("GeoJSON has no 'features' array")
    out = []
    for feat in features:
        geom = feat.get("geometry") or {}
        pos = _representative_point(geom)
        if pos is None:
            continue
        rec = dict(feat.get("properties") or {})
        rec["__lon__"], rec["__lat__"] = pos
        # The representative point is kept for every feature, so extent, projection and
        # the point path work unchanged. The rings are kept as well, so the areal path
        # can use what the point throws away.
        shape = _areal_rings(geom)
        if shape:
            rec["__shape__"] = shape
        out.append(rec)
    return out


def _areal_rings(geom: dict) -> list | None:
    """Polygon rings from a geometry, as [polygon][ring][(lon, lat)].

    Only Polygon and MultiPolygon have area. A LineString encloses nothing, and closing
    one into a region would invent extent the source never claimed.
    """
    gtype, coords = geom.get("type"), geom.get("coordinates")
    if coords is None:
        return None
    if gtype == "Polygon":
        polygons = [coords]
    elif gtype == "MultiPolygon":
        polygons = list(coords)
    elif gtype == "GeometryCollection":
        found = []
        for sub in geom.get("geometries", []):
            found.extend(_areal_rings(sub) or [])
        return found or None
    else:
        return None

    out = []
    for poly in polygons:
        rings = []
        for ring in poly:
            pts = []
            for pos in _open_ring(ring):
                try:
                    pts.append((float(pos[0]), float(pos[1])))
                except (TypeError, ValueError, IndexError):
                    continue
            if len(pts) >= 3:
                rings.append(pts)
        if rings:
            out.append(rings)
    return out or None


def _representative_point(geom: dict) -> tuple[float, float] | None:
    """One representative coordinate per geometry.

    Polygons collapse to the mean of their exterior ring. That is a real
    simplification — a large reservation or a long cave system becomes one dot — and
    it is recorded as a limitation rather than hidden. Areal support is Phase 2 work.
    """
    gtype, coords = geom.get("type"), geom.get("coordinates")
    if not gtype or coords is None:
        return None
    if gtype == "Point":
        return float(coords[0]), float(coords[1])
    if gtype == "MultiPoint" or gtype == "LineString":
        return _mean_positions(coords)
    if gtype == "Polygon":
        return _mean_positions(_open_ring(coords[0])) if coords else None
    if gtype == "MultiLineString":
        return _mean_positions([p for part in coords for p in part])
    if gtype == "MultiPolygon":
        return _mean_positions([p for poly in coords for p in _open_ring(poly[0])])
    if gtype == "GeometryCollection":
        pts = [_representative_point(g) for g in geom.get("geometries", [])]
        pts = [p for p in pts if p]
        return _mean_positions(pts) if pts else None
    return None


def _open_ring(ring):
    """Drop a GeoJSON ring's repeated closing vertex.

    Rings are required to close, so the first coordinate appears twice. Averaging it
    twice pulls the representative point toward that corner — a small bias, but a
    systematic one in the same direction for every polygon in a file.
    """
    if len(ring) > 1 and list(ring[0][:2]) == list(ring[-1][:2]):
        return ring[:-1]
    return ring


def _mean_positions(positions) -> tuple[float, float] | None:
    xs, ys = [], []
    for pos in positions:
        try:
            xs.append(float(pos[0]))
            ys.append(float(pos[1]))
        except (TypeError, ValueError, IndexError):
            continue
    if not xs:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


# ------------------------------------------------------------- extraction --


def _columns(records) -> str:
    """The file's columns with a sample value each.

    A bare list of column names is not much help when the problem is that the column
    you meant holds text, or is empty, or is the one two along. Showing what is
    actually in the first row usually answers the question without a second command.
    """
    first = records[0]
    parts = []
    for key in [k for k in first if not str(k).startswith("__")][:12]:
        sample = str(first.get(key, ""))
        if len(sample) > 18:
            sample = sample[:17] + "…"
        parts.append(f"    {key!r:<22} e.g. {sample!r}")
    if len(first) > 12:
        parts.append(f"    … and {len(first) - 12} more")
    return "\n".join(parts)


def _extract(records, *, lat_field, lon_field, weight_field, path):
    keys = list(records[0].keys())
    lat_key = lat_field or _find_field(keys, LAT_NAMES) or ("__lat__" if "__lat__" in keys else None)
    lon_key = lon_field or _find_field(keys, LON_NAMES) or ("__lon__" if "__lon__" in keys else None)

    if lat_key is None or lon_key is None:
        # Suggest columns that could plausibly BE coordinates. Naming the first and
        # last column regardless of content invites the user to declare a site name as
        # a longitude, and the loader would then drop every row and blame the data.
        numeric = [k for k in keys if _to_float(records[0].get(k)) is not None]
        hint = (
            f"  Name them explicitly: --lat {numeric[0]} --lon {numeric[1]}"
            if len(numeric) >= 2 else
            "  Name them explicitly with --lat and --lon."
        )
        raise LoadError(
            f"{path}: could not identify coordinate columns. The file has:\n"
            f"{_columns(records)}\n{hint}"
        )
    for named, key in (("--lat", lat_key), ("--lon", lon_key)):
        if key not in keys:
            raise LoadError(
                f"{path}: {named} column {key!r} not found. The file has:\n"
                f"{_columns(records)}"
            )
    if weight_field and weight_field not in keys:
        raise LoadError(
            f"{path}: --weight column {weight_field!r} not found. The file has:\n"
            f"{_columns(records)}"
        )

    points, weights, shapes, dropped = [], [], [], 0
    for rec in records:
        lat, lon = _to_float(rec.get(lat_key)), _to_float(rec.get(lon_key))
        if lat is None or lon is None or not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            dropped += 1
            continue
        if lat == 0.0 and lon == 0.0:
            # Null Island: almost always a failed geocode rather than a real
            # observation in the Gulf of Guinea.
            dropped += 1
            continue
        weight = 1.0
        if weight_field:
            w = _to_float(rec.get(weight_field))
            if w is None or w < 0.0:
                dropped += 1
                continue
            weight = w
        points.append((lon, lat))
        weights.append(weight)
        shapes.append(rec.get("__shape__"))
    return points, weights, (shapes if any(shapes) else None), dropped


def _find_field(keys: list[str], candidates: tuple[str, ...]) -> str | None:
    norm = {str(k).strip().lower().replace(" ", "_").replace("-", "_"): k for k in keys}
    for cand in candidates:
        if cand in norm:
            return norm[cand]
    return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
