# Roadmap

Phases are ordered by dependency, not by calendar. Each phase states its deliverable and
the condition under which it is done.

**Where things actually stand:** the general engine (originally Phase 5) was pulled
forward and built first. Phases 1–3 — verifying the North America sources, ingesting
them, and rendering the map — are the remaining work. Building the analytical core
before the case study turned out to be the right order: it forced the confound
machinery to be general, and it surfaced four false-positive-generating defects on
synthetic data where ground truth was known, rather than on real data where it isn't.

## Phase 0 — Specification (current)

Cement the intent before writing ingest code, so the epistemic commitments are load-bearing
rather than retrofitted.

- [x] README, vision, and trajectory
- [x] Evidence tiering and its enforcement points
- [x] Methodology: confound stack, null-model construction, reporting rules
- [x] Ethics: cave locations, tribal data sovereignty, victim dignity
- [x] Source register with every entry marked unverified
- [ ] Technology selection (see open questions)

**Done when:** a contributor can read this repo and correctly predict what the app will
refuse to do.

## Phase 1 — Source verification

Turn the research-grade register into a validated dependency list.

- [ ] Open every source in `data/sources.yaml`; confirm custodian, vintage, format,
      license, and access path
- [ ] Record verifier and date; flip `verified` to true only for confirmed entries
- [ ] Remove or replace entries that no longer resolve
- [ ] Resolve licensing for NSS-derived data and any non-public-domain source
- [ ] Document which cave entrance coordinates are withheld and honor that downstream

**Done when:** every `verified: true` entry has been opened by a human, and no unverified
entry is referenced by ingest.

## Phase 2 — Ingest and normalization

- [ ] Source-manifest loader that refuses unverified entries
- [ ] Fetch and cache with retrieval-date stamping
- [ ] Reprojection to Albers Equal Area Conic (NAD83)
- [ ] Rasterization to a parameterized equal-area analysis grid
- [ ] Tier propagation through the transformation chain
- [ ] Explicit no-data regions where jurisdictions do not report

**Done when:** all three layers plus the confound stack load into a common grid, with tier
and provenance intact and no-data preserved rather than interpolated.

## Phase 3 — Honest overlay

The first thing a user can look at.

- [ ] Interactive map, self-contained, layer toggles
- [ ] Tier-locked symbology (Tier C cannot render as Tier A)
- [ ] Legend that names custodian and tier per entry
- [ ] Per-feature provenance tooltips
- [ ] Sources-and-limitations panel rendered from the manifest, not hand-written
- [ ] Confound layers displayable alongside their dependent layer

**Done when:** a skeptic and a believer both agree it is a fair rendering of the data.

## Phase 4 — The null model

The actual product.

- [ ] Kernel density per layer with a stated bandwidth-selection rule
- [ ] Stratified surrogate generation preserving the confound structure
- [ ] Monte Carlo co-location testing against surrogates
- [ ] Effect sizes with confidence intervals
- [ ] Sensitivity reporting across bandwidth and cell size (MAUP)
- [ ] Null-model visualization — users see what chance looks like
- [ ] Plain-language result statements, including for negative results

**Done when:** for any layer pair or triple, the app returns an effect size, an interval,
the null specification, and a statement of what it does and does not license — and displays
a failure to beat the null as prominently as a success.

## Phase 5 — Generalization (built first)

- [x] User-supplied layers in CSV, TSV, JSON, JSON Lines, GeoJSON
- [x] Coordinate auto-detection with explicit override; unparseable rows dropped and counted
- [x] Equal-area projection chosen automatically from the data's extent
- [x] Stratified surrogate nulls conditioned on user-declared confounds
- [x] Monte Carlo co-location testing with effect size and interval
- [x] Effect-size floor gating the verdict, not the p-value alone
- [x] Sensitivity sweeps over grid resolution and bandwidth
- [x] Tier propagation from ingest through to output
- [x] Reproducible export bundle: inputs, provenance, parameters, null spec, seed
- [x] Worked synthetic example where the confounded association demonstrably evaporates
- [x] Test suite, including the project's central claim as an executable assertion
- [ ] User-supplied study boundary, to replace the inferred convex-hull window
- [ ] Areal support for polygons instead of collapsing them to representative points
- [ ] Confound declaration enforced as a required step rather than a strong default

**Done when:** someone can bring an unrelated claimed coincidence and get an honest answer
without modifying the codebase. *Substantially met* — the remaining items lower the
noise floor and widen the geometry support rather than adding capability.

## Open questions

**Stack.** Python analysis (GeoPandas, rasterio, PySAL, scipy) with a web render layer is
the obvious default and PySAL in particular covers most of Phase 4. The alternative is
doing more in the browser for a fully self-contained artifact. Decision deferred until
Phase 2 data volumes are known.

**Precomputation boundary.** Monte Carlo surrogate testing is not interactive-speed at
continental scale and fine resolution. Either results are precomputed for a fixed parameter
grid and the UI interpolates between them, or the analysis runs server-side on request.
This choice constrains the stack decision above.

**Distribution.** Static site with precomputed results is cheapest and most durable and fits
the reproducibility goal. A live service enables Phase 5 user-supplied layers. These may
end up being two artifacts rather than one.

**Cross-border harmonization.** US, Canadian, and Mexican sources differ in vintage,
resolution, and definition. Whether to harmonize or to analyze per-jurisdiction and compare
is unresolved, and it materially affects Phase 4 since the border is itself a reporting
discontinuity that the null model needs to represent.
