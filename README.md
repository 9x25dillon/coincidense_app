# Coincidence App

A tool for testing whether apparent spatial coincidence survives contact with base rates.

Bring any two located datasets and the things you think already explain where they occur.
It answers one question: **does the overlap exceed what those confounds already predict?**

Pure Python standard library. No install, no dependencies, no network, no build step.

## Try it in thirty seconds

```bash
python3 examples/make_synthetic.py

# Two layers that both cluster where a third thing is, and are otherwise
# unrelated to each other. The naive test finds a striking association:
python3 -m coincidence test examples/layer_a.csv examples/layer_b.csv

# Declare the thing that actually drives both, and it evaporates:
python3 -m coincidence test examples/layer_a.csv examples/layer_b.csv \
    --confound examples/confound_c.csv --bins 10 --sensitivity
```

The first command reports a large, highly significant association. The second reports
that it was the confound all along. There is no relationship between those two layers —
the generator built them independently — and the difference between those two commands
is the entire reason this project exists.

## The problem it exists to solve

Put three evocative map layers on top of each other and the eye will find a pattern. It
essentially always will. Deep cave systems, tribal lands, and clusters of missing-persons
cases all concentrate in the same kind of country: rugged, sparsely populated, hard to
search, unevenly policed, inconsistently reported. Overlay them and you get overlap. The
overlap is real. What it *means* is a separate question, and the map alone cannot answer
it.

Most tools stop at the overlay — they render the suggestion and let the viewer supply the
inference. This one goes one step further: it states what the overlap would look like
under the null, and shows whether the observed overlap exceeds it.

Not to debunk, and not to confirm. To make the claim *testable* and then actually test it.

## Bring your own data

CSV, TSV, JSON, JSON Lines, GeoJSON. Coordinate columns are auto-detected and can be
named explicitly. Any subject matter — the machinery does not care whether your points
are cave entrances, UFO sightings, cell towers, cancer cases, or bird nests. The
analytical question is identical.

```bash
python3 -m coincidence describe mydata.csv
python3 -m coincidence test sightings.csv towers.csv --confound population.csv
python3 -m coincidence test a.csv b.csv --confound pop.csv --export finding.json
```

Full input contract, output interpretation, and limitations: [`docs/ANY_DATA.md`](docs/ANY_DATA.md).

## What makes it different

**Confounds are the input, not an afterthought.** Without them the engine runs a uniform
null and tells you the answer is close to meaningless. Nothing is uniformly distributed;
against that null nearly everything looks significant.

**Effect size gates the verdict, not the p-value.** Monte Carlo nulls tighten with more
simulations until a 2% deviation reads as p < 0.01. A result needs a 10% effect *and*
p < 0.05 before the tool will call it anything.

**Scale is reported with the number.** Two layers coupled at 5 km read as 4.9x under a
25 km kernel and 1.1x under a 200 km kernel. Both are correct answers to different
questions. `--sensitivity` sweeps grid resolution and bandwidth so one parameter choice
cannot quietly decide your result.

**Negative results are printed.** "No association beyond chance" gets the same prominence
as a positive, because it is equally a finding.

**Provenance is a type.** Every layer carries an evidence tier through ingest, analysis,
and output. Data loads as *uncertain* until you assert otherwise — see
[`docs/EVIDENCE_STANDARDS.md`](docs/EVIDENCE_STANDARDS.md).

**Results are shareable and re-runnable.** `--export` writes a bundle with the inputs,
parameters, null specification, and seed. Someone else can re-run it and disagree
precisely, rather than trading screenshots.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

40 tests, including the executable form of the project's central claim: a confounded
association must collapse when conditioned, a genuine one must survive, and two
independent layers must come back as unrelated. Several were written after the
implementation got those wrong — see [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md#what-went-wrong-on-the-way-here).

## The originating case study

The three-layer North America map this started from — deepest cave systems, tribal
lands, and Missing 411 case clusters — remains the worked example the design documents
are written against. The data has not been ingested; every source in
[`data/sources.yaml`](data/sources.yaml) is marked `verified: false` until a human opens
it and confirms custodian, vintage, license, and access path.

That case study is also why the ethics constraints are structural rather than advisory:
withheld cave entrances stay withheld, tribal boundary categories stay legally distinct,
and no missing person appears on a map by name. See [`docs/ETHICS.md`](docs/ETHICS.md).

## Repository layout

```
coincidence/                the engine
  loading.py                any format in — CSV, JSON, JSONL, GeoJSON
  projection.py             equal-area projection (Albers, cylindrical)
  grid.py                   analysis grid, kernel smoothing, observation window
  nulls.py                  stratified surrogate generation
  analysis.py               co-location statistic, Monte Carlo testing, reporting
  cli.py                    describe / test
docs/
  ANY_DATA.md               input contract, reading results, limitations
  EVIDENCE_STANDARDS.md     tiering and how it's enforced
  METHODOLOGY.md            confounds, null construction, and what went wrong
  DATA_SOURCES.md           narrative register of the case-study datasets
  ETHICS.md                 cave locations, tribal data sovereignty, victim dignity
  ROADMAP.md                phase plan
data/sources.yaml           machine-readable source manifest
examples/                   synthetic worked example
tests/                      the suite
prompts/                    the originating specification
VISION.md                   ambition and trajectory
```

## Status

The engine works and is tested. The North America case-study data is not yet ingested.
See [`docs/ROADMAP.md`](docs/ROADMAP.md).
