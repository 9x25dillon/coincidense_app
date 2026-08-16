"""Command line interface.

    python3 -m coincidence demo
    python3 -m coincidence describe data.csv
    python3 -m coincidence test a.csv b.csv --confound population.csv
    python3 -m coincidence test a.csv b.csv --confound pop.csv --report finding.html

The presentation here has one job beyond legibility: it must not let the shape of the
output do any arguing the numbers have not earned. A negative result gets the same
banner as a positive one, the effect size is printed larger than the p-value, and the
null is drawn rather than described.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .analysis import prepare, sensitivity, test_pair
from .console import Progress, Style, null_plot, rule, width, wrap
from .layers import TIERS
from .loading import LoadError, load_layer

EPILOG = """\
examples:
  coincidence demo                            the worked example, start to finish
  coincidence describe sightings.csv          what columns did it find?
  coincidence test a.csv b.csv --confound population.csv
  coincidence test a.csv b.csv --confound pop.csv --sensitivity --report out.html

the one thing you have to supply is --confound: what else explains where your
observations are? without it the tool runs a uniform null and will tell you, loudly,
that the answer means very little.
"""

VERDICT_LABEL = {
    "co-located": ("CO-LOCATED BEYOND THE CONFOUNDS", "yellow"),
    "segregated": ("SEGREGATED BEYOND THE CONFOUNDS", "magenta"),
    "no association": ("NO ASSOCIATION BEYOND CHANCE", "cyan"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coincidence",
        description="Test whether apparent spatial coincidence survives base rates.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"coincidence {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("demo", help="run the worked example and explain what it shows")

    d = sub.add_parser("describe", help="inspect a file: columns, detected coordinates, extent")
    d.add_argument("path")
    _coord_args(d)
    d.add_argument("--no-color", action="store_true", help="disable ANSI colour")

    t = sub.add_parser(
        "test", help="test co-location of two layers against a conditional null",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    t.add_argument("a", metavar="LAYER_A")
    t.add_argument("b", metavar="LAYER_B")
    t.add_argument("--confound", action="append", default=[], metavar="PATH",
                   help="a layer explaining where observations can occur. Repeatable. "
                        "Omitting this gives a uniform null, which is uninformative.")
    _coord_args(t)
    for suffix, who in (("a", "layer A"), ("b", "layer B"), ("c", "every confound")):
        g = t.add_argument_group(f"column names for {who}")
        g.add_argument(f"--lat-{suffix}", dest=f"lat_{suffix}", metavar="COL",
                       help=f"latitude column for {who} (overrides --lat)")
        g.add_argument(f"--lon-{suffix}", dest=f"lon_{suffix}", metavar="COL",
                       help=f"longitude column for {who} (overrides --lon)")
        g.add_argument(f"--weight-{suffix}", dest=f"weight_{suffix}", metavar="COL",
                       help=f"per-row weight column for {who}")
    t.add_argument("--tier-a", default="D", choices=list("ABCD"),
                   help="evidence tier of layer A (default D, uncertain)")
    t.add_argument("--tier-b", default="D", choices=list("ABCD"),
                   help="evidence tier of layer B (default D, uncertain)")
    t.add_argument("--cell-km", type=float, default=50.0, help="analysis cell size")
    t.add_argument("--bandwidth-km", type=float, default=None,
                   help="kernel bandwidth in km (default: a stated rule from sample size)")
    t.add_argument("--sim", type=int, default=999, help="Monte Carlo simulations")
    t.add_argument("--bins", type=int, default=5, help="quantile bins per confound")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--sensitivity", action="store_true",
                   help="sweep cell size and bandwidth to expose parameter artifacts")
    t.add_argument("--one-way", action="store_true",
                   help="skip the reverse-direction null; faster, but the answer then "
                        "depends on which layer you typed first")
    t.add_argument("--export", metavar="PATH", help="write a shareable JSON bundle")
    t.add_argument("--report", metavar="PATH", help="write a self-contained HTML report")
    t.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    t.add_argument("--no-color", action="store_true", help="disable ANSI colour")

    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return _demo()
        if args.command == "describe":
            return _describe(args)
        return _test(args)
    except LoadError as exc:
        style = Style(False if getattr(args, "no_color", False) else None, sys.stderr)
        print(style("\n  Could not load that file.", "bold", "red"), file=sys.stderr)
        message = str(exc)
        # Column listings are pre-formatted; only prose gets re-wrapped.
        print("\n".join(
            wrap(line, indent="  ") if not line.startswith("  ") else line
            for line in message.splitlines()
        ), file=sys.stderr)
        if args.command != "describe":
            print(style("\n  `coincidence describe <file>` shows what a file contains "
                        "before you test it.", "grey"), file=sys.stderr)
        print(file=sys.stderr)
        return 2


def _coord_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--lat", dest="lat_field", metavar="COL",
                   help="latitude column (auto-detected if omitted)")
    p.add_argument("--lon", dest="lon_field", metavar="COL",
                   help="longitude column (auto-detected if omitted)")
    p.add_argument("--weight", dest="weight_field", metavar="COL",
                   help="per-row weight column")


# ---------------------------------------------------------------- describe --


def _describe(args) -> int:
    style = Style(False if args.no_color else None)
    layer = load_layer(args.path, lat_field=args.lat_field, lon_field=args.lon_field,
                       weight_field=args.weight_field)
    lons, lats = layer.lons, layer.lats
    cols = width()

    print()
    print(f"  {style(layer.name, 'bold')}   {style(args.path, 'grey')}")
    print(rule(cols))
    print(f"  located rows   {len(layer)}")
    if layer.dropped_rows:
        print(f"  dropped        {style(str(layer.dropped_rows), 'yellow')}"
              f"   {style('no usable coordinates — counted, never guessed at', 'grey')}")
    print(f"  extent         lon {min(lons):.3f} .. {max(lons):.3f}   "
          f"lat {min(lats):.3f} .. {max(lats):.3f}")
    print(f"  total weight   {layer.total_weight:g}")
    print(f"  evidence tier  {layer.tier} — {TIERS[layer.tier]}")
    print()
    print(wrap(style("Tier D is what every file loads as. Claiming anything better is "
                     "your assertion to make, with --tier-a / --tier-b.", "grey")))
    print()
    print(f"  {style('Next:', 'bold')} test it against another layer, and say what "
          f"already explains both.")
    print(style(f"    coincidence test {args.path} OTHER.csv --confound WHAT_DRIVES_BOTH.csv",
                "grey"))
    print()
    return 0


# -------------------------------------------------------------------- test --


def _pick(specific, general):
    return specific if specific is not None else general


def _test(args) -> int:
    style = Style(False if args.no_color else None)

    a = load_layer(args.a, tier=args.tier_a,
                   lat_field=_pick(args.lat_a, args.lat_field),
                   lon_field=_pick(args.lon_a, args.lon_field),
                   weight_field=_pick(args.weight_a, args.weight_field))
    b = load_layer(args.b, tier=args.tier_b,
                   lat_field=_pick(args.lat_b, args.lat_field),
                   lon_field=_pick(args.lon_b, args.lon_field),
                   weight_field=_pick(args.weight_b, args.weight_field))
    confounds = [
        load_layer(p, tier="A",
                   lat_field=_pick(args.lat_c, args.lat_field),
                   lon_field=_pick(args.lon_c, args.lon_field),
                   weight_field=args.weight_c)
        for p in args.confound
    ]
    a.confounds = [c.name for c in confounds]
    b.confounds = [c.name for c in confounds]

    sigma_cells = (args.bandwidth_km / args.cell_km) if args.bandwidth_km else None
    prep = prepare(a, b, confounds=confounds, cell_km=args.cell_km, n_bins=args.bins,
                   sigma_cells=sigma_cells)

    shared = dict(confounds=confounds, n_sim=args.sim, n_bins=args.bins, seed=args.seed,
                  both_directions=not args.one_way)

    quiet = args.json
    bar = Progress("simulating", enabled=False if quiet else None)
    result = test_pair(a, b, cell_km=args.cell_km, sigma_cells=sigma_cells, prep=prep,
                       progress=bar, **shared)
    bar.done()

    bundle = {
        "tool": "coincidence", "version": __version__,
        "inputs": [a.provenance(), b.provenance()] + [c.provenance() for c in confounds],
        "parameters": {
            "cell_km": args.cell_km, "n_simulations": args.sim,
            "bins_per_confound": args.bins, "seed": args.seed,
            "bandwidth_km": result.bandwidth_km,
            "both_directions": not args.one_way,
        },
        "result": result.to_dict(),
    }

    if args.sensitivity:
        bar = Progress("sweeping  ", enabled=False if quiet else None)
        sweeps = sensitivity(a, b, cell_km=args.cell_km, sigma_cells=sigma_cells,
                             progress=bar, **shared)
        bar.done()
        bundle["sensitivity"] = {
            name: [r.to_dict() for r in runs] for name, runs in sweeps.items()
        }

    if args.json:
        print(json.dumps(bundle, indent=2))
    else:
        _print_human(result, bundle.get("sensitivity"), style)

    written = []
    if args.export:
        with open(args.export, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, indent=2)
        written.append(("bundle", args.export,
                        "inputs, parameters, null specification and seed — "
                        "someone else can re-run this and disagree precisely"))
    if args.report:
        from .report import render
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(render(result, prep, bundle))
        written.append(("report", args.report,
                        "self-contained HTML: the maps, the null, the sensitivity "
                        "sweeps and the provenance"))

    if written and not args.json:
        print()
        for kind, path, why in written:
            print(f"  {style('✓', 'green')} {kind} → {style(path, 'bold')}")
            print(wrap(style(why, "grey"), indent="    "))
        print()
    return 0


def _print_human(result, sens, style: Style) -> None:
    r = result
    cols = width()
    label, colour = VERDICT_LABEL[r.verdict]
    confounds = r.strata["confounds"]

    print()
    print(f"  {style(r.layer_a, 'bold')} {style('×', 'grey')} {style(r.layer_b, 'bold')}")
    shape = (f"{r.grid['cell_km']:g} km cells · {r.bandwidth_km:.0f} km kernel · "
             f"{r.strata['window_cells']} cells in the observation window")
    print(f"  {style(shape, 'grey')}")
    print(rule(cols))
    print()
    print(f"  {style('●', colour)}  {style(label, 'bold', colour)}")
    print()
    print(f"     {style(f'{r.effect_ratio:.2f}×', 'bold')} "
          f"{style('the co-location the null predicts', 'grey')}"
          f"        p = {r.p_value:.4f}")
    if confounds:
        print(f"     {style('holding fixed:', 'grey')} {', '.join(confounds)}")
    else:
        print(f"     {style('holding fixed:', 'grey')} "
              f"{style('NOTHING — uniform null', 'yellow', 'bold')}")
    print(f"     {style('evidence tier:', 'grey')} {r.tier}"
          f"{style('  descriptive only', 'grey') if r.descriptive_only else ''}")
    print()
    print(wrap(r.statement(), indent="  ", cols=cols))
    print()
    print(f"  {style('How the observation compares with chance', 'grey')}   "
          f"{style('(1.00× = the middle of the null)', 'grey')}")
    scale = r.null_mean or 1.0
    for line in null_plot([v / scale for v in r.null_values], r.observed / scale,
                          style, cols=cols, suffix="×"):
        print(line)

    if sens:
        print()
        print(f"  {style('Sensitivity to grid resolution', 'grey')} "
              f"{style('(bandwidth held fixed — this isolates the raster)', 'grey')}")
        for run in sens["cell_size"]:
            print(f"    {run['grid']['cell_km']:>6g} km cells : "
                  f"{run['effect_ratio']:.3f}×  p = {run['p_value']:.4f}   "
                  f"{style(run['verdict'], 'grey')}")
        if len({run["beats_null"] for run in sens["cell_size"]}) > 1:
            print(wrap(style("→ The conclusion CHANGES with cell size. That is a "
                             "resolution artifact (MAUP), not a finding.", "yellow"),
                       indent="    ", cols=cols))

        print()
        print(f"  {style('Sensitivity to bandwidth', 'grey')} "
              f"{style('(the spatial scale of the question)', 'grey')}")
        for run in sens["bandwidth"]:
            print(f"    {run['bandwidth_km']:>6.0f} km kernel: "
                  f"{run['effect_ratio']:.3f}×  p = {run['p_value']:.4f}   "
                  f"{style(run['verdict'], 'grey')}")
        ratios = [run["effect_ratio"] for run in sens["bandwidth"]]
        flips = len({run["verdict"] for run in sens["bandwidth"]}) > 1
        if ratios and max(ratios) / max(1e-9, min(ratios)) > 2.0:
            print(wrap("→ Strongly scale-dependent. This is usually real rather than "
                       "artifactual: the layers are coupled at the finer scale and not "
                       "the coarser one. Report the scale with the number.",
                       indent="    ", cols=cols))
        elif flips:
            print(wrap("→ The answer depends on the scale you ask at, and no single "
                       "one of these is the right one. Quote the bandwidth with the "
                       "ratio, or the number does not mean anything.",
                       indent="    ", cols=cols))

    for w in r.warnings:
        print()
        print(f"  {style('[!]', 'yellow', 'bold')} "
              + wrap(w, indent="      ", cols=cols).lstrip())

    if not confounds:
        print()
        print(f"  {style('→ Next:', 'bold')} name what already explains where both "
              f"layers occur.")
        print(style(f"      coincidence test {r.layer_a} {r.layer_b} "
                    f"--confound WHAT_DRIVES_BOTH.csv", "grey"))
    print()


# -------------------------------------------------------------------- demo --


def _demo() -> int:
    """The thesis in one command, on data whose ground truth we know."""
    import random

    from .layers import Layer

    style = Style()
    cols = width()
    hotspots = [(-84.0, 37.2), (-92.5, 36.5), (-104.5, 43.6),
                (-105.5, 32.2), (-121.5, 44.0), (-87.5, 20.5)]

    def cluster(rng, n, spread):
        out = []
        for _ in range(n):
            lon0, lat0 = hotspots[rng.randrange(len(hotspots))]
            out.append((rng.gauss(lon0, spread), rng.gauss(lat0, spread * 0.7)))
        return out

    rng = random.Random(20260811)
    a = Layer("layer_a", cluster(rng, 220, 1.6), tier="A")
    b = Layer("layer_b", cluster(rng, 260, 1.9), tier="A")
    c = Layer("confound_c", cluster(rng, 900, 2.0), tier="A")

    print()
    print(f"  {style('The worked example', 'bold')}")
    print(rule(cols))
    print(wrap(
        "Three synthetic layers. A and B both cluster where C is, and are otherwise "
        "built independently of each other — the generator draws them from the same "
        "hotspots with separate random draws, so there is no relationship between A "
        "and B except the one C creates. We know the true answer: nothing.",
        indent="  ", cols=cols))
    print()

    print(f"  {style('1. The overlay question', 'bold')} — no confounds declared")
    print()
    bar = Progress("simulating")
    naive = test_pair(a, b, cell_km=50.0, n_sim=299, seed=7, progress=bar)
    bar.done()
    print(f"     effect {style(f'{naive.effect_ratio:.2f}×', 'bold', 'yellow')}   "
          f"p = {naive.p_value:.4f}   "
          f"{style('— a large, overwhelmingly significant association', 'grey')}")
    print()

    print(f"  {style('2. The base-rate question', 'bold')} — conditioned on C")
    print()
    bar = Progress("simulating")
    real = test_pair(a, b, confounds=[c], cell_km=50.0, n_sim=299, n_bins=10, seed=7,
                     progress=bar)
    bar.done()
    print(f"     effect {style(f'{real.effect_ratio:.2f}×', 'bold', 'cyan')}   "
          f"p = {real.p_value:.4f}   "
          f"{style('— it was the confound all along', 'grey')}")
    print()
    print(rule(cols))
    print(wrap(
        f"The overlap was real and the naive test was not wrong about it: A and B do "
        f"co-locate {naive.effect_ratio:.1f}× more than scattered points would. What "
        f"the first number cannot tell you is that every bit of it is C. That gap — "
        f"between {naive.effect_ratio:.2f}× and {real.effect_ratio:.2f}× — is the "
        f"entire reason this tool exists.",
        indent="  ", cols=cols))
    print()
    print(f"  {style('Now on your own data:', 'bold')}")
    print(style("    coincidence describe mydata.csv", "grey"))
    print(style("    coincidence test mydata.csv other.csv --confound population.csv "
                "--report out.html", "grey"))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
