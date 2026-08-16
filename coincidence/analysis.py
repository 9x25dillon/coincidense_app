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
from .nulls import Strata, build_strata, stratum_totals, surrogate_dot
from .projection import auto_projection


# Minimum deviation from 1.0 that counts as a real effect. Below this the result is
# inside the method's own systematic error — chiefly the inferred observation window,
# which over-covers any concave study region and leaves a few percent of association
# that belongs to the geometry rather than the data. Supplying a true study boundary
# lowers this floor; until then, honesty requires it.
NOISE_FLOOR = 0.10

# Below this, a cell's kernel is so far outside the window that dividing by the
# retained fraction would turn rounding error into a hotspot.
EDGE_FLOOR = 0.05


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
class NullDistribution:
    """One conditional null, built by resampling one layer and holding the other fixed.

    Which layer moves is a real choice, not a formality — see `test_pair`.
    """

    resampled: str
    mean: float
    sd: float
    lo: float
    hi: float
    p_value: float
    effect_ratio: float
    z_score: float
    values: list[float] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "resampled_layer": self.resampled,
            "mean": self.mean,
            "sd": self.sd,
            "interval_95": [self.lo, self.hi],
            "effect_ratio": self.effect_ratio,
            "z_score": self.z_score,
            "p_value": self.p_value,
        }


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
    nulls: list[NullDistribution] = field(default_factory=list, repr=False)

    @property
    def null_values(self) -> list[float]:
        """The simulated null the headline number is quoted against."""
        return self.nulls[0].values if self.nulls else []

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

    @property
    def verdict(self) -> str:
        """One of four states, for a caller that needs to branch rather than read."""
        if not self.beats_null:
            return "no association"
        return "co-located" if self.effect_ratio > 1.0 else "segregated"

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
                "directions": [n.to_dict() for n in self.nulls],
                "reported_direction": self.nulls[0].resampled if self.nulls else None,
            },
            "effect_ratio": self.effect_ratio,
            "z_score": self.z_score,
            "p_value": self.p_value,
            "beats_null": self.beats_null,
            "verdict": self.verdict,
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


def _apply_edge(values: list[float], edge: list[float], floor: float = EDGE_FLOOR) -> list[float]:
    """Rescale by the retained kernel fraction.

    The floor stops a cell whose kernel is almost entirely outside the window from
    being divided by something near zero and exploding into a spurious hotspot.
    """
    return [
        (v / e if e > floor else 0.0)
        for v, e in zip(values, edge)
    ]


@dataclass
class Prepared:
    """Everything the pipeline derives from the inputs before any simulation runs.

    Split out so that the test and the visual report are guaranteed to be looking at
    the same grid, window, bandwidth and intensities. A report that recomputed its own
    surfaces could drift from the numbers printed beside it, which for this tool would
    be the worst possible bug.
    """

    a: Layer
    b: Layer
    confounds: list[Layer]
    projection: object
    grid: Grid
    sigma: float
    window: list[bool]
    window_cells: int
    recip_edge: list[float]
    raster_a: list[float]
    raster_b: list[float]
    intensity_a: list[float]
    intensity_b: list[float]
    confound_intensity: dict[str, list[float]]
    strata: Strata
    projected: list[list[tuple[float, float]]]

    def intensity(self, raw: list[float]) -> list[float]:
        """Raw counts to edge-corrected kernel intensity: the one smoothing pass every
        layer, observed or simulated, goes through."""
        return [v * r for v, r in zip(smooth(raw, self.grid, self.sigma), self.recip_edge)]

    def surrogate_surface(self, seed: int = 0) -> list[float]:
        """One draw from the null for layer A, as an intensity surface.

        Only used for display — "here is what chance looks like" is a design principle
        of this project and it is hard to honour with a number alone.
        """
        from .nulls import surrogate
        totals = stratum_totals(self.raster_a, self.strata)
        return self.intensity(surrogate(totals, self.strata, random.Random(seed)))


