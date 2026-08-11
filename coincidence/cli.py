"""Command line interface.

    python -m coincidence describe data.csv
    python -m coincidence test a.csv b.csv --confound population.csv
    python -m coincidence test a.csv b.csv --confound pop.csv --export bundle.json
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .analysis import sensitivity, test_pair
from .loading import LoadError, load_layer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coincidence",
        description="Test whether apparent spatial coincidence survives base rates.",
    )
    parser.add_argument("--version", action="version", version=f"coincidence {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("describe", help="inspect a file: columns, detected coordinates, extent")
    d.add_argument("path")
    _coord_args(d)

    t = sub.add_parser("test", help="test co-location of two layers against a conditional null")
    t.add_argument("a")
    t.add_argument("b")
    t.add_argument("--confound", action="append", default=[], metavar="PATH",
                   help="a layer explaining where observations can occur. Repeatable. "
                        "Omitting this gives a uniform null, which is uninformative.")
    _coord_args(t)
    t.add_argument("--tier-a", default="D", choices=list("ABCD"))
    t.add_argument("--tier-b", default="D", choices=list("ABCD"))
    t.add_argument("--cell-km", type=float, default=50.0)
    t.add_argument("--sim", type=int, default=999, help="Monte Carlo simulations")
    t.add_argument("--bins", type=int, default=5, help="quantile bins per confound")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--sensitivity", action="store_true",
                   help="also run at 25/50/100 km to expose resolution artifacts")
    t.add_argument("--export", metavar="PATH", help="write a shareable result bundle")
    t.add_argument("--json", action="store_true", help="machine-readable output on stdout")

    args = parser.parse_args(argv)
    try:
        if args.command == "describe":
            return _describe(args)
        return _test(args)
    except LoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _coord_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--lat", dest="lat_field", help="latitude column (auto-detected if omitted)")
    p.add_argument("--lon", dest="lon_field", help="longitude column (auto-detected if omitted)")
    p.add_argument("--weight", dest="weight_field", help="per-row weight column")


def _describe(args) -> int:
    layer = load_layer(args.path, lat_field=args.lat_field, lon_field=args.lon_field,
                       weight_field=args.weight_field)
    lons, lats = layer.lons, layer.lats
    print(f"{layer.name}: {len(layer)} located rows, {layer.dropped_rows} dropped")
    print(f"  extent: lon {min(lons):.3f} .. {max(lons):.3f}   "
          f"lat {min(lats):.3f} .. {max(lats):.3f}")
    print(f"  total weight: {layer.total_weight:g}")
    print(f"  tier: {layer.tier} (declare a real one with --tier-a/--tier-b when testing)")
    if layer.dropped_rows:
        print(f"  note: {layer.dropped_rows} rows had no usable coordinates and were "
              f"dropped, not guessed at.")
    return 0


def _test(args) -> int:
    a = load_layer(args.a, lat_field=args.lat_field, lon_field=args.lon_field,
                   weight_field=args.weight_field, tier=args.tier_a)
    b = load_layer(args.b, lat_field=args.lat_field, lon_field=args.lon_field,
                   weight_field=args.weight_field, tier=args.tier_b)
    confounds = [
        load_layer(p, lat_field=args.lat_field, lon_field=args.lon_field, tier="A")
        for p in args.confound
    ]
    a.confounds = [c.name for c in confounds]
    b.confounds = [c.name for c in confounds]

    kwargs = dict(confounds=confounds, n_sim=args.sim, n_bins=args.bins, seed=args.seed)
    result = test_pair(a, b, cell_km=args.cell_km, **kwargs)

    bundle = {
        "tool": "coincidence", "version": __version__,
        "inputs": [a.provenance(), b.provenance()] + [c.provenance() for c in confounds],
        "parameters": {
            "cell_km": args.cell_km, "n_simulations": args.sim,
            "bins_per_confound": args.bins, "seed": args.seed,
        },
        "result": result.to_dict(),
    }

    if args.sensitivity:
        sweeps = sensitivity(a, b, cell_km=args.cell_km, **kwargs)
        bundle["sensitivity"] = {
            name: [r.to_dict() for r in runs] for name, runs in sweeps.items()
        }

    if args.json:
        print(json.dumps(bundle, indent=2))
    else:
        _print_human(result, bundle.get("sensitivity"))

    if args.export:
        with open(args.export, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, indent=2)
        print(f"\nBundle written to {args.export}. It carries the inputs, the parameters, "
              f"the null specification and the seed, so anyone can re-run this and "
              f"disagree precisely.")
    return 0


def _print_human(result, sens) -> None:
    r = result
    print()
    print(f"  {r.layer_a}  x  {r.layer_b}")
    print(f"  {'-' * 60}")
    print(f"  observed co-location : {r.observed:.4f}")
    print(f"  expected under null  : {r.null_mean:.4f}  "
          f"(95% of nulls fall in {r.null_lo:.4f} .. {r.null_hi:.4f})")
    print(f"  effect ratio         : {r.effect_ratio:.3f}x")
    print(f"  p-value              : {r.p_value:.4f}   ({r.n_sim} simulations)")
    print(f"  grid                 : {r.grid['cell_km']:g} km cells, "
          f"{r.grid['nx']}x{r.grid['ny']}")
    print(f"  null holds fixed     : "
          f"{', '.join(r.strata['confounds']) if r.strata['confounds'] else 'NOTHING (uniform)'}")
    print(f"  evidence tier        : {r.tier}"
          f"{'  [descriptive only]' if r.descriptive_only else ''}")
    print()
    print("  " + _wrap(r.statement(), 76))
    if sens:
        print()
        print("  Sensitivity to grid resolution:")
        for run in sens["cell_size"]:
            print(f"    {run['grid']['cell_km']:>6g} km cells : ratio "
                  f"{run['effect_ratio']:.3f}x, p = {run['p_value']:.4f}")
        if len({run["beats_null"] for run in sens["cell_size"]}) > 1:
            print("    -> The conclusion CHANGES with cell size. That is a resolution "
                  "artifact (MAUP), not a finding.")

        print()
        print("  Sensitivity to bandwidth (the spatial scale of the question):")
        for run in sens["bandwidth"]:
            km = run["bandwidth_km"]
            print(f"    {km:>6.0f} km kernel: ratio {run['effect_ratio']:.3f}x, "
                  f"p = {run['p_value']:.4f}")
        ratios = [run["effect_ratio"] for run in sens["bandwidth"]]
        if ratios and max(ratios) / max(1e-9, min(ratios)) > 2.0:
            print("    -> Association is strongly scale-dependent. This is usually real "
                  "rather than artifactual: it means the layers are coupled at the "
                  "finer scale and not the coarser one. Report the scale with the "
                  "number, because the number alone is not interpretable.")
    for w in r.warnings:
        print(f"\n  [!] {_wrap(w, 74)}")
    print()


def _wrap(text: str, width: int) -> str:
    import textwrap
    return "\n  ".join(textwrap.wrap(text, width))


if __name__ == "__main__":
    raise SystemExit(main())
