# Bring your own data

The engine does not care what your data is about. It cares that each observation has a
location and that you can say what else drives where those locations are.

## Supported inputs

CSV, TSV, semicolon- or pipe-delimited text, JSON (an array of objects, or an object
wrapping one), JSON Lines / NDJSON, and GeoJSON.

Coordinate columns are detected automatically from the usual names — `lat`/`latitude`/
`y`/`decimalLatitude`, `lon`/`lng`/`long`/`longitude`/`x`, and others. When detection
fails the loader raises rather than guessing, and the error shows you what the file
actually holds — every column with a sample value from the first row — so you can name
the right ones without a second look:

```bash
python3 -m coincidence describe mydata.csv
python3 -m coincidence describe mydata.csv --lat POINT_Y --lon POINT_X
```

`--lat`, `--lon` and `--weight` apply to both tested layers. When your files disagree
about naming, override per layer: `--lat-a`/`--lon-a`/`--weight-a` for layer A,
`-b` for layer B, and `-c` for every confound.

```bash
python3 -m coincidence test cases.csv towers.geojson \
    --lat-a CASE_LAT --lon-a CASE_LON \
    --confound census.csv --weight-c POP2020
```

Confound layers take weights too, which matters more than it sounds: a population
confound is a set of place coordinates weighted by how many people live there, and
unweighted it says only "somebody lives here".

GeoJSON polygons collapse to the mean of their exterior ring. That is a real
simplification — a whole county becomes one dot — and it is recorded rather than hidden.
Areal support is roadmap work.

Rows without usable coordinates are dropped and **counted**, never imputed. The count
appears in the layer's provenance and in every exported bundle. Out-of-range values and
(0, 0) are treated as failed geocodes rather than observations in the Gulf of Guinea.

## The one thing you have to supply

**Confounds.** What else explains where your observations are?

This is the entire difference between this tool and a scatter plot. Without confounds
the engine runs against a uniform null — the assumption that observations could have
landed anywhere with equal probability — and reports, loudly, that the answer is close
to meaningless. Nothing on Earth is uniformly distributed. Against that null almost
everything looks significant, which is why so many overlay maps look so convincing.

```bash
# Uninformative: no confounds. The tool will say so.
python3 -m coincidence test sightings.csv towers.csv

# The real question: does the association survive population?
python3 -m coincidence test sightings.csv towers.csv --confound population.csv

# Multiple confounds, repeat the flag.
python3 -m coincidence test a.csv b.csv \
    --confound population.csv --confound roads.csv --confound landcover.csv
```

A confound layer is just another located dataset: points wherever the confounding thing
is, optionally weighted with `--weight`. Population counts by place, road intersections,
karst outcrops, park visitor centres — anything that describes where observation was
possible or likely.

## Reading the output

```
  observed co-location : 3.8073
  expected under null  : 3.5011  (95% of nulls fall in 3.3911 .. 3.6418)
  effect ratio         : 1.087x
  p-value              : 0.0050
```

**The effect ratio is the answer.** 1.0 means the layers are exactly as co-located as
the confounds already predict. 2.0 means twice as much. 0.5 means they actively avoid
each other, which is as real a finding as clustering.

**The p-value is not the answer.** Monte Carlo nulls tighten as simulations increase, so
with enough of them a 2% deviation shows p < 0.01. The engine therefore requires an
effect of at least 10% *and* p < 0.05 before it will call anything a result — 4% once you
declare a study boundary with `--boundary`. Below that
it says so explicitly, because a small p on a trivial effect is a property of the
simulation count, not evidence.

**Always report the bandwidth with the ratio.** Layers coupled at 5 km read as 4.9x
under a 25 km kernel and 1.1x under a 200 km kernel. Both numbers are correct answers to
different questions. Set it directly with `--bandwidth-km`, or let the stated rule pick
one from your sample size.

`--sensitivity` sweeps grid resolution and bandwidth separately, each holding the other
fixed, so a single parameter choice cannot silently decide your result — and so the two
sweeps cannot be confused for each other. A conclusion that moves across *cell sizes* is
a resolution artifact and should be discarded. A conclusion that moves across
*bandwidths* is information about the scale at which your layers are coupled, and should
be reported with the scale attached.

**Both directions are run.** The null resamples one layer and holds the other fixed, and
that is a different test depending on which one moves. The tool runs it both ways and
reports the conservative answer, so the result cannot depend on the order you typed the
files in. Both appear in the exported bundle. `--one-way` skips the second direction if
you need the speed and accept the order-dependence.

## Declare your study region

