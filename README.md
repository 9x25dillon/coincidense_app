# Coincidence App

A tool for testing whether apparent spatial coincidence survives contact with base rates.

## The problem it exists to solve

Put three evocative map layers on top of each other and the eye will find a pattern.
It essentially always will. Deep cave systems, tribal lands, and clusters of missing-persons
cases all concentrate in the same kind of country: rugged, sparsely populated, hard to
search, unevenly policed, and inconsistently reported across jurisdictions. Overlay them
and you get overlap. The overlap is real. What it *means* is an entirely separate question,
and the map alone cannot answer it.

Most tools in this space stop at the overlay — they render the suggestion and let the
viewer supply the inference. This one is built to go one step further: to state what the
overlap would look like under the null hypothesis, and to show whether the observed
overlap exceeds it.

That is the whole ambition. Not to debunk, and not to confirm. To make the claim *testable*
and then actually test it.

## The three layers

| Layer | What it shows | Evidentiary tier |
|---|---|---|
| **Speleological** | Documented cave systems by surveyed depth and length, over karst/soluble-bedrock extent | Tier A — surveyed, published |
| **Tribal lands** | Reservations, trust lands, statistical areas, and Canadian reserves | Tier A — authoritative government boundary files |
| **Missing persons** | Agency missing-person incidence, MMIWG series, and separately, the "Missing 411" clusters | Tier A and Tier C — **not merged** |

The third layer is deliberately split. Agency data (NamUs, NCIC, NPS SAR, RCMP) and
author-asserted cluster locations from the *Missing 411* books are different kinds of
object with different provenance, and the app renders them as different kinds of object.
See [`docs/EVIDENCE_STANDARDS.md`](docs/EVIDENCE_STANDARDS.md) for the tiering rules and
why they are enforced in the type system rather than left to the cartographer's judgment.

## The methodological commitment

Every layer in this app carries its confounds with it. Cave presence is a function of
lithology before it is a function of anything else — you cannot have a cave without soluble
bedrock, so any cave-related clustering must be tested against karst extent, not against
uniform space. Missing-person counts track population and visitation before they track
anything mysterious. Reservation boundaries are the outcome of a specific and documented
history of federal land policy, not a natural feature of terrain.

The app therefore ships the confound layers as first-class citizens, not as optional
context. A correlation panel that cannot control for karst extent, population density,
visitor-days, terrain ruggedness, and reporting-regime boundaries is not a correlation
panel; it is a coincidence generator with a legend.

## Status

Pre-implementation. This repository currently holds the specification, the data-source
register, the evidence standards, and the roadmap. No data has been ingested and no
map has been rendered. Every source in [`data/sources.yaml`](data/sources.yaml) is marked
`verified: false` until a human has opened it and confirmed the custodian, vintage, license,
and access path. That flag is load-bearing — the ingest layer is specified to refuse
unverified sources rather than fetch them optimistically.

See [`VISION.md`](VISION.md) for where this is going and [`docs/ROADMAP.md`](docs/ROADMAP.md)
for the phase plan.

## Repository layout

```
VISION.md                       ambition and trajectory
docs/
  EVIDENCE_STANDARDS.md         tiering, provenance, and how they're enforced
  METHODOLOGY.md                confounds, null models, spatial statistics plan
  DATA_SOURCES.md               narrative register of every dataset
  ROADMAP.md                    phased build plan
  ETHICS.md                     cave locations, tribal data sovereignty, victim dignity
data/
  sources.yaml                  machine-readable source manifest
prompts/
  three-layer-north-america-map.md   the originating specification prompt
```

## Origin

This repository was cemented from a working session that started as a request for a
three-layer overlay map of North America and turned into an argument about what such a
map would actually be evidence of. The originating prompt is preserved verbatim in
[`prompts/three-layer-north-america-map.md`](prompts/three-layer-north-america-map.md).
