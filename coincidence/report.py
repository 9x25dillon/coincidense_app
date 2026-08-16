"""A self-contained HTML report.

The tool's own design principles say the null model should be visible and that absence
should be rendered. Both were unmet while the only output was a paragraph of text: a
spatial instrument that shows nothing spatial asks the reader to take its word for
everything.

So this renders the surfaces the test actually ran on — not a prettier basemap, the
literal analysis grid at its literal resolution, including one draw from the null
beside the observation it is being compared to. If the two look alike, the reader can
see for themselves why the number came back near 1.

No dependencies, no network, no build step: rasters are encoded as inline PNG data
URIs with a small writer at the bottom of this file, and everything else is inline SVG
and CSS. The output is one file that can be emailed, and it will still render in ten
years.
"""

from __future__ import annotations

import base64
import html
import json
import struct
import zlib

from .analysis import Prepared, TestResult
from .grid import convex_hull

# Ramp stops, light to dark. Each layer keeps its own hue everywhere it appears so the
# observation and its null draw are directly comparable by eye.
RAMPS = {
    "a": ((222, 235, 247), (66, 133, 200), (12, 44, 84)),
    "b": ((253, 232, 214), (222, 118, 51), (94, 38, 12)),
    "confound": ((228, 240, 231), (86, 156, 104), (22, 61, 34)),
}

# Inside the observation window, zero intensity: a hatch-free flat grey that reads as
# neither data nor void.
EMPTY_CELL = (198, 198, 202, 255)

# Mid grey for the window outline — legible against both the pale raster and the dark
# panel behind it, which `currentColor` is not.
OUTLINE = "#6b6863"

VERDICT_TONE = {
    "co-located": ("finding", "#b45309"),
    "segregated": ("finding", "#7c3aed"),
    "no association": ("null", "#0f766e"),
}


# ------------------------------------------------------------------ rasters --


def _ramp(stops, t: float) -> tuple[int, int, int]:
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    lo, mid, hi = stops
    if t < 0.5:
        u, c0, c1 = t * 2.0, lo, mid
    else:
        u, c0, c1 = (t - 0.5) * 2.0, mid, hi
    return tuple(int(round(c0[i] + (c1[i] - c0[i]) * u)) for i in range(3))


def _scale_max(values: list[float], window: list[bool]) -> float:
    """Cap the colour scale at the 99th percentile of occupied cells.

    One extreme cell would otherwise flatten every other cell to the palest tint and
    the map would show a single dot on an empty continent, which is a rendering
    artifact rather than a property of the data.
    """
    occupied = sorted(v for v, inside in zip(values, window) if inside and v > 0.0)
    if not occupied:
        return 1.0
    return occupied[min(len(occupied) - 1, int(len(occupied) * 0.99))] or 1.0


def raster_png(values: list[float], prep: Prepared, ramp: str) -> str:
    """One analysis surface as a base64 PNG data URI, one pixel per grid cell.

    Rendered at grid resolution and upscaled by the browser with nearest-neighbour, so
    the cell size the analysis actually used stays visible instead of being smoothed
    into a plausible-looking continuous field.
    """
    grid, window = prep.grid, prep.window
    stops = RAMPS[ramp]
    top = _scale_max(values, window)

    # Three states, three appearances. "Outside the study area", "inside it but no
    # observation reaches here", and "inside it with a little intensity" are different
    # claims, and an earlier version rendered the first two identically — which made
    # the window look concave when it is a convex hull, and quietly turned rendered
    # absence back into missing data.
    rows = []
    for iy in range(grid.ny - 1, -1, -1):  # PNG rows run north to south
        row = bytearray()
        base = iy * grid.nx
        for ix in range(grid.nx):
            i = base + ix
            if not window[i]:
                row += b"\x00\x00\x00\x00"  # not analysed, not drawn
            elif values[i] <= 0.0:
                row += bytes(EMPTY_CELL)  # analysed, nothing here
            else:
                t = values[i] / top if top > 0 else 0.0
                r, g, b = _ramp(stops, t ** 0.6)  # gamma lifts the low end into view
                row += bytes((r, g, b, 255))
        rows.append(bytes(row))

    return "data:image/png;base64," + base64.b64encode(_png(grid.nx, grid.ny, rows)).decode()


def _window_rings(prep: Prepared) -> list[list[tuple[float, float]]]:
    """The window outline in projected metres — the declared boundary when there is
    one, the inferred hull otherwise. Drawing the hull over a declared boundary would
    show the reader a window the analysis did not use."""
    if prep.boundary_rings:
        return prep.boundary_rings
    hull = convex_hull([p for layer in prep.projected for p in layer])
    return [hull] if len(hull) >= 3 else []


