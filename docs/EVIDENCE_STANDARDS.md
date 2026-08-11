# Evidence Standards

Every dataset entering this system carries an evidentiary tier. The tier is assigned at
ingest, travels with the data through analysis, and constrains how the render layer is
permitted to display it.

This exists because the failure mode of overlay maps is not bad data — it is *good data
and bad data drawn in the same ink*. A reader cannot distinguish a surveyed cave entrance
from an author's assertion about where something happened if both are rendered as a red dot.

## The tiers

### Tier A — Instrumented or authoritative

Data produced by a custodian with a mandate, a documented collection method, and a
published product. The custodian can be named, the vintage is known, and the methodology
is inspectable.

Examples: USGS karst extent mapping. Census TIGER/Line AIANNH boundary files. BIA Land
Area Representations. NSS surveyed cave length and depth. FBI NCIC annual missing-person
totals. NamUs case aggregates. Statistics Canada boundary files.

Tier A is not "true." It is *auditable*. NCIC counts are Tier A and are also known to
undercount substantially — that is a documented property of an auditable source, which is
exactly the point.

### Tier B — Derived, modeled, or secondary

Analysis products built on Tier A inputs, where the transformation is published and the
inputs are traceable. Peer-reviewed studies, agency reports that synthesize primary data,
academic reconstructions.

Examples: the Urban Indian Health Institute MMIWG analysis. RCMP operational overviews.
Published SAR-incidence studies normalizing by visitor-days. Any KDE surface this app
itself generates.

Tier B inherits the constraint that its provenance chain must terminate in Tier A. A
derived product whose inputs cannot be identified is not Tier B; it is Tier C.

### Tier C — Asserted

A claim published without an accompanying open dataset, inclusion criteria, or
reproducible method. The assertion may be sincere, well-researched, and correct. It is
still not auditable, and the distinction is what the tier records.

The *Missing 411* cluster locations are Tier C. The books describe cases and identify
geographic clusters, but there is no published case list, no stated inclusion or exclusion
criteria, no denominator, and no independent path to reconstruct the clusters from source
records. Assigning Tier C is a statement about the availability of the evidence, not about
the sincerity or the correctness of the author.

Tier C data is welcome in this app. It is the interesting input. It simply may not
masquerade as Tier A.

### Tier D — Uncertain provenance

Crowdsourced, scraped, aggregated-from-unknown, or otherwise unattributable. Accepted only
into an explicitly quarantined workspace, never into the default map, never into the
correlation panel.

## Enforcement

Tier is not a documentation convention. It is enforced at three points:

**Ingest.** A source record without a `tier` field fails validation. A source with
`verified: false` will not be fetched — the ingest layer refuses rather than proceeding
optimistically, so an unverified URL cannot quietly become a data dependency.

**Analysis.** The correlation panel refuses to compute a statistic that mixes tiers into a
single series. Cross-tier comparison is permitted and is in fact a primary use case, but
the tiers must remain distinguishable in the output.

**Render.** The symbolization system is keyed on tier. Tier A gets filled marks. Tier B
gets filled marks with a derived-product indicator. Tier C gets outlined marks, a hatch
fill, and a persistent inline label naming the assertion's source. There is no code path
that renders Tier C with Tier A symbology, and adding one should be treated as a defect
rather than a feature request.

## The legend requirement

The map legend must distinguish evidentiary status, not just visual encoding. A legend
that explains what red means but not what red *is* has failed at the app's central job.

Every legend entry names the custodian and the tier. A user who screenshots the map and
posts it without context should still be transmitting the provenance, because the
provenance is drawn into the image.

## On not being a debunking tool

Tiering is frequently mistaken for dismissal. It is not.

The reason to mark *Missing 411* as Tier C is not to wave it away — it is to make it
possible to test. An assertion held at arm's length with its provenance labeled can be
compared against a null model and either survive or not. An assertion blended into agency
data can never be tested at all, because it has already been granted the conclusion.

Tier C is how a claim gets taken seriously. It is the opposite of a dismissal.