def prepare(
    a: Layer,
    b: Layer,
    *,
    confounds: list[Layer] | None = None,
    cell_km: float = 50.0,
    n_bins: int = 5,
    sigma_cells: float | None = None,
    projection=None,
) -> Prepared:
    """Project, rasterize, smooth, window, and stratify. No randomness here."""
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
    recip = [(1.0 / e if e > EDGE_FLOOR else 0.0) for e in edge]

    def intensity(raw):
        return [v * r for v, r in zip(smooth(raw, grid, sigma), recip)]

    ia, ib = intensity(rasters[0]), intensity(rasters[1])
    confound_intensity = {l.name: intensity(r) for l, r in zip(confounds, rasters[2:])}
    strata = build_strata(grid, confound_intensity, n_bins=n_bins, mask=window)

    return Prepared(
        a=a, b=b, confounds=confounds, projection=projection, grid=grid, sigma=sigma,
        window=window, window_cells=sum(1 for w in window if w), recip_edge=recip,
        raster_a=rasters[0], raster_b=rasters[1], intensity_a=ia, intensity_b=ib,
        confound_intensity=confound_intensity, strata=strata, projected=projected,
    )


def _simulate(
    prep: Prepared, *, move_raster: list[float], fixed: list[float], label: str,
    observed: float, n_sim: int, seed: int, progress=None, progress_base: int = 0,
    progress_total: int = 0,
) -> NullDistribution:
    """One conditional null: resample `move_raster` within strata, hold `fixed`.

    The simulation loop never smooths anything. The co-location statistic reaches a
    surrogate only through inner products, and Gaussian smoothing is self-adjoint, so
    `<K s, w> == <s, K w>` — the convolution can be applied once to the fixed side and
    hoisted out of the loop. What is left per simulation is one array lookup per point.
    This is an exact rearrangement, not an approximation; the arithmetic below is the
    same arithmetic `colocation(prep.intensity(sim), fixed, window)` would do.
    """
    grid, sigma, window, recip = prep.grid, prep.sigma, prep.window, prep.recip_edge

    fixed_total = sum(v for v, inside in zip(fixed, window) if inside)
    # u carries the fixed layer; v carries the surrogate's own normalizer, which has to
    # be recomputed per draw because each surrogate integrates to its own total inside
    # the window once edge correction is applied.
    u = smooth([r * f if w else 0.0 for r, f, w in zip(recip, fixed, window)], grid, sigma)
    v = smooth([r if w else 0.0 for r, w in zip(recip, window)], grid, sigma)

    totals = stratum_totals(move_raster, prep.strata)
    n_cells = prep.window_cells
    rng = random.Random(seed)

    values = []
    for i in range(n_sim):
        dot_u, dot_v = surrogate_dot(totals, prep.strata, rng, [u, v])
        if dot_v <= 0.0 or fixed_total <= 0.0:
            values.append(0.0)
        else:
            values.append(n_cells * dot_u / (dot_v * fixed_total))
        if progress is not None and (i % 25 == 0 or i == n_sim - 1):
            progress(progress_base + i + 1, progress_total or n_sim)

    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / max(1, len(values) - 1)
    sd = math.sqrt(var)
    ordered = sorted(values)
    lo = ordered[int(0.025 * len(ordered))]
    hi = ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))]

    # Two-sided empirical p, with the +1 correction that keeps p from ever being 0.
    at_least_as_extreme = sum(1 for x in values if abs(x - mean) >= abs(observed - mean))
    p_value = (1 + at_least_as_extreme) / (1 + len(values))

    return NullDistribution(
        resampled=label, mean=mean, sd=sd, lo=lo, hi=hi, p_value=p_value,
        effect_ratio=(observed / mean) if mean > 0 else float("nan"),
        z_score=((observed - mean) / sd) if sd > 0 else float("nan"),
        values=values,
    )


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
    both_directions: bool = True,
    progress=None,
    prep: Prepared | None = None,
) -> TestResult:
    """Test co-location of two layers against a confound-conditioned null.

    The null resamples one layer and holds the other fixed, which is a valid test in
    either direction — and they do not have to agree. Whichever layer moves, its own
    stratum totals and its own spatial granularity shape the null, so `test(a, b)` and
    `test(b, a)` are different tests of the same hypothesis. Running only the first
    means the answer depends on the order the arguments were typed in, which for a tool
    whose whole subject is spurious pattern would be an embarrassing place to leave it.

    So both are run and the more conservative is reported: the effect ratio closer to
    1.0, with the larger p-value. Both appear in the exported bundle, and a
    disagreement large enough to change the verdict raises a warning rather than being
    resolved silently.
    """
    if prep is None:
        prep = prepare(a, b, confounds=confounds, cell_km=cell_km, n_bins=n_bins,
                       sigma_cells=sigma_cells, projection=projection)

    observed = colocation(prep.intensity_a, prep.intensity_b, prep.window)

    plan = [(prep.raster_a, prep.intensity_b, a.name)]
    if both_directions:
        plan.append((prep.raster_b, prep.intensity_a, b.name))
    total_sims = n_sim * len(plan)

    nulls = [
        _simulate(prep, move_raster=move, fixed=fixed, label=label, observed=observed,
                  n_sim=n_sim, seed=seed, progress=progress,
                  progress_base=k * n_sim, progress_total=total_sims)
        for k, (move, fixed, label) in enumerate(plan)
    ]

    # Conservative: the direction that claims least. A finding has to hold whichever
    # layer is treated as the one that could have landed elsewhere.
    reported = min(nulls, key=lambda n: abs(n.effect_ratio - 1.0))
    p_value = max(n.p_value for n in nulls)
    nulls = [reported] + [n for n in nulls if n is not reported]

    tier = lowest_tier([a, b])
    descriptive_only = tier in ("C", "D")
    strata = prep.strata

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
            "inferential. The p-value describes the sample you supplied, not a "
            "population."
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
    if len(nulls) > 1:
        verdicts = {
            (n.p_value < 0.05 and abs(n.effect_ratio - 1.0) >= NOISE_FLOOR,
             n.effect_ratio > 1.0)
            for n in nulls
        }
        if len(verdicts) > 1:
            warnings.append(
                "The two directions of the null disagree: resampling "
                f"{nulls[0].resampled} gives {nulls[0].effect_ratio:.2f}x "
                f"(p = {nulls[0].p_value:.4f}), resampling {nulls[1].resampled} gives "
                f"{nulls[1].effect_ratio:.2f}x (p = {nulls[1].p_value:.4f}). The "
                "conservative one is reported. A result that depends on which layer is "
                "held fixed is usually a difference in how finely the two layers are "
                "resolved, not a finding."
            )

    return TestResult(
        layer_a=a.name, layer_b=b.name,
        observed=observed, null_mean=reported.mean, null_sd=reported.sd,
        null_lo=reported.lo, null_hi=reported.hi,
        p_value=p_value, n_sim=n_sim,
        effect_ratio=reported.effect_ratio, z_score=reported.z_score,
        grid=prep.grid.describe(), strata=strata.describe(),
        tier=tier, descriptive_only=descriptive_only, sigma_cells=prep.sigma,
        warnings=warnings, nulls=nulls,
    )