def _outline(prep: Prepared) -> str:
    grid = prep.grid
    declared = bool(prep.boundary_rings)
    dash = "" if declared else ' stroke-dasharray="2 1.6"'
    parts = []
    for ring in _window_rings(prep):
        pts = " ".join(
            f"{(x - grid.x_min) / grid.cell_m:.2f},"
            f"{grid.ny - (y - grid.y_min) / grid.cell_m:.2f}"
            for x, y in ring
        )
        parts.append(
            f'<polygon points="{pts}" fill="none" stroke="{OUTLINE}" '
            f'stroke-opacity="{0.9 if declared else 0.8}" stroke-width="0.7"{dash}/>'
        )
    return "".join(parts)


def map_panel(title: str, subtitle: str, values: list[float], prep: Prepared,
              ramp: str) -> str:
    grid = prep.grid
    href = raster_png(values, prep, ramp)
    outline = _outline(prep)
    return f"""
<figure class="map">
  <svg viewBox="0 0 {grid.nx} {grid.ny}" role="img" aria-label="{html.escape(title)}">
    <image href="{href}" x="0" y="0" width="{grid.nx}" height="{grid.ny}"/>
    {outline}
  </svg>
  <figcaption><strong>{html.escape(title)}</strong><span>{html.escape(subtitle)}</span></figcaption>
</figure>"""


# --------------------------------------------------------------------- plot --


def null_chart(result: TestResult) -> str:
    """The null distribution with the observed value marked, as inline SVG.

    Drawn in multiples of the null mean rather than in raw co-location units, so the
    axis is the same quantity as the headline effect ratio. A reader should not have to
    convert between two scales to check that the picture agrees with the number.
    """
    scale = result.null_mean or 1.0
    values = [v / scale for v in result.null_values]
    if not values:
        return ""
    observed = result.observed / scale
    lo, hi = min(min(values), observed), max(max(values), observed)
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.06, hi + span * 0.06
    span = hi - lo

    n_bins = 48
    counts = [0] * n_bins
    for v in values:
        counts[min(n_bins - 1, max(0, int((v - lo) / span * n_bins)))] += 1
    peak = max(counts) or 1

    w, h = 720.0, 190.0
    left, right, bottom = 8.0, 8.0, 34.0
    plot_w = w - left - right
    plot_h = h - bottom - 12.0

    def px(value: float) -> float:
        return left + (value - lo) / span * plot_w

    bars = []
    bw = plot_w / n_bins
    for i, c in enumerate(counts):
        if not c:
            continue
        bh = c / peak * plot_h
        bars.append(
            f'<rect x="{left + i * bw:.2f}" y="{12.0 + plot_h - bh:.2f}" '
            f'width="{bw - 0.6:.2f}" height="{bh:.2f}" class="bar"/>'
        )

    band = (
        f'<rect x="{px(result.null_lo / scale):.2f}" y="12" '
        f'width="{max(0.0, px(result.null_hi / scale) - px(result.null_lo / scale)):.2f}" '
        f'height="{plot_h:.2f}" class="band"/>'
    )
    obs_x = px(observed)
    marker = (
        f'<line x1="{obs_x:.2f}" y1="6" x2="{obs_x:.2f}" y2="{12.0 + plot_h:.2f}" '
        f'class="obs"/>'
        f'<circle cx="{obs_x:.2f}" cy="6" r="4" class="obs-dot"/>'
    )
    anchor = "start" if obs_x < left + plot_w * 0.5 else "end"
    dx = 8 if anchor == "start" else -8
    labels = (
        f'<text x="{obs_x + dx:.2f}" y="{12.0 + plot_h + 22:.2f}" text-anchor="{anchor}" '
        f'class="lbl obs-lbl">observed {observed:.2f}×</text>'
        f'<text x="{px(1.0):.2f}" y="{12.0 + plot_h + 22:.2f}" '
        f'text-anchor="middle" class="lbl">1.00× — the middle of chance</text>'
    )
    return (
        f'<svg class="chart" viewBox="0 0 {w:.0f} {h:.0f}" role="img" '
        f'aria-label="null distribution">{band}{"".join(bars)}{marker}{labels}</svg>'
    )


# --------------------------------------------------------------------- html --


def _rows(pairs) -> str:
    return "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{v}</td></tr>" for k, v in pairs
    )


