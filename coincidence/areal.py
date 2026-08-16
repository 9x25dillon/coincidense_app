"""Areal support: polygons rasterized by the area they actually cover.

Until now every polygon collapsed to one representative point, so a reservation the size
of a small country and a single cave entrance entered the grid as the same thing: one
dot, one unit of weight. That is the largest distortion the input path has, and it runs
in a consistent direction — it shrinks large features to nothing and lets small ones
count for as much.

Here a polygon contributes to every cell it touches, in proportion to how much of that
cell it covers. The intersection area is computed exactly, by clipping, rather than by
sampling points inside cells: sampling introduces its own noise into a tool whose whole
job is deciding whether a small residual is real.

Two readings of "how much", because they are different questions and both are wanted:

    extent  a cell gets the area covered. A polygon twice the size contributes twice
            as much. This is the right reading for karst, land cover, or any layer
            answering "how much of this place is X".

    mass    a feature's weight is divided across the cells it covers, so every feature
            contributes its weight and no more, wherever it is spread. This is the
            right reading for a county's population, or for counting features.
"""

from __future__ import annotations

from .grid import Grid

# A ring is a closed loop of projected metres; a polygon is an exterior ring followed by
# its holes; a shape is one feature, which may be several polygons (a MultiPolygon).
Ring = list
Polygon = list
Shape = list

EXTENT = "extent"
MASS = "mass"
MODES = (EXTENT, MASS)


def ring_area(ring: Ring) -> float:
    """Unsigned area by the shoelace formula."""
    n = len(ring)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) * 0.5


def clip_axis(ring: Ring, axis: int, value: float, keep_greater: bool) -> Ring:
    """One Sutherland-Hodgman pass against an axis-aligned line.

    A grid cell is bounded by four such lines, so the crossing point has a closed form
    and no root-finding is needed: one coordinate is the clip value exactly, the other
    is a linear interpolation. This runs once per vertex per cell edge, which is the
    innermost loop in the module.
    """
    if not ring:
        return []
    other = 1 - axis
    out = []
    prev = ring[-1]
    prev_in = (prev[axis] >= value) if keep_greater else (prev[axis] <= value)
    for point in ring:
        point_in = (point[axis] >= value) if keep_greater else (point[axis] <= value)
        if point_in != prev_in:
            span = point[axis] - prev[axis]
            t = 0.0 if span == 0.0 else (value - prev[axis]) / span
            crossing = [0.0, 0.0]
            crossing[axis] = value
            crossing[other] = prev[other] + (point[other] - prev[other]) * t
            out.append((crossing[0], crossing[1]))
        if point_in:
            out.append(point)
        prev, prev_in = point, point_in
    return out


def clip_to_box(ring: Ring, x0: float, y0: float, x1: float, y1: float) -> Ring:
    """The part of a ring inside an axis-aligned box.

    Sutherland–Hodgman against a convex window. For a concave ring the result can carry
    zero-width corridors running along the box edge where the algorithm joins otherwise
    disjoint pieces; those contribute nothing to the shoelace sum, so the AREA of the
    result is correct even where its outline is degenerate. Area is all this module
    asks of it — and the test suite checks that claim against an independent
    supersampled estimate on a deliberately concave shape rather than trusting it.
    """
    ring = clip_axis(ring, 0, x0, True)
    ring = clip_axis(ring, 0, x1, False)
    ring = clip_axis(ring, 1, y0, True)
    ring = clip_axis(ring, 1, y1, False)
    return ring


def _bounds(rings) -> tuple[float, float, float, float]:
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    return min(xs), min(ys), max(xs), max(ys)


