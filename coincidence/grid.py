"""Equal-area analysis grid.

All layers are rasterized onto one grid so that point sets, polygons-reduced-to-points,
and continuous surfaces become commensurable.

Cell size is a declared parameter and results are reported across several sizes,
because the modifiable areal unit problem is not optional at continental scale: a
cluster that appears at 25 km and vanishes at 100 km is a resolution artifact, and the
tool should be able to say so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .layers import Layer


@dataclass
class Grid:
    x_min: float
    y_min: float
    cell_m: float
    nx: int
    ny: int

    @property
    def n_cells(self) -> int:
        return self.nx * self.ny

    @property
    def cell_km(self) -> float:
        return self.cell_m / 1000.0

    def cell_of(self, x: float, y: float) -> int | None:
        ix = int((x - self.x_min) // self.cell_m)
        iy = int((y - self.y_min) // self.cell_m)
        if 0 <= ix < self.nx and 0 <= iy < self.ny:
            return iy * self.nx + ix
        return None

    def rasterize(self, xy: list[tuple[float, float]], weights: list[float]) -> list[float]:
        out = [0.0] * self.n_cells
        for (x, y), w in zip(xy, weights):
            idx = self.cell_of(x, y)
            if idx is not None:
                out[idx] += w
        return out

    def describe(self) -> dict:
        return {
            "cell_km": self.cell_km,
            "nx": self.nx,
            "ny": self.ny,
            "n_cells": self.n_cells,
        }


def build_grid(projected: list[list[tuple[float, float]]], cell_km: float, margin_cells: int = 2) -> Grid:
    """Grid covering the union of all layers, with a margin so kernel smoothing near
    the edge is not truncated against the data's own bounding box."""
    xs = [x for layer in projected for x, _ in layer]
    ys = [y for layer in projected for _, y in layer]
    if not xs:
        raise ValueError("cannot build a grid from zero points")

    cell_m = cell_km * 1000.0
    pad = margin_cells * cell_m
    x_min, x_max = min(xs) - pad, max(xs) + pad
    y_min, y_max = min(ys) - pad, max(ys) + pad
    nx = max(1, int(math.ceil((x_max - x_min) / cell_m)))
    ny = max(1, int(math.ceil((y_max - y_min) / cell_m)))
    return Grid(x_min=x_min, y_min=y_min, cell_m=cell_m, nx=nx, ny=ny)


def project_layer(layer: Layer, projection) -> list[tuple[float, float]]:
    return [projection.forward(lon, lat) for lon, lat in layer.points]


def smooth(values: list[float], grid: Grid, sigma_cells: float) -> list[float]:
    """Separable Gaussian blur — the kernel density step.

    Bandwidth is chosen by a stated rule and reported, never tuned by eye, because
    bandwidth choice alone can manufacture or dissolve a cluster.
    """
    if sigma_cells <= 0:
        return list(values)

    radius = max(1, int(math.ceil(3.0 * sigma_cells)))
    kernel = [math.exp(-0.5 * (d / sigma_cells) ** 2) for d in range(-radius, radius + 1)]
    total = sum(kernel)
    kernel = [k / total for k in kernel]

    nx, ny = grid.nx, grid.ny
    tmp = [0.0] * len(values)
    for iy in range(ny):
        row = iy * nx
        for ix in range(nx):
            acc = 0.0
            for k, weight in enumerate(kernel, start=-radius):
                jx = ix + k
                if 0 <= jx < nx:
                    acc += values[row + jx] * weight
            tmp[row + ix] = acc

    out = [0.0] * len(values)
    for ix in range(nx):
        for iy in range(ny):
            acc = 0.0
            for k, weight in enumerate(kernel, start=-radius):
                jy = iy + k
                if 0 <= jy < ny:
                    acc += tmp[jy * nx + ix] * weight
            out[iy * nx + ix] = acc
    return out


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Convex hull by Andrew's monotone chain. Counter-clockwise, no repeated endpoint."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def build(seq):
        out: list[tuple[float, float]] = []
        for p in seq:
            while len(out) >= 2 and _cross(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]

    return build(pts) + build(reversed(pts))


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def window_from_rings(rings: list[list[tuple[float, float]]], grid: Grid) -> list[bool]:
    """The observation window from a declared study boundary, in projected metres.

    A cell is in when its centre is in. No dilation: an inferred hull is padded because
    it is a guess, and a supplied boundary is not a guess. Cells straddling the edge are
    resolved by their centres, which is the conventional rule and the only one that
    keeps the window's area unbiased — including partial cells would inflate the region,
    excluding them all would shrink it.
    """
    from .boundary import rings_contain

    out = [False] * grid.n_cells
    half = grid.cell_m / 2.0
    for iy in range(grid.ny):
        y = grid.y_min + iy * grid.cell_m + half
        row = iy * grid.nx
        for ix in range(grid.nx):
            x = grid.x_min + ix * grid.cell_m + half
            if rings_contain(rings, x, y):
                out[row + ix] = True
    return out


