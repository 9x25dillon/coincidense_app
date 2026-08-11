"""Co-location testing.

Given two or more layers and their declared confounds, report an effect size, an
interval, the null specification, and a plain-language statement of what the result
does and does not license.

Not a verdict. A result that fails to beat the null is reported with the same
prominence as one that beats it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .grid import (
    Grid, build_grid, default_sigma_cells, observation_window, project_layer, smooth,
)
from .layers import Layer, lowest_tier
from .nulls import Strata, build_strata, stratum_totals, surrogate
from .projection import auto_projection


# Minimum deviation from 1.0 that counts as a real effect. Below this the result is
# inside the method's own systematic error — chiefly the inferred observation window,
# which over-covers any concave study region and leaves a few percent of association
# that belongs to the geometry rather than the data. Supplying a true study boundary
# lowers this floor; until then, honesty requires it.
NOISE_FLOOR = 0.10


def colocation(a: list[float], b: list[float], mask: list[bool] | None = None) -> float:
    """Co-location index: the inner product of the two normalized intensities,
    scaled by cell count so that 1.0 means "as co-located as two independent uniform
    layers" and larger means more concentrated together.

    Scaling makes the statistic comparable across grid resolutions, which raw inner
    products are not.

    `mask` restricts the statistic to the observation window. Counting empty margin
    cells inflates the index for every layer pair equally, which is exactly the kind
    of shared artifact this tool exists to strip out.
    """
    if mask is None:
        idx = range(len(a))
        n_cells = len(a)
    else:
        idx = [i for i, inside in enumerate(mask) if inside]
        n_cells = len(idx)
    if n_cells == 0:
        return 0.0

    sa = sum(a[i] for i in idx)
    sb = sum(b[i] for i in idx)
    if sa <= 0.0 or sb <= 0.0:
        return 0.0
    return sum((a[i] / sa) * (b[i] / sb) for i in idx) * n_cells


@dataclass
class TestResult:
    layer_a: str
    layer_b: str
    observed: float
    null_mean: float
    null_sd: float
    null_lo: float
    null_hi: float
    p_value: float
    n_sim: int
    effect_ratio: float
    z_score: float
    grid: dict
    strata: dict
    tier: str
    descriptive_only: bool
    sigma_cells: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def bandwidth_km(self) -> float:
        """The spatial scale this result is about. A ratio without its bandwidth is
        not interpretable."""
        return self.sigma_cells * self.grid.get("cell_km", 0.0)

    @property
    def beats_null(self) -> bool:
        """Statistical AND practical significance.

        A p-value alone is not enough. Monte Carlo nulls get arbitrarily tight as
        simulations increase, so with enough of them a 2% deviation registers as
        p < 0.01 — and 2% is inside this method's own noise floor, because an inferred
        convex-hull window over-covers a concave study region by roughly that much.
        Reporting that as a finding would be exactly the failure this tool exists to
        prevent, just dressed in a p-value.
        """
        return self.p_value < 0.05 and abs(self.effect_ratio - 1.0) >= NOISE_FLOOR

    def statement(self) -> str:
        """Plain language, stating what the number licenses — and what it doesn't."""
        if self.strata.get("uniform_null"):
            basis = (
                "against a UNIFORM null, which assumes observations could fall anywhere "
                "with equal probability. Nothing is distributed uniformly, so this "
                "comparison is close to meaningless on its own"
            )
        else:
            basis = (
                "against a null that holds "
                + ", ".join(self.strata.get("confounds", []))
                + " fixed"
            )

        if self.p_value < 0.05 and abs(self.effect_ratio - 1.0) < NOISE_FLOOR:
            return (
                f"{self.layer_a} and {self.layer_b} differ from the null by only "
                f"{abs(self.effect_ratio - 1.0) * 100:.1f}% (p = {self.p_value:.4f}) "
                f"{basis}. The deviation is statistically detectable but smaller than "
                f"this method's noise floor of {NOISE_FLOOR * 100:.0f}%, which comes "
                f"from inferring the observation window rather than being given one. "
                f"Read this as no association. A small p-value on a tiny effect is a "
                f"property of running many simulations, not evidence of anything."
            )

        if self.effect_ratio > 1.0 and self.p_value < 0.05:
            head = (
                f"{self.layer_a} and {self.layer_b} co-locate "
                f"{self.effect_ratio:.2f}x more than expected {basis} "
                f"(p = {self.p_value:.4f})."
            )
            tail = (
                " This is a spatial association, not a mechanism. It does not indicate "
                "that either layer causes or explains the other, and an unmeasured "
                "confound remains the most common explanation for a residual of this kind."
            )
        elif self.effect_ratio < 1.0 and self.p_value < 0.05:
            head = (
                f"{self.layer_a} and {self.layer_b} co-locate LESS than expected "
                f"({self.effect_ratio:.2f}x) {basis} (p = {self.p_value:.4f})."
            )
            tail = " Segregation is as real a finding as clustering."
        else:
            head = (
                f"{self.layer_a} and {self.layer_b} show no association beyond chance "
                f"{basis} (ratio {self.effect_ratio:.2f}x, p = {self.p_value:.4f})."
            )
            tail = (
                " The apparent overlap on a map of these layers is accounted for by the "
                "confounds already declared. This is a real result, not a failed one."
            )
        return head + tail

    def to_dict(self) -> dict:
        return {
            "layers": [self.layer_a, self.layer_b],
            "observed": self.observed,
            "null": {
                "mean": self.null_mean,
                "sd": self.null_sd,
                "interval_95": [self.null_lo, self.null_hi],
                "n_simulations": self.n_sim,
                "specification": self.strata,
            },
            "effect_ratio": self.effect_ratio,
            "z_score": self.z_score,
            "p_value": self.p_value,
            "beats_null": self.beats_null,
            "grid": self.grid,
            "bandwidth_km": self.bandwidth_km,
            "bandwidth_cells": self.sigma_cells,
            "evidence_tier": self.tier,
            "descriptive_only": self.descriptive_only,
            "statement": self.statement(),
            "warnings": self.warnings,
        }


