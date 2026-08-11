"""Coincidence — test whether apparent spatial coincidence survives base rates.

Bring any two located datasets and the things you think already explain where they
occur. The library answers one question: does the overlap exceed what those confounds
already predict?

Pure standard library. No install, no build step, no network.

    from coincidence import load_layer, test_pair

    caves  = load_layer("caves.csv", tier="A")
    cases  = load_layer("cases.geojson", tier="A")
    karst  = load_layer("karst.csv", tier="A")

    result = test_pair(caves, cases, confounds=[karst])
    print(result.statement())
"""

from .analysis import TestResult, colocation, sensitivity, test_pair
from .grid import Grid, build_grid, smooth
from .layers import TIERS, Layer
from .loading import LoadError, load_layer
from .nulls import build_strata, surrogate
from .projection import Albers, CylindricalEqualArea, auto_projection

__version__ = "0.1.0"

__all__ = [
    "Layer", "TIERS", "load_layer", "LoadError",
    "test_pair", "sensitivity", "colocation", "TestResult",
    "Grid", "build_grid", "smooth",
    "build_strata", "surrogate",
    "Albers", "CylindricalEqualArea", "auto_projection",
]