def sensitivity(
    a: Layer,
    b: Layer,
    *,
    confounds=None,
    cell_sizes=(25.0, 50.0, 100.0),
    bandwidths_km=None,
    sigmas=(1.0, 2.0, 4.0),
    cell_km: float = 50.0,
    sigma_cells: float | None = None,
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

    Which means the two sweeps have to be kept apart, and an earlier version of this
    function did not: bandwidth was specified in CELLS, so sweeping the cell size
    swept the bandwidth with it. Cells of 25/50/100 km carried kernels of 61/122/244
    km, and the tool would then report a scale effect as a resolution artifact and
    advise discarding it. The cell-size sweep now holds the bandwidth fixed in
    KILOMETRES and varies only the raster it is measured on, which is the only version
    of the sweep that isolates what it claims to isolate.
    """
    base_sigma = sigma_cells if sigma_cells is not None else default_sigma_cells(
        min(len(a), len(b))
    )
    base_bandwidth_km = base_sigma * cell_km
    bandwidths = bandwidths_km if bandwidths_km is not None else [s * cell_km for s in sigmas]

    return {
        "cell_size": [
            test_pair(a, b, confounds=confounds, cell_km=c,
                      sigma_cells=base_bandwidth_km / c, **kwargs)
            for c in cell_sizes
        ],
        "bandwidth": [
            test_pair(a, b, confounds=confounds, cell_km=cell_km,
                      sigma_cells=bw / cell_km, **kwargs)
            for bw in bandwidths
        ],
    }
