# Originating prompt: three-layer North America overlay

This is the specification that started the project, preserved verbatim. The design
documents in `docs/` are the elaboration of the commitments embedded here — particularly
the split third layer, the mandatory confound handling, and the requirement that
evidentiary status be visible in the rendering rather than stated in a footnote.

The original one-line request was:

> Can you generate a data map over three overlayed sets, the deepest cave systems, the
> native American reservation locations, and the 411 missing people cases statistics of the
> north american continent

Elaborated into the following specification:

```
Build an interactive, multi-layer choropleth-and-point map of North America
(CONUS, Alaska, Canada, and northern Mexico) that renders three independent,
individually toggleable data layers over a shared basemap, so spatial
coincidence between them can be inspected visually and tested statistically.

BASEMAP AND PROJECTION
- Use a conformal or equal-area projection appropriate to continental extent
  (Albers Equal Area Conic, NAD83, is preferred for area-honest comparison;
  state Web Mercator explicitly if you use it instead).
- Include a muted terrain/hillshade or karst-geology base so the cave layer
  has physical context. Keep basemap contrast low so the three layers read
  clearly on top of it.

LAYER 1 — DEEP AND LONG CAVE SYSTEMS
- Plot documented cave systems by both maximum surveyed depth (meters below
  entrance) and total surveyed length (kilometers), symbolized separately so
  the two dimensions aren't conflated.
- Source from the NSS Long and Deep Cave Lists, the Speleological Survey /
  national karst inventories, and USGS karst-terrain mapping.
- Include at minimum: Mammoth Cave, Jewel Cave, Wind Cave, Lechuguilla,
  Carlsbad, Sistema Sac Actun / Ox Bel Ha (Yucatán), Sistema Huautla (Oaxaca),
  Castleguard (Alberta), and the major Appalachian and Ozark systems.
- Underlay a karst/soluble-bedrock extent polygon layer, since cave presence is
  a function of lithology and this is the primary confound for any apparent
  clustering.
- Note explicitly where entrance coordinates are deliberately obscured or
  withheld for conservation and access reasons.

LAYER 2 — TRIBAL LANDS AND RESERVATIONS
- Render federally recognized reservation boundaries, off-reservation trust
  lands, Oklahoma Tribal Statistical Areas, and Alaska Native Village
  Statistical Areas from the Census Bureau AIANNH TIGER/Line shapefiles and
  BIA Land Area Representations (LAR).
- For Canada, include First Nations reserves from Statistics Canada / Crown-
  Indigenous Relations boundary files; for Mexico, include comunidades
  indígenas / ejido lands where authoritative boundaries exist.
- Represent these as polygons with clear labeling of nation/tribe names as
  self-identified. Distinguish reservation land from ceded territory and from
  broader ancestral/traditional territory — these are three different things
  and conflating them is a substantive error, not a cartographic nicety.

LAYER 3 — MISSING PERSONS
- Present two clearly separated sublayers, and do not merge them:
  (a) VERIFIABLE BASELINE: missing-persons incidence from NamUs, the FBI NCIC
      annual missing-person statistics, NPS incident and SAR reporting, and
      the Canadian Centre for Missing Persons. Normalize by visitor-days or
      population where possible so raw counts don't simply reproduce a
      population/visitation map. Include the MMIWG data (Urban Indian Health
      Institute, NCIC, RCMP) as its own clearly labeled series, given it is a
      documented and separately studied phenomenon with real jurisdictional
      reporting gaps.
  (b) "MISSING 411" CLUSTERS: the cluster locations described in David
      Paulides' published work. Label this sublayer explicitly as
      author-asserted, derived from books rather than from an open,
      auditable case database, with no published case list, inclusion
      criteria, or peer review. Style it visually distinct (e.g., outlined
      rather than filled) so it is never mistaken for the agency data in (a).
      Do not present it as equivalent evidence.

ANALYSIS AND HONESTY REQUIREMENTS
- Provide a spatial-correlation panel: kernel density estimates per layer,
  plus a test of whether the overlap between layers exceeds chance given the
  underlying population, land-area, visitation, and karst-extent distributions.
- Explicitly address the base-rate problem: wilderness areas, national parks,
  karst terrain, and tribal lands all covary with terrain ruggedness, low
  population density, and search-and-rescue difficulty. Any apparent
  three-way overlap most likely reflects those shared confounds. State this
  in the map's own explanatory text, not just in the notes.
- Cite every dataset with its name, custodian, vintage, and access URL.
- Where a layer's data is unavailable, incomplete, or reported inconsistently
  across jurisdictions, say so on the map rather than interpolating.

OUTPUT
- A self-contained interactive HTML map with a layer toggle, per-feature
  tooltips, a legend distinguishing the evidentiary status of each layer, and
  a sources-and-limitations section.
```

## The note that turned this into a project

The observation attached to the prompt, which became the app's thesis:

> If you strip the tiering out, whatever comes back will imply a three-way correlation that
> the underlying data doesn't support — cave systems and reservations both sit
> disproportionately in rugged, sparsely populated terrain where people go missing and are
> hard to find, which is enough to produce the overlap on its own.

The app exists to make that sentence testable rather than merely assertable.