def _sensitivity_table(runs: list[dict], key: str) -> str:
    """One sweep. The column that is being varied comes first, the one being held
    fixed comes second, so a reader can confirm at a glance that the sweep isolates
    what it claims to."""
    varying, holding = ("cell size", "bandwidth") if key == "cell" else ("bandwidth", "cell size")
    head = (
        f"<tr><th>{varying}</th><th>{holding} (fixed)</th><th>effect</th>"
        f"<th>p</th><th>reads as</th></tr>"
    )
    body = []
    for r in runs:
        cell = f"{r['grid']['cell_km']:g} km"
        band = f"{r['bandwidth_km']:.0f} km"
        first, second = (cell, band) if key == "cell" else (band, cell)
        body.append(
            f"<tr><td>{first}</td><td class=\"muted\">{second}</td>"
            f"<td class=\"num\">{r['effect_ratio']:.3f}×</td>"
            f"<td class=\"num\">{r['p_value']:.4f}</td>"
            f"<td>{html.escape(r['verdict'])}</td></tr>"
        )
    return f"<table class=\"grid-table\">{head}{''.join(body)}</table>"


def render(result: TestResult, prep: Prepared, bundle: dict) -> str:
    """The whole report as one HTML string."""
    tone_class, tone_colour = VERDICT_TONE.get(result.verdict, ("null", "#0f766e"))
    headline = {
        "co-located": "Association survives the declared confounds",
        "segregated": "The layers avoid each other, beyond the confounds",
        "no association": "No association beyond what the confounds predict",
    }[result.verdict]

    confounds = result.strata.get("confounds") or []
    basis = ", ".join(confounds) if confounds else "NOTHING — uniform null"

    maps = [
        map_panel(result.layer_a, f"{prep.n_a} observations, kernel intensity",
                  prep.intensity_a, prep, "a"),
        map_panel(result.layer_b, f"{prep.n_b} observations, kernel intensity",
                  prep.intensity_b, prep, "b"),
        map_panel(f"{result.layer_a} under the null",
                  "one draw from the conditional null", prep.surrogate_surface(seed=1),
                  prep, "a"),
    ]
    for layer in prep.confounds:
        maps.append(map_panel(
            f"confound: {layer.name}", "held fixed by the null",
            prep.confound_intensity[layer.name], prep, "confound",
        ))

    warnings = "".join(
        f'<li>{html.escape(w)}</li>' for w in result.warnings
    )
    warning_block = (
        f'<section class="warn"><h2>Warnings</h2><ul>{warnings}</ul></section>'
        if warnings else ""
    )

    provenance = "".join(
        "<tr>"
        f"<td>{html.escape(p['name'])}</td>"
        f"<td>{html.escape(p['tier'])} — {html.escape(p['tier_meaning'])}</td>"
        f"<td class=\"num\">{p['n_points']}</td>"
        f"<td class=\"num\">{p['dropped_rows']}</td>"
        f"<td>{html.escape(str(p.get('custodian') or '—'))}</td>"
        f"<td class=\"path\">{html.escape(str(p.get('source_path') or '—'))}</td>"
        "</tr>"
        for p in bundle["inputs"]
    )

    sens = bundle.get("sensitivity")
    sens_block = ""
    if sens:
        sens_block = f"""
<section>
  <h2>Sensitivity</h2>
  <div class="two">
    <div>
      <h3>Grid resolution</h3>
      <p class="note">Bandwidth is held fixed in kilometres across this sweep, so it
      isolates the raster and nothing else. A conclusion that moves here is a
      resolution artifact and should be discarded.</p>
      {_sensitivity_table(sens['cell_size'], 'cell')}
    </div>
    <div>
      <h3>Bandwidth</h3>
      <p class="note">The bandwidth <em>is</em> the spatial scale of the question. A
      conclusion that moves here is usually real information about the scale at which
      the layers are coupled — report the scale with the number.</p>
      {_sensitivity_table(sens['bandwidth'], 'bandwidth')}
    </div>
  </div>
</section>"""

    directions = result.to_dict()["null"]["directions"]
    direction_rows = "".join(
        f"<tr><td>{html.escape(d['resampled_layer'])} resampled</td>"
        f"<td class=\"num\">{d['effect_ratio']:.3f}×</td>"
        f"<td class=\"num\">{d['p_value']:.4f}</td></tr>"
        for d in directions
    )
    direction_note = (
        "Both directions are run because resampling A against a fixed B and resampling "
        "B against a fixed A are different tests. The conservative one is what the "
        "headline reports."
        if len(directions) > 1 else
        "Only one direction was run (--one-way). Resampling A against a fixed B and "
        "resampling B against a fixed A are different tests, so this result depends on "
        "which layer was given first."
    )

    win = result.window
    outline_note = (
        "solid, because it was declared" if win.get("declared")
        else "dashed, because it was inferred from a convex hull"
    )
    if win.get("declared"):
        window_row = f"declared: {html.escape(str(win.get('source')))}"
        window_note = (
            "The observation window was declared rather than inferred, so the "
            f"noise floor is {result.noise_floor * 100:.0f}% — the residual left by the "
            "analysis geometry itself, without the convex-hull over-coverage the "
            "inferred window carries."
        )
    else:
        window_row = "inferred: convex hull of the data"
        window_note = (
            "The observation window is inferred from a convex hull, which over-covers "
            f"concave study regions — that is where the {result.noise_floor * 100:.0f}% "
            "noise floor comes from. Supplying --boundary lowers it."
        )

    params = bundle["parameters"]
    spec = _rows([
        ("Confounds held fixed", html.escape(basis)),
        ("Observation window", window_row),
        ("Noise floor", f"{result.noise_floor * 100:.0f}% minimum reportable effect"),
        ("Strata", f"{result.strata['n_strata']} "
                   f"({result.strata['bins_per_confound']} bins per confound)"),
        ("Window", f"{result.strata['window_cells']} cells of "
                   f"{result.grid['n_cells']} in the grid"),
        ("Grid", f"{result.grid['cell_km']:g} km cells, "
                 f"{result.grid['nx']}×{result.grid['ny']}"),
        ("Bandwidth", f"{result.bandwidth_km:.0f} km "
                      f"({result.sigma_cells:.2f} cells)"),
        ("Simulations", f"{result.n_sim} per direction"),
        ("Seed", params["seed"]),
        ("Evidence tier", f"{result.tier}"
                          f"{' — descriptive only' if result.descriptive_only else ''}"),
    ])

    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(result.layer_a)} × {html.escape(result.layer_b)} — coincidence</title>
