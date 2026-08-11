"""Equal-area projection.

Area-based statistics on a Mercator grid are wrong by a factor that varies with
latitude. Across a continental extent that is not a rounding error, so everything in
this package works in an equal-area projection.

Albers Equal Area Conic on a sphere. The spherical form is exact for equal-area
purposes and avoids a dependency on a full geodesy library; the ellipsoidal
correction matters for survey-grade positioning, not for density statistics on
kilometre-scale cells.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Authalic-ish mean Earth radius, metres.
EARTH_RADIUS_M = 6371008.8


@dataclass(frozen=True)
class Albers:
    """Albers Equal Area Conic.

    Defaults are the standard North America parameters. Any region works — pick
    standard parallels at roughly 1/6 and 5/6 of the latitude span of your data.
    """

    lat_1: float = 29.5
    lat_2: float = 45.5
    lat_0: float = 23.0
    lon_0: float = -96.0
    radius: float = EARTH_RADIUS_M

    def __post_init__(self) -> None:
        p1, p2 = math.radians(self.lat_1), math.radians(self.lat_2)
        n = (math.sin(p1) + math.sin(p2)) / 2.0
        if abs(n) < 1e-12:
            raise ValueError(
                "standard parallels are symmetric about the equator; Albers is "
                "degenerate here. Use cylindrical_equal_area for global extents."
            )
        c = math.cos(p1) ** 2 + 2.0 * n * math.sin(p1)
        object.__setattr__(self, "_n", n)
        object.__setattr__(self, "_c", c)
        rho0 = self.radius * math.sqrt(c - 2.0 * n * math.sin(math.radians(self.lat_0))) / n
        object.__setattr__(self, "_rho0", rho0)

    def forward(self, lon: float, lat: float) -> tuple[float, float]:
        """(lon, lat) in degrees -> (x, y) in metres."""
        n, c, rho0 = self._n, self._c, self._rho0
        inner = c - 2.0 * n * math.sin(math.radians(lat))
        if inner < 0.0:
            # Beyond the projection's valid range; clamp rather than raise so a
            # single bad row cannot abort an entire ingest.
            inner = 0.0
        rho = self.radius * math.sqrt(inner) / n
        theta = n * math.radians(_wrap_lon(lon - self.lon_0))
        return rho * math.sin(theta), rho0 - rho * math.cos(theta)


@dataclass(frozen=True)
class CylindricalEqualArea:
    """Lambert cylindrical equal-area. Fallback for global or equatorial extents
    where a conic projection degenerates."""

    lat_ts: float = 30.0
    lon_0: float = 0.0
    radius: float = EARTH_RADIUS_M

    def forward(self, lon: float, lat: float) -> tuple[float, float]:
        k = math.cos(math.radians(self.lat_ts))
        x = self.radius * math.radians(_wrap_lon(lon - self.lon_0)) * k
        y = self.radius * math.sin(math.radians(lat)) / k
        return x, y


def _wrap_lon(d: float) -> float:
    """Wrap a longitude difference into [-180, 180] so antimeridian-spanning data
    (Alaska, the Aleutians) does not project to the far side of the world."""
    return (d + 180.0) % 360.0 - 180.0


def auto_projection(lons: list[float], lats: list[float]):
    """Choose a sensible equal-area projection for the data's actual extent.

    Explicit is better, but a tool meant for arbitrary user data has to do
    something reasonable when nobody specified a CRS.
    """
    if not lats:
        return Albers()
    lo, hi = min(lats), max(lats)
    # A conic projection is a poor fit for near-global or equator-straddling
    # extents; fall back to cylindrical.
    if hi - lo > 80.0 or (lo < -20.0 and hi > 20.0):
        return CylindricalEqualArea(lat_ts=(lo + hi) / 2.0, lon_0=_mid_lon(lons))
    span = hi - lo
    return Albers(
        lat_1=lo + span / 6.0,
        lat_2=hi - span / 6.0,
        lat_0=(lo + hi) / 2.0,
        lon_0=_mid_lon(lons),
    )


def _mid_lon(lons: list[float]) -> float:
    """Circular mean longitude, so data spanning the antimeridian gets a central
    meridian near the data rather than halfway around the planet."""
    if not lons:
        return 0.0
    sx = sum(math.cos(math.radians(v)) for v in lons)
    sy = sum(math.sin(math.radians(v)) for v in lons)
    if abs(sx) < 1e-12 and abs(sy) < 1e-12:
        return 0.0
    return math.degrees(math.atan2(sy, sx))
