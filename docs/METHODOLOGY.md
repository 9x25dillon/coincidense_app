# Methodology

## The core question

Given two or more spatial layers that appear to co-locate, does the observed co-location
exceed what the shared confounds already predict?

Everything below is machinery for answering that without cheating in either direction.

## Why the naive overlay is uninformative

At continental scale, most human and physical geography is correlated with terrain,
population, and jurisdiction. Two arbitrary layers drawn from that world will overlap.
The overlap statistic against a *uniform* null — the implicit null when someone eyeballs
a map — is almost guaranteed to be significant and almost never meaningful.

The uniform null asks: "would these coincide if events were scattered evenly across the
continent?" Nothing is scattered evenly across the continent. The answer is always no,
and the finding is always spurious.

The correct null is *conditional*: would these coincide at this rate given karst extent,
population density, visitation, terrain ruggedness, and reporting regime? That null is
harder to construct, and constructing it is most of the work of this project.

## The confound stack

Each layer declares its confounds. A layer with no declared confounds cannot enter the
correlation panel — that is a configuration error, not a permissive default.

### Caves

- **Soluble bedrock extent.** The hard precondition. Cave density outside karst,
  pseudokarst, and lava-tube terrain is near zero for reasons that have nothing to do with
  anything else on the map. This is the dominant term.
- **Exploration effort.** Surveyed length measures *survey*, not cave. Mammoth is the
  longest known system partly because it has been continuously surveyed for over a century.
  Length data is confounded by caver-hours in a way that depth data is somewhat less so.
- **Access and disclosure.** Many entrances are deliberately unpublished. Absence in the
  dataset is not absence in the ground.

### Tribal lands

- **Federal land policy history.** Reservation locations are the outcome of removal,
  allotment, and termination-era policy. The selection pressure was toward land considered
  economically marginal at the time of assignment — which correlates with aridity,
  ruggedness, and remoteness. This is a historical process with a documented record, and
  it explains a large share of the spatial pattern.
- **Boundary definition.** Reservation, off-reservation trust land, statistical area, ceded
  territory, and ancestral territory are five different geographies. Conflating them
  inflates apparent extent by a wide and inconsistent margin.
- **Population density.** Tribal lands are disproportionately in low-density counties,
  which independently drives search difficulty and reporting behavior.

### Missing persons

- **Population and visitation.** Raw counts reproduce a population map. Normalization by
  resident-population and, for park units, by visitor-days is mandatory before any spatial
  claim.
- **Reporting regime.** Jurisdictional patchwork across tribal, BIA, federal, state,
  county, and provincial policing determines whether a case enters a national database at
  all. Apparent spatial structure may be a map of *record-keeping*, not of events. The
  documented MMIWG reporting gap is the clearest instance.
- **Search difficulty and recovery probability.** A person lost in rugged, forested,
  karst-riddled terrain is less likely to be found, so cases in that terrain stay open
  longer and are overrepresented in any snapshot of *currently missing*. This mechanism
  alone predicts a cave-terrain correlation with no additional explanation required, and
  it must be explicitly modeled before any residual is interpreted.
- **Case-status dynamics.** Open-case counts are a stock, not a flow. Comparing stocks
  across regions with different clearance rates measures clearance, not incidence.

## Analytical pipeline

**1. Normalize.** Reproject all layers to Albers Equal Area Conic (NAD83). Area-based
statistics on a Mercator basemap are wrong by a factor that varies with latitude, which
across an Alaska-to-Yucatán extent is not a rounding error.

**2. Rasterize to a common grid.** Analysis operates on a fixed equal-area cell grid so
that polygon layers, point layers, and continuous surfaces are commensurable. Cell size is
a declared parameter and results are reported across several cell sizes, because the
modifiable areal unit problem is not optional here — cluster findings that appear at one
resolution and vanish at another are resolution artifacts and must be reported as such.

**3. Estimate intensity.** Kernel density per layer, bandwidth selected by a stated rule
rather than by eye, since bandwidth choice can manufacture or dissolve a cluster.

**4. Build the conditional null.** Generate surrogate layers that preserve the confound
structure while destroying the hypothesized association — resampling points within strata
defined by the confound stack rather than uniformly across space. This is the step the
genre skips.

