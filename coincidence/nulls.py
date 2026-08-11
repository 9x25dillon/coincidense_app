"""Null models — the actual product.

The naive question is "do these two layers overlap?" Against a uniform null the answer
is essentially always yes, because nothing on Earth is uniformly distributed. That
test is not evidence of anything.

The conditional null asks the useful question: does the overlap exceed what the shared
confounds already predict? It is built by stratifying space on the confound stack and
resampling within strata, which destroys the hypothesized association while preserving
each layer's relationship to its confounds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .grid import Grid


@dataclass
class Strata:
    """Stratum assignment per grid cell, plus the cell membership of each stratum."""

    of_cell: list[int]
    cells: dict[int, list[int]]
    n_bins: int
    confound_names: list[str]

    @property
    def n_strata(self) -> int:
        return len(self.cells)

    @property
    def is_uniform(self) -> bool:
        """True when no confounds were declared — i.e. the uninformative null."""
        return not self.confound_names

    def describe(self) -> dict:
        sizes = sorted((len(v) for v in self.cells.values()), reverse=True)
        return {
            "confounds": list(self.confound_names),
            "n_strata": self.n_strata,
            "bins_per_confound": self.n_bins,
            "largest_stratum_cells": sizes[0] if sizes else 0,
            "smallest_stratum_cells": sizes[-1] if sizes else 0,
            "window_cells": sum(sizes),
            "uniform_null": self.is_uniform,
        }


def build_strata(
    grid: Grid,
    confound_rasters: dict[str, list[float]],
    n_bins: int = 5,
    mask: list[bool] | None = None,
) -> Strata:
    """Stratify cells by the joint quantile bins of the confound rasters.

    Cells outside `mask` — the observation window — belong to no stratum and receive no
    surrogate mass, because no observation could have come from there.

    With no confounds this collapses to a single stratum: the uniform null. That is
    permitted so the difference can be demonstrated, and the reporting layer is
    required to flag it as uninformative.
    """
    n = grid.n_cells
    in_window = mask if mask is not None else [True] * n

    if not confound_rasters:
        cells = [i for i in range(n) if in_window[i]]
        return Strata(of_cell=[0 if in_window[i] else -1 for i in range(n)],
                      cells={0: cells}, n_bins=n_bins, confound_names=[])

    # Quantile cuts are computed over window cells only, so a large empty margin
    # cannot drag every real cell into the top bin.
    keys = [[] for _ in range(n)]
    for name in sorted(confound_rasters):
        bins = _quantile_bins(confound_rasters[name], n_bins, in_window)
        for i in range(n):
            keys[i].append(bins[i])

    ids: dict[tuple, int] = {}
    of_cell = [-1] * n
    cells: dict[int, list[int]] = {}
    for i, key in enumerate(keys):
        if not in_window[i]:
            continue
        k = tuple(key)
        if k not in ids:
            ids[k] = len(ids)
            cells[ids[k]] = []
        of_cell[i] = ids[k]
        cells[ids[k]].append(i)

    return Strata(of_cell=of_cell, cells=cells, n_bins=n_bins,
                  confound_names=sorted(confound_rasters))


def _quantile_bins(values: list[float], n_bins: int, in_window: list[bool] | None = None) -> list[int]:
    """Assign each cell to a quantile bin of one confound.

    Zero is held out as its own bin. For most confound surfaces — population,
    karst extent, visitation — "none here" is a categorically different state from
    "a little here", and letting it dissolve into the bottom quantile is how a hard
    physical precondition gets smoothed into a soft gradient.
    """
    window = in_window if in_window is not None else [True] * len(values)
    nonzero = sorted(v for v, inside in zip(values, window) if inside and v > 0.0)
    if not nonzero:
        return [0] * len(values)

    cuts = [
        nonzero[min(len(nonzero) - 1, int(len(nonzero) * q / n_bins))]
        for q in range(1, n_bins)
    ]
    out = []
    for v in values:
        if v <= 0.0:
            out.append(0)
            continue
        bin_idx = 1
        for cut in cuts:
            if v > cut:
                bin_idx += 1
        out.append(bin_idx)
    return out


def stratum_totals(raster: list[float], strata: Strata) -> dict[int, float]:
    totals: dict[int, float] = {}
    for i, value in enumerate(raster):
        if value:
            s = strata.of_cell[i]
            if s < 0:  # outside the observation window
                continue
            totals[s] = totals.get(s, 0.0) + value
    return totals


def surrogate(totals: dict[int, float], strata: Strata, rng: random.Random) -> list[float]:
    """One surrogate layer.

    Each stratum's total weight is redistributed uniformly at random over the cells of
    that same stratum. The layer's relationship to its confounds is preserved exactly;
    its position within each confound stratum is randomized. Anything that survives
    this is association not explained by the declared confounds.
    """
    out = [0.0] * len(strata.of_cell)
    for stratum, total in totals.items():
        cells = strata.cells.get(stratum)
        if not cells or total <= 0.0:
            continue
        # Multinomial over the stratum's cells via repeated draws, so the surrogate is
        # a plausible realization rather than a smeared expectation.
        draws = int(round(total))
        if draws <= 0:
            out[rng.choice(cells)] += total
            continue
        unit = total / draws
        for _ in range(draws):
            out[cells[rng.randrange(len(cells))]] += unit
    return out