<style>{_CSS}</style>
<main style="--tone: {tone_colour}">
  <header>
    <p class="kicker">coincidence · spatial co-location test</p>
    <h1>{html.escape(result.layer_a)} <span>×</span> {html.escape(result.layer_b)}</h1>
    <p class="verdict {tone_class}">{html.escape(headline)}</p>
    <div class="numbers">
      <div><span class="big">{result.effect_ratio:.2f}×</span><span
        class="cap">effect ratio</span><span class="sub">1.00× = exactly what the
        confounds predict</span></div>
      <div><span class="big">{result.p_value:.4f}</span><span class="cap">p-value</span>
        <span class="sub">not the answer on its own</span></div>
      <div><span class="big">{result.bandwidth_km:.0f} km</span><span
        class="cap">scale</span><span class="sub">the question this answers</span></div>
    </div>
  </header>

  <section>
    <p class="statement">{html.escape(result.statement())}</p>
  </section>

  <section>
    <h2>What chance looks like</h2>
    <p class="note">The bars are {result.n_sim} co-location values produced by
    resampling {html.escape(directions[0]['resampled_layer'])} within the confound
    strata. The shaded band holds 95% of them. The line is what was actually observed.
    A result matters when the line sits clear of the bars — and the effect has to clear
    {result.noise_floor * 100:.0f}% as well, because a Monte Carlo p-value shrinks with the
    simulation count whether or not anything is there.</p>
    {null_chart(result)}
    <table class="grid-table narrow">
      <tr><th>direction of the null</th><th>effect</th><th>p</th></tr>
      {direction_rows}
    </table>
    <p class="note">{html.escape(direction_note)}</p>
  </section>

  <section>
    <h2>The surfaces the test ran on</h2>
    <p class="note">One pixel per analysis cell, at the resolution the statistic used.
    The outline is the observation window — {outline_note} — and nothing outside it is
    analysed or drawn. Colour is scaled to the 99th percentile of occupied cells in each
    panel, so panels show shape rather than comparable absolute magnitudes.</p>
    <div class="maps">{''.join(maps)}</div>
  </section>

  {sens_block}
  {warning_block}

  <section>
    <h2>Null specification</h2>
    <table class="spec">{spec}</table>
  </section>

  <section>
    <h2>Inputs</h2>
    <table class="grid-table">
      <tr><th>layer</th><th>evidence tier</th><th>located</th><th>dropped</th>
        <th>custodian</th><th>source</th></tr>
      {provenance}
    </table>
    <p class="note">Dropped rows had no usable coordinates. They were counted, not
    imputed.</p>
  </section>

  <footer>
    <p><strong>What this does not license.</strong> This is spatial association, not
    mechanism. It cannot distinguish cause, direction, or the individuals involved, and
    an unmeasured confound remains the most common explanation for any residual.
    {html.escape(window_note)}</p>
    <p class="repro">Generated by coincidence {html.escape(bundle['version'])}. Seed
    {params['seed']}. Re-run it, change the confound set, and disagree precisely.</p>
  </footer>
