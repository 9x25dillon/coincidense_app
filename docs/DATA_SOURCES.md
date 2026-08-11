# Data Sources

Narrative companion to [`../data/sources.yaml`](../data/sources.yaml), which is the
machine-readable register the ingest layer actually reads.

**Nothing here has been verified.** Every entry in the manifest carries `verified: false`.
The URLs and identifiers below were assembled from working knowledge and are a research
starting point, not a validated dependency list. Custodians reorganize their portals,
retire endpoints, and change licensing. Before any source is used, a human must open it and
confirm custodian, vintage, format, license, and access path, then flip the flag and record
who checked it and when.

The ingest layer is specified to refuse `verified: false` sources rather than attempt a
fetch. This is deliberate: an unverified URL that happens to resolve is how a wrong dataset
becomes a silent dependency.

## Speleological

**NSS Long and Deep Cave Lists** — National Speleological Society. The standard reference
for surveyed length and depth in the United States. Note that these are *surveyed* figures
and update continuously as exploration proceeds; a snapshot needs a retrieval date attached.
Access and republication terms need checking, and many entrance coordinates are withheld.

**USGS karst and potential karst mapping** — the conterminous-US karst engineering/geology
compilation (Weary & Doctor, USGS Open-File Report 2014-1156, is the reference to start
from). This is the single most important confound layer in the project, since it defines
where caves can exist at all. Public domain as a federal work product, but confirm.

**International and Mexican systems** — Sistema Sac Actun and Ox Bel Ha in Quintana Roo,
Sistema Huautla in Oaxaca, and the Canadian systems including Castleguard. These sit outside
NSS coverage and require separate national-survey sourcing. Expect the least consistent
metadata here.

**Lava tubes and pseudokarst** — a separate mechanism producing caves in non-soluble rock,
concentrated in the volcanic Pacific Northwest, Hawaii, and central Mexico. Must be a
distinct confound layer from soluble karst; merging them misstates the physical
precondition.

## Tribal lands

**Census TIGER/Line AIANNH** — American Indian, Alaska Native, and Native Hawaiian Areas.
Covers federal and state reservations, off-reservation trust land, Oklahoma Tribal
Statistical Areas, and Alaska Native Village Statistical Areas. Public domain, annual
vintage, well documented. This is the workhorse layer.

**BIA Land Area Representations (LAR)** — Bureau of Indian Affairs. The authoritative
representation of federally recognized tribal land boundaries, and where LAR and TIGER
disagree, LAR is generally the better authority on land status while TIGER is the better
authority on statistical geography. The disagreement itself should be surfaced rather than
resolved silently.

**Canada** — First Nations reserve boundaries via Statistics Canada boundary files and
Crown-Indigenous Relations and Northern Affairs Canada. Distinct legal category from US
reservations; the app must not flatten the two into one symbology without a note.

**Mexico** — comunidades indígenas and ejido lands, via RAN and INEGI. Boundary
availability and consistency are materially weaker than for the US and Canada. Where
authoritative boundaries do not exist, the map renders no-data rather than approximating.

**A caution that belongs in the data layer, not just the ethics doc:** reservation land,
ceded territory, and ancestral or traditional territory are three different geographies
with different legal meanings and wildly different extents. Community-maintained resources
such as Native Land Digital map traditional territory and are valuable, but they answer a
different question than TIGER or LAR and must never be merged into the same layer.

## Missing persons

**NamUs** — National Missing and Unidentified Persons System, NIJ. Case-level public
records. This app works with aggregates, not individual case records; see
[`ETHICS.md`](ETHICS.md).

**FBI NCIC Missing Person and Unidentified Person Statistics** — annual national totals.
Known to undercount, for well-documented structural reasons involving which agencies enter
records and when. Auditable and undercounting are not in tension; both are true.

**National Park Service SAR and incident reporting** — the right denominator source for
park-unit analysis, because it is one of the few contexts where visitor-days are estimated
and a rate rather than a count becomes possible.

**MMIWG series** — the Urban Indian Health Institute's 2018 report on missing and murdered
Indigenous women and girls in urban areas, and the RCMP's 2014 national operational
overview. Carried as its own explicitly labeled series. The central finding of this
literature is a *reporting gap* — cases that do not enter national databases — which makes
it simultaneously a data layer and a confound on the layer it sits inside.

**Canadian Centre for Missing Persons and Unidentified Remains** — RCMP. The Canadian
counterpart, with its own reporting regime, which is precisely why the border is a
discontinuity that must be modeled rather than smoothed across.

## Missing 411

**Source:** the published *Missing 411* books by David Paulides.

**Tier C.** There is no accompanying open dataset. The books describe cases and identify
geographic clusters, but there is no published case list, no stated inclusion or exclusion
criteria, no denominator, and no reproducible path from public records to the clusters as
drawn. Any cluster geometry in this app is therefore a *transcription of an assertion*,
carrying a page-level citation to where the assertion appears, and is rendered as such.

Two consequences follow, and both are structural rather than editorial:

Without inclusion criteria there is no denominator, so no rate can be computed and no
conventional significance test applies. Effect sizes involving this layer are descriptive
only, and the interface must say so at the point of display rather than in a footnote.

Because the clusters were identified by a process that is not specified, the possibility
that selection tracked the confounds — rugged terrain, park land, low recovery probability —
cannot be excluded from the data alone. The app's job is to show what the confound stack
predicts and let the reader see how much of the pattern is already accounted for. That is
a more useful contribution than either endorsement or dismissal.

## Base and confound layers

Terrain and ruggedness from USGS 3DEP and NRCan CDEM. Population from Census and
Statistics Canada and INEGI. Protected-area extent from the USGS Protected Areas Database.
Land cover and forest canopy for search-difficulty modeling. Jurisdictional boundaries for
policing and reporting regime.

These are not decoration. They are the null model's inputs, and the analysis will not run
without them.
