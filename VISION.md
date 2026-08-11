# Vision

## What this is

A spatial-inference instrument disguised as a map application.

The visible product is an interactive multi-layer map of North America. The actual product
is the analytical apparatus underneath it: a system that takes a claim of the form *"these
two things occur in the same places"* and answers the only question that matters — *more
often than you'd expect given what else is true about those places?*

## The thesis

Apparent coincidence is the default output of overlaying any two spatially non-uniform
datasets. This is not a flaw in anyone's reasoning; it is a property of geography. Human
settlement, terrain, geology, jurisdiction, and institutional attention are all correlated
with each other, so nearly everything is correlated with nearly everything else at
continental scale.

The interesting question is never *"do these overlap?"* It is *"does the overlap exceed
what the shared confounds already predict?"*

Almost no consumer-facing map tool is built to answer that. The overlay is easy and
compelling; the null model is hard and unglamorous. The result is a genre of map — the
mystery-cluster map — that is rhetorically powerful and epistemically empty.

This app inverts the emphasis. The overlay is the entry point. The null model is the product.

## Why these three layers

They were the originating request, and they turned out to be an unusually good test case,
because they fail in three different ways:

- **Caves** have a hard physical precondition (soluble bedrock) that fully explains their
  distribution at first order. This is the *clean* confound — undeniable, quantifiable, and
  a perfect demonstration of how a base-rate control changes a conclusion.

- **Tribal lands** have a *historical* determinant. Their locations are the residue of
  federal removal and allotment policy, which itself selected for land considered
  marginal — arid, rugged, remote. This is the *structural* confound, and it is the one
  most often laundered into mystical language by people who do not know the history.

- **Missing persons** have a *reporting* determinant. The data is not a record of events;
  it is a record of events that were reported, to an agency with jurisdiction, that
  entered them into a database. Jurisdictional patchwork across tribal, federal, state,
  and provincial policing produces apparent spatial structure that is an artifact of
  who was counting. This is the *measurement* confound, and it is why the MMIWG data
  is included as its own series: the gap between reported and actual is itself the
  documented finding.

Three layers, three distinct classes of confound. If the app handles these correctly, its
machinery generalizes.

## Trajectory

**Near term — make the claim legible.** Ingest the three layers plus their confound layers.
Render the overlay honestly, with evidentiary tier encoded in the visual language. Ship the
sources register. The deliverable is a map that a skeptic and a believer would both agree
is a fair rendering of what the data says.

**Middle term — make the claim testable.** Kernel density estimation per layer. Null models
constructed from the confound stack. Monte Carlo resampling against those nulls. A
correlation panel that reports effect size and uncertainty, not a verdict. The deliverable
is: for any pair or triple of layers, a number with a confidence interval and a plain-language
statement of what it does and does not license.

**Long term — make the method portable.** The three layers are a case study. The general
form is a layer-and-null framework where any user can bring their own claimed coincidence,
declare its confounds, and get an honest answer. Ley lines, UFO sightings, cancer clusters,
crime hotspots, bigfoot reports, cell towers — the analytical question is identical and
the machinery does not care about the subject matter. The deliverable is a tool that makes
it *easy to do this right* and correspondingly awkward to do it wrong.

## Design principles

**Provenance is a type, not a footnote.** A dataset's evidentiary tier travels with it
through ingest, analysis, and render. Tier C data cannot be silently styled like Tier A
data because the render layer will not accept it without an explicit tier-appropriate
symbolization. This is enforced in code, not in a style guide.

**Confounds are mandatory, not optional.** A layer may not be added to the correlation
panel without declaring its confound set. A layer with an empty confound set is a
configuration error.

**The null model is visible.** Users see what chance looks like, not just what the data
looks like. An overlap that fails to beat the null is displayed as failing, prominently,
in the same visual weight as a success.

**Absence is rendered.** Where a jurisdiction does not report, or reports inconsistently,
the map shows a no-data state rather than interpolating across it. Interpolated absence is
how reporting artifacts get promoted to findings.

**Take the claim seriously enough to test it.** This is not a debunking tool. Dismissal and
credulity are the same failure — both skip the measurement. If a claimed cluster survives
the null model, the app says so as clearly as it would say the opposite.

## Non-goals

- Not a *Missing 411* fan project, and not a rebuttal to one.
- Not a general-purpose GIS. It does one analytical thing well.
- Not a case database. It works with published aggregates and public boundary files; it
  does not host individual case records.
- Not a predictive tool. It characterizes observed spatial association. It does not forecast
  where anyone will go missing, and any such use is out of scope and unsupported.