</main>
<script type="application/json" id="bundle">{
    html.escape(json.dumps(bundle), quote=False)
}</script>
"""


_CSS = """
:root {
  --bg: #fbfaf8; --panel: #ffffff; --ink: #1c1b19; --muted: #6b6863;
  --line: #e5e1da; --tone: #0f766e;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #16151a; --panel: #1e1d24; --ink: #eceaf0; --muted: #9d99a6;
          --line: #33313c; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1000px; margin: 0 auto; padding: 40px 24px 72px; }
header { border-bottom: 3px solid var(--tone); padding-bottom: 24px; margin-bottom: 8px; }
.kicker { text-transform: uppercase; letter-spacing: .14em; font-size: 11px;
  color: var(--muted); margin: 0 0 12px; }
h1 { font-size: clamp(26px, 4.5vw, 40px); margin: 0 0 16px; line-height: 1.15;
  font-weight: 650; }
h1 span { color: var(--muted); font-weight: 400; }
h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .1em;
  color: var(--muted); margin: 40px 0 12px; font-weight: 600; }
h3 { font-size: 14px; margin: 0 0 6px; }
.verdict { font-size: clamp(17px, 2.4vw, 21px); font-weight: 600; color: var(--tone);
  margin: 0 0 24px; }
.numbers { display: flex; flex-wrap: wrap; gap: 32px; }
.numbers div { display: flex; flex-direction: column; }
.big { font-size: 32px; font-weight: 660; font-variant-numeric: tabular-nums;
  line-height: 1.1; }
.cap { font-size: 11px; text-transform: uppercase; letter-spacing: .1em;
  color: var(--muted); margin-top: 4px; }
.sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
.statement { font-size: 17px; background: var(--panel); border: 1px solid var(--line);
  border-left: 3px solid var(--tone); border-radius: 4px; padding: 18px 20px; margin: 24px 0 0; }
.note { color: var(--muted); font-size: 14px; max-width: 76ch; }
.chart { width: 100%; height: auto; background: var(--panel);
  border: 1px solid var(--line); border-radius: 4px; padding: 8px; }
.chart .bar { fill: var(--muted); fill-opacity: .55; }
.chart .band { fill: var(--muted); fill-opacity: .12; }
.chart .obs { stroke: var(--tone); stroke-width: 2; }
.chart .obs-dot { fill: var(--tone); }
.chart .lbl { font: 12px ui-sans-serif, system-ui, sans-serif; fill: var(--muted); }
.chart .obs-lbl { fill: var(--tone); font-weight: 600; }
.maps { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.map { margin: 0; background: var(--panel); border: 1px solid var(--line);
  border-radius: 4px; padding: 10px; color: var(--ink); }
.map svg { width: 100%; height: auto; display: block; }
.map image { image-rendering: pixelated; }
figcaption { display: flex; flex-direction: column; gap: 2px; margin-top: 8px;
  font-size: 13px; }
figcaption span { color: var(--muted); font-size: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin: 12px 0; }
.grid-table th { text-align: left; font-weight: 600; font-size: 11px;
  text-transform: uppercase; letter-spacing: .08em; color: var(--muted);
  border-bottom: 1px solid var(--line); padding: 6px 10px 6px 0; }
.grid-table td { padding: 7px 10px 7px 0; border-bottom: 1px solid var(--line); }
.grid-table.narrow { max-width: 460px; }
.num { font-variant-numeric: tabular-nums; }
.path { color: var(--muted); font-size: 12px; word-break: break-all; }
.muted { color: var(--muted); }
.spec th { text-align: left; font-weight: 500; color: var(--muted); width: 40%;
  padding: 7px 12px 7px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
.spec td { padding: 7px 0; border-bottom: 1px solid var(--line);
  font-variant-numeric: tabular-nums; }
.two { display: grid; gap: 28px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
.warn ul { padding-left: 20px; }
.warn li { margin-bottom: 10px; color: var(--ink); font-size: 14px; max-width: 80ch; }
footer { margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 13px; }
.repro { font-size: 12px; }
"""


# ---------------------------------------------------------------- png writer --


def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    """Minimal RGBA PNG encoder.

    Thirty lines of stdlib beats a dependency for a tool that promises to run anywhere
    with nothing installed.
    """
    raw = b"".join(b"\x00" + row for row in rows)  # filter type 0 per scanline

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