def observation_window(
    projected: list[list[tuple[float, float]]], grid: Grid, dilate_cells: int = 0
) -> list[bool]:
    """The region the data could actually have been observed in.

    This is not a nicety, and the shape of it matters more than it looks.

    A grid is a rectangle in projected space, but real data occupies some irregular
    region inside it — a lon/lat box projects to a curved quadrilateral, a country is
    not a rectangle, and the grid carries a margin for smoothing. Resampling a null
    across the whole rectangle scatters surrogate points into territory no observation
    could have come from, which makes the real data look concentrated together and
    returns a positive result for two layers that are genuinely independent.

    The window must be COARSE. An earlier version here took the union of the two tested
    layers' occupied cells, which is selection on the very thing under test: a cell
    enters the window because layer A is there or layer B is there, so within the
    window the two are positively associated by construction. That inflated independent
    layers to ~1.10x on its own.

    The convex hull of all points is a global boundary rather than a per-cell
    selection, so it does not carry that bias. It is also the conventional default
    observation window in spatial point-pattern analysis. Callers with a real study
    boundary — a coastline, a park boundary, a survey extent — should supply it
    instead, and should, because a hull over-covers a concave region.
    """
    all_points = [p for layer in projected for p in layer]
    if len(all_points) < 3:
        return [True] * grid.n_cells

    hull = convex_hull(all_points)
    if len(hull) < 3:
        return [True] * grid.n_cells

    pad = dilate_cells * grid.cell_m
    if pad > 0:
        cx = sum(p[0] for p in hull) / len(hull)
        cy = sum(p[1] for p in hull) / len(hull)
        hull = [_push_out(p, cx, cy, pad) for p in hull]

    out = [False] * grid.n_cells
    half = grid.cell_m / 2.0
    for iy in range(grid.ny):
        y = grid.y_min + iy * grid.cell_m + half
        row = iy * grid.nx
        for ix in range(grid.nx):
            x = grid.x_min + ix * grid.cell_m + half
            if _point_in_polygon(x, y, hull):
                out[row + ix] = True
    return out


def _push_out(p, cx, cy, pad):
    dx, dy = p[0] - cx, p[1] - cy
    d = math.hypot(dx, dy)
    if d == 0.0:
        return p
    return (p[0] + dx / d * pad, p[1] + dy / d * pad)


def _point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


def default_sigma_cells(n_points: int) -> float:
    """Bandwidth rule, stated so it can be argued with.

    Scales as n^(-1/6) — the two-dimensional analogue of Silverman's rule — floored at
    one cell so smoothing never drops below grid resolution, and capped so a sparse
    layer does not smear across the whole continent.
    """
    if n_points <= 1:
        return 1.0
    return min(6.0, max(1.0, 2.0 * n_points ** (-1.0 / 6.0) * 3.0))