def _edge_correction(window: list[bool], grid: Grid, sigma: float) -> list[float]:
    """Fraction of a kernel centred on each cell that lands inside the window."""
    return smooth([1.0 if inside else 0.0 for inside in window], grid, sigma)


def _apply_edge(values: list[float], edge: list[float], floor: float = 0.05) -> list[float]:
    """Rescale by the retained kernel fraction.

    The floor stops a cell whose kernel is almost entirely outside the window from
    being divided by something near zero and exploding into a spurious hotspot.
    """
    return [
        (v / e if e > floor else 0.0)
        for v, e in zip(values, edge)
    ]


def test_pair(
    a: Layer,
    b: Layer,
    *,
    confounds: list[Layer] | None = None,
    cell_km: float = 50.0,
    n_sim: int = 999,
    n_bins: int = 5,
    seed: int = 0,
    sigma_cells: float | None = None,
    projection=None,
) -> TestResult:
    """Test co-location of two layers against a confound-conditioned null."""
    confounds = list(confounds or [])
    all_layers = [a, b] + confounds

    if projection is None:
        lons = [p[0] for l in all_layers for p in l.points]
        lats = [p[1] for l in all_layers for p in l.points]
        projection = auto_projection(lons, lats)

    projected = [project_layer(l, projection) for l in all_layers]
    grid = build_grid(projected, cell_km)

    rasters = [grid.rasterize(xy, l.weights) for xy, l in zip(projected, all_layers)]
    sigma = sigma_cells if sigma_cells is not None else default_sigma_cells(min(len(a), len(b)))

    window = observation_window(projected, grid, dilate_cells=1)

    # Edge correction. A Gaussian kernel centred near the window boundary spills part
    # of its mass outside and that mass is simply lost, so intensity is systematically
    # depleted near the edge — identically for every layer, which correlates them all
    # with each other for no reason but geometry. Dividing by the smoothed window
    # indicator rescales each cell by the fraction of its kernel that stayed inside.
    # Without this, two independent layers came back at 1.03x with p = 0.005.
    edge = _edge_correction(window, grid, sigma)

    def intensity(raw: list[float]) -> list[float]:
        return _apply_edge(smooth(raw, grid, sigma), edge)

    ra = intensity(rasters[0])
    rb = intensity(rasters[1])
    confound_rasters = {l.name: intensity(r) for l, r in zip(confounds, rasters[2:])}
    strata = build_strata(grid, confound_rasters, n_bins=n_bins, mask=window)
    # Surrogates are drawn from the RAW counts and smoothed exactly once, so the null
    # goes through the same single smoothing as the observation. Resampling the
    # already-smoothed raster would blur the null twice, flattening it and inflating
    # every effect size the tool reports.
    totals = stratum_totals(rasters[0], strata)

    rng = random.Random(seed)
    observed = colocation(ra, rb, window)
    null_values = []
    for _ in range(n_sim):
        sim = surrogate(totals, strata, rng)
        null_values.append(colocation(intensity(sim), rb, window))

    mean = sum(null_values) / len(null_values)
    var = sum((v - mean) ** 2 for v in null_values) / max(1, len(null_values) - 1)
    sd = math.sqrt(var)
    ordered = sorted(null_values)
    lo = ordered[int(0.025 * len(ordered))]
    hi = ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))]

    # Two-sided empirical p, with the +1 correction that keeps p from ever being 0.
    at_least_as_extreme = sum(1 for v in null_values if abs(v - mean) >= abs(observed - mean))
    p_value = (1 + at_least_as_extreme) / (1 + len(null_values))

    tier = lowest_tier([a, b])
    descriptive_only = tier in ("C", "D")

    warnings = []
    if strata.is_uniform:
        warnings.append(
            "No confounds declared. This is a uniform null and is uninformative — "
            "declare what else drives where these observations occur."
        )
    if descriptive_only:
        warnings.append(
            f"Lowest input tier is {tier}. Without an open dataset and stated inclusion "
            "criteria there is no denominator, so this result is descriptive, not "
            "inferential. The p-value describes the sample you supplied, not a population."
        )
    if min(len(a), len(b)) < 30:
        warnings.append(
            f"Small sample ({min(len(a), len(b))} points in the smaller layer). "
            "Effect estimates are unstable at this size."
        )
    if strata.n_strata > 1 and min(len(v) for v in strata.cells.values()) < 5:
        warnings.append(
            "Some strata contain fewer than 5 cells; resampling within them is nearly "
            "deterministic and the null is correspondingly too narrow. Reduce --bins."
        )

    return TestResult(
        layer_a=a.name, layer_b=b.name,
        observed=observed, null_mean=mean, null_sd=sd, null_lo=lo, null_hi=hi,
        p_value=p_value, n_sim=n_sim,
        effect_ratio=(observed / mean) if mean > 0 else float("nan"),
        z_score=((observed - mean) / sd) if sd > 0 else float("nan"),
        grid=grid.describe(), strata=strata.describe(),
        tier=tier, descriptive_only=descriptive_only, sigma_cells=sigma,
        warnings=warnings,
    )


def sensitivity(
    a: Layer,
    b: Layer,
    *,
    confounds=None,
    cell_sizes=(25.0, 50.0, 100.0),
    sigmas=(1.0, 2.0, 4.0),
    cell_km: float = 50.0,
    **kwargs,
) -> dict[str, list[TestResult]]:
    """Run the same test across grid resolutions and across bandwidths.

    Both sweeps are mandatory reporting, for different reasons.

    Cell size: a finding that appears at one resolution and vanishes at another is a
    resolution artifact (the modifiable areal unit problem), not a finding.

    Bandwidth: this one is easy to mistake for an artifact but usually is not. The
    kernel bandwidth IS the spatial scale of the question being asked. Two layers
    coupled at 5 km read as a strong association under a 25 km kernel and as almost
    nothing under a 200 km kernel — and both numbers are correct answers to different
    questions. Reporting the sweep stops a single bandwidth choice from silently
    deciding the result, in either direction.
    """
    return {
        "cell_size": [
            test_pair(a, b, confounds=confounds, cell_km=c, **kwargs) for c in cell_sizes
        ],
        "bandwidth": [
            test_pair(a, b, confounds=confounds, cell_km=cell_km, sigma_cells=s, **kwargs)
            for s in sigmas
        ],
    }