def polygon_coverage(polygon: Polygon, grid: Grid, out: dict) -> None:
    """Accumulate covered area per cell for one polygon, holes subtracted.

    Clipping runs in two stages — the whole polygon to a row of cells, then that much
    smaller polygon to each cell in the row. A continental outline densified to a few
    thousand vertices would otherwise be re-clipped in full against every cell in its
    bounding box, which is the difference between this running in a second and running
    in a minute.
    """
    if not polygon or len(polygon[0]) < 3:
        return
    x_lo, y_lo, x_hi, y_hi = _bounds(polygon)

    ix0 = max(0, int((x_lo - grid.x_min) // grid.cell_m))
    ix1 = min(grid.nx - 1, int((x_hi - grid.x_min) // grid.cell_m))
    iy0 = max(0, int((y_lo - grid.y_min) // grid.cell_m))
    iy1 = min(grid.ny - 1, int((y_hi - grid.y_min) // grid.cell_m))
    if ix1 < ix0 or iy1 < iy0:
        return

    for iy in range(iy0, iy1 + 1):
        row_y0 = grid.y_min + iy * grid.cell_m
        row_y1 = row_y0 + grid.cell_m
        strips = [
            clip_axis(clip_axis(ring, 1, row_y0, True), 1, row_y1, False)
            for ring in polygon
        ]
        if len(strips[0]) < 3:
            continue
        row = iy * grid.nx
        for ix in range(ix0, ix1 + 1):
            cx0 = grid.x_min + ix * grid.cell_m
            cx1 = cx0 + grid.cell_m
            area = 0.0
            for k, strip in enumerate(strips):
                if len(strip) < 3:
                    continue
                piece = clip_axis(clip_axis(strip, 0, cx0, True), 0, cx1, False)
                a = ring_area(piece)
                area += -a if k else a  # ring 0 is the exterior, the rest are holes
            if area > 0.0:
                out[row + ix] = out.get(row + ix, 0.0) + area


def check_shape(shape: Shape) -> None:
    """Refuse malformed geometry instead of covering nothing.

    The nesting here is three deep — shape, polygon, ring — and getting it one level
    wrong is easy for a caller building geometry by hand. Left unchecked it does not
    raise: the ring is read as a polygon, its first point as a ring, and the feature
    silently covers zero cells. A layer that quietly contributes nothing is the worst
    failure mode this tool has, because every downstream number stays plausible.
    """
    if not shape:
        return
    for polygon in shape:
        if not polygon:
            continue
        ring = polygon[0]
        ok = (
            isinstance(ring, (list, tuple)) and len(ring) >= 3
            and isinstance(ring[0], (list, tuple)) and len(ring[0]) == 2
            and all(isinstance(c, (int, float)) for c in ring[0])
        )
        if not ok:
            raise ValueError(
                "malformed areal geometry. A shape is a list of polygons, a polygon is "
                "a list of rings (exterior first, then holes), and a ring is a list of "
                "(x, y) pairs — so one square is [[[(0,0),(1,0),(1,1),(0,1)]]]. "
                f"Got a polygon whose first ring is {ring!r:.80}"
            )


def shape_coverage(shape: Shape, grid: Grid) -> dict:
    """Covered area per cell index for one feature, which may be several polygons."""
    check_shape(shape)
    out: dict = {}
    for polygon in shape:
        polygon_coverage(polygon, grid, out)
    return out


def rasterize(shapes: list, weights: list, grid: Grid, mode: str = EXTENT) -> list:
    """Areal raster for a whole layer.

    In `extent` the value is weight times covered area, normalized by the cell area so
    a full cell reads 1.0 and the numbers stay comparable across grid resolutions. In
    `mass` the weight is divided among the cells the feature covers, so each feature
    totals its own weight regardless of how far it is spread.
    """
    if mode not in MODES:
        raise ValueError(f"unknown areal mode {mode!r}; expected one of {MODES}")

    cell_area = grid.cell_m * grid.cell_m
    out = [0.0] * grid.n_cells
    for shape, weight in zip(shapes, weights):
        cover = shape_coverage(shape, grid)
        if not cover:
            continue
        if mode == MASS:
            total = sum(cover.values())
            if total <= 0.0:
                continue
            for i, area in cover.items():
                out[i] += weight * area / total
        else:
            for i, area in cover.items():
                out[i] += weight * area / cell_area
    return out


def total_area(shape: Shape) -> float:
    """Area of one feature in projected units, holes subtracted."""
    total = 0.0
    for polygon in shape:
        for k, ring in enumerate(polygon):
            a = ring_area(ring)
            total += -a if k else a
    return max(0.0, total)


def project_shapes(shapes, projection, densify_deg: float = 0.25):
    """Project a layer's geometry, densifying long edges first.

    A straight edge in longitude/latitude is a curve in an equal-area projection, so a
    county drawn with four vertices loses real area at its corners once projected.
    Subdividing before projection costs vertices and buys back the area.
    """
    from .boundary import densify

    out = []
    for shape in shapes or []:
        if not shape:
            out.append(None)
            continue
        out.append([
            [[projection.forward(lon, lat) for lon, lat in densify(ring, densify_deg)]
             for ring in polygon]
            for polygon in shape
        ])
    return out


def rasterize_layer(xy, shapes, weights, grid: Grid, mode: str = EXTENT) -> list:
    """Rasterize a layer whose features may be points, areas, or a mix of both.

    Point features keep the count semantics they always had. Areal features are spread
    over the cells they cover. A file holding both puts two different units on one
    grid, which is worth knowing about but is the source's choice, not this function's
    to resolve.
    """
    if not shapes:
        return grid.rasterize(xy, weights)

    point_xy, point_w, area_shapes, area_w = [], [], [], []
    for pos, shape, weight in zip(xy, shapes, weights):
        if shape:
            area_shapes.append(shape)
            area_w.append(weight)
        else:
            point_xy.append(pos)
            point_w.append(weight)

    out = grid.rasterize(point_xy, point_w) if point_xy else [0.0] * grid.n_cells
    if area_shapes:
        areal = rasterize(area_shapes, area_w, grid, mode)
        out = [a + b for a, b in zip(out, areal)]
    return out