```bash
python3 -m coincidence test a.csv b.csv --confound pop.csv --boundary watershed.geojson
```

A GeoJSON Polygon or MultiPolygon, holes included, describing where an observation could
have occurred at all — a watershed, a county, a survey extent, a park, a coastline-clipped
land area. Several polygons in one file are fine; they are taken together.

**This is the highest-value flag in the tool, and on some geometries it is not optional.**
Without it the window is the convex hull of your points. For a roughly convex study area
that is close enough. For a concave one it is not close at all: measured on a crescent,
two layers scattered *independently* inside it come back at **1.31×** — a confident false
positive at three times the 10% floor built to suppress exactly that. With the real
boundary declared, the same data reads **1.005×**.

| window | mean effect on independent layers | worst deviation |
|---|---|---|
| inferred convex hull | 1.307× | 33.4% |
| declared boundary | 1.005× | 1.9% |

Coastlines, valley floors, river corridors, mountain arcs and anything with a lake in it
are all that shape. The tool measures how much of an inferred window is reached by no
observation at all and warns above 5%, but the warning is a prompt to supply the
boundary, not a substitute for it.

Three things change when you declare one:

- **The noise floor drops from 10% to 4%**, because the hull over-coverage that the
  higher floor was paying for is gone. A 5% effect becomes reportable.
- **The grid is cut to the boundary** rather than to the data, so a confound file
  covering half a continent no longer drags the analysis extent out with it.
- **Observations outside the region are dropped and counted.** The null can only draw
  surrogates from inside the window, so an outside point left in place would smooth into
  the window and inflate the observed statistic while contributing nothing to the null.
  A point outside your study region is either a bad coordinate or evidence the boundary
  is wrong, and the tool tells you how many there were rather than absorbing them.
  Confounds are exempt — they never contribute mass to the null, only shape to the
  surface, and a city just over the line genuinely does inform the intensity at the edge.

## Seeing it

```bash
python3 -m coincidence test a.csv b.csv --confound pop.csv --report finding.html
```

One self-contained HTML file — no network, no assets, no build step — with the verdict,
the null distribution in ratio units, both directions of the test, the sensitivity
sweeps, the provenance of every input, and the analysis surfaces themselves: layer A,
layer B, each confound, and **one draw from the null** rendered beside them in the same
colour ramp as A.

That last panel is the one to look at. If the real layer A and a random draw from its
null are hard to tell apart, you are looking at why the ratio came back near 1. Each
panel is one pixel per analysis cell at the resolution the statistic actually used, so
the grid is visible rather than smoothed into a plausible-looking continuous field, and
three states are drawn distinctly: outside the observation window (not analysed, not
drawn), inside it with no observation reaching (flat grey), and inside it with intensity
(the ramp).

## Sharing a result

```bash
python3 -m coincidence test a.csv b.csv --confound pop.csv --export finding.json
```

The bundle carries the inputs and their provenance, every parameter, the null
specification, the random seed, and the result. Anyone with the same files can re-run it
and get the same numbers — or change the confound set and show you why you were wrong.
The HTML report embeds the same bundle in a `<script type="application/json">` tag, so a
report that arrives by email can still be re-run.

That last part is the point. A claim that comes with its null model attached is a claim
someone can argue with precisely, instead of trading screenshots.

## What the tool will not do

- **Infer provenance.** Every layer loads as tier D, uncertain, until you declare
  otherwise with `--tier-a` / `--tier-b`. Claiming your data is authoritative is your
  assertion to make, not something a filename earns.
- **Guess coordinates.** Ambiguous columns raise an error.
- **Interpolate across missing data.** No-data stays no-data.
- **Say anything causal.** The engine measures spatial association. It cannot
  distinguish mechanism, direction, or cause, and its output text never implies it can.
- **Hide a negative result.** "No association beyond chance" is printed with the same
  prominence as a positive, because it is equally a finding.

## Known limitations

**The observation window is inferred unless you declare one.** Absent `--boundary`, the
engine uses the convex hull of your points, which over-covers any concave region. On a
mildly concave extent that costs a few percent, which is where the 10% floor comes from.
On a strongly concave one — a crescent, a coastline, a river corridor — it costs 31%, and
the floor does not save you. Declare the boundary.

**Polygons become points.** See above.

**Ecological inference.** Association between areas does not transfer to individuals.
Two layers co-locating in the same cells does not mean the same individuals are involved.

**Confounds you didn't declare.** The engine can only condition on what you give it. An
unmeasured confound remains the most likely explanation for any residual association,
and the output says so every time it reports one. This is not false modesty. It is the
single most common reason a spatial finding turns out to be nothing.