**5. Test.** Monte Carlo comparison of observed co-location against the surrogate
distribution. Report effect size with a confidence interval.

**6. Report honestly.** Output is an effect size, an interval, the null model's
specification, and a plain-language statement of what the result licenses. Not a verdict.
A result that fails to beat the null is displayed with the same prominence as one that
beats it.

## Reporting rules

- Every statistic names its null model. "Significant" without a stated null is meaningless
  and is treated as a defect.
- Sensitivity to bandwidth, cell size, and confound specification is reported alongside the
  headline number, not buried.
- Negative results are rendered. A layer pair that shows no residual association after
  controls is a finding and is displayed as one.
- No causal language anywhere in the output surface. This pipeline measures spatial
  association. It cannot distinguish mechanism, and the interface must not imply otherwise.

## What went wrong on the way here

Four defects surfaced while building the engine, each of which would have produced
confident false positives. They are recorded because they are the exact failures this
project accuses the overlay-map genre of, and finding them in our own implementation is
the strongest available argument that the discipline is necessary rather than decorative.

**Double-smoothed nulls.** Surrogates were resampled from the already-smoothed raster
and then smoothed again, while the observation was smoothed once. The null came out
flatter than it should have been, and every effect size was inflated. Fixed by drawing
surrogates from raw counts so both paths get exactly one smoothing pass.

**A rectangular observation window.** The analysis grid is a rectangle; the region data
actually occupies is not. For a projected lon/lat box, roughly three quarters of the
grid was territory no observation could have come from. The null scattered surrogates
into that void, making real data look concentrated together. Two independent layers came
back at 1.23x, p = 0.01.

**A window selected on the layers under test.** The first fix took the union of the two
tested layers' occupied cells as the window. That is selection on the outcome: a cell
enters the window because layer A is there *or* layer B is there, so within the window
the two are positively associated by construction. It halved the artifact rather than
removing it — independent layers still read 1.10x. Fixed by using the convex hull of all
points, a coarse global boundary rather than a per-cell selection.

**Uncorrected kernel truncation at the boundary.** A kernel centred near the window edge
spills mass outside, and that mass was simply lost — depleting intensity near the edge
identically for every layer, which correlates them all with each other for no reason but
geometry. Fixed by dividing through by the smoothed window indicator, so each cell is
rescaled by the fraction of its kernel that stayed inside.

After all four, two independent layers read 1.02x — and that residual is why the noise
floor exists.

## The noise floor

A result must show at least a 10% deviation from the null *and* p < 0.05 before the tool
will call it anything.

The p-value alone is not enough, and this is not a stylistic preference. Monte Carlo
nulls tighten without bound as simulations increase, so with enough of them a 2%
deviation registers as p < 0.01. Two percent is inside this method's own systematic
error, because an inferred convex-hull window over-covers any concave study region.
Reporting that as a finding would be precisely the failure this tool exists to prevent,
merely dressed in a p-value.

Supplying a real study boundary instead of an inferred one would lower the floor. Until
then, honesty requires it.

## Bandwidth is the question, not a parameter

Kernel bandwidth sets the spatial scale at which co-location is being interrogated. Two
layers coupled at 5 km read as 4.9x under a 25 km kernel and 1.1x under a 200 km kernel.

Neither number is wrong. They are answers to different questions — "are these together
at neighbourhood scale?" versus "are these together at regional scale?" — and a ratio
reported without its bandwidth is not interpretable.

This is why the sensitivity sweep covers bandwidth as well as cell size, and why the two
sweeps carry different warnings. A conclusion that flips with *cell size* is a resolution
artifact and should be discarded. A conclusion that changes with *bandwidth* is usually
real information about the scale of the coupling, and should be reported as such.

## Known limitations to state up front

- Ecological inference: area-level association does not transfer to individuals.
- Edge effects at the US–Canada and US–Mexico borders, where reporting regimes change
  discontinuously and datasets are not harmonized.
- Temporal misalignment: layer vintages differ by years to decades. Cave surveys accumulate
  continuously, boundary files update irregularly, case data is annual.
- Tier C inputs have no denominator, so effect sizes involving them are bounded by an
  unknown selection process and should be read as descriptive, not inferential.
