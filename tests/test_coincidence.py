"""Tests. Run with:  python3 -m unittest discover -s tests -v"""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coincidence import (  # noqa: E402
    Layer, build_grid, load_layer, sensitivity, smooth, test_pair,
)
from coincidence.analysis import colocation  # noqa: E402
from coincidence.grid import Grid, project_layer  # noqa: E402
from coincidence.loading import LoadError  # noqa: E402
from coincidence.nulls import build_strata, stratum_totals, surrogate  # noqa: E402
from coincidence.projection import Albers, auto_projection  # noqa: E402

ROWS = [("a", -84.0, 37.2), ("b", -92.5, 36.5), ("c", -104.5, 43.6)]


def _tmp(name: str, text: str) -> str:
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestLoading(unittest.TestCase):
    """Any format in, the same layer out. That is the whole promise of the loader."""

    def test_csv(self):
        text = "name,longitude,latitude\n" + "\n".join(f"{n},{x},{y}" for n, x, y in ROWS)
        layer = load_layer(_tmp("a.csv", text))
        self.assertEqual(len(layer), 3)
        self.assertAlmostEqual(layer.points[0][0], -84.0)

    def test_tsv_and_semicolons(self):
        for sep, ext in ((";", "csv"), ("\t", "tsv")):
            text = sep.join(["name", "lon", "lat"]) + "\n" + "\n".join(
                sep.join([n, str(x), str(y)]) for n, x, y in ROWS
            )
            self.assertEqual(len(load_layer(_tmp(f"a.{ext}", text))), 3)

    def test_alternate_column_names(self):
        for lat_name, lon_name in (("lat", "lng"), ("Latitude", "Longitude"),
                                   ("decimalLatitude", "decimalLongitude"), ("y", "x")):
            text = f"{lon_name},{lat_name}\n-84.0,37.2\n"
            self.assertEqual(len(load_layer(_tmp("a.csv", text))), 1)

    def test_json_array(self):
        text = json.dumps([{"lon": x, "lat": y} for _, x, y in ROWS])
        self.assertEqual(len(load_layer(_tmp("a.json", text))), 3)

    def test_json_wrapped_in_object(self):
        text = json.dumps({"status": "ok", "results": [{"lon": x, "lat": y} for _, x, y in ROWS]})
        self.assertEqual(len(load_layer(_tmp("a.json", text))), 3)

    def test_jsonl(self):
        text = "\n".join(json.dumps({"lon": x, "lat": y}) for _, x, y in ROWS)
        self.assertEqual(len(load_layer(_tmp("a.jsonl", text))), 3)

    def test_geojson_points_and_polygons(self):
        fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"n": "p"},
             "geometry": {"type": "Point", "coordinates": [-84.0, 37.2]}},
            {"type": "Feature", "properties": {"n": "poly"},
             "geometry": {"type": "Polygon", "coordinates": [
                 [[-90.0, 30.0], [-88.0, 30.0], [-88.0, 32.0], [-90.0, 32.0], [-90.0, 30.0]]]}},
        ]}
        layer = load_layer(_tmp("a.geojson", json.dumps(fc)))
        self.assertEqual(len(layer), 2)
        # Polygon collapses to its exterior-ring mean — a documented simplification.
        self.assertAlmostEqual(layer.points[1][1], 31.0, places=5)

    def test_weights(self):
        text = "lon,lat,pop\n-84.0,37.2,100\n-92.5,36.5,50\n"
        layer = load_layer(_tmp("a.csv", text), weight_field="pop")
        self.assertEqual(layer.total_weight, 150.0)

    def test_bad_rows_dropped_and_counted_not_guessed(self):
        text = ("lon,lat\n-84.0,37.2\n,\nnot_a_number,37.0\n"
                "-84.0,999.0\n0,0\n-92.5,36.5\n")
        layer = load_layer(_tmp("a.csv", text))
        self.assertEqual(len(layer), 2)
        self.assertEqual(layer.dropped_rows, 4)  # blank, non-numeric, out-of-range, null island

    def test_unnamed_columns_raise_rather_than_guess(self):
        with self.assertRaises(LoadError):
            load_layer(_tmp("a.csv", "alpha,beta\n1,2\n"))

    def test_explicit_column_override(self):
        text = "alpha,beta\n-84.0,37.2\n"
        layer = load_layer(_tmp("a.csv", text), lon_field="alpha", lat_field="beta")
        self.assertEqual(layer.points, [(-84.0, 37.2)])

    def test_missing_named_column_is_an_error(self):
        with self.assertRaises(LoadError):
            load_layer(_tmp("a.csv", "lon,lat\n-84,37\n"), lat_field="nope")

    def test_tier_defaults_to_uncertain(self):
        """The loader never infers provenance. Claiming a tier is the user's act."""
        self.assertEqual(load_layer(_tmp("a.csv", "lon,lat\n-84,37\n")).tier, "D")


class TestProjection(unittest.TestCase):
    def test_albers_preserves_area(self):
        """Two equal-area patches at different latitudes must project to equal areas.
        This is the property the whole statistical layer depends on."""
        proj = Albers()

        def patch_area(lat0):
            d = 0.5
            corners = [proj.forward(lon, lat) for lon, lat in
                       ((-100, lat0), (-100 + d, lat0), (-100 + d, lat0 + d), (-100, lat0 + d))]
            return abs(_shoelace(corners))

        # Equal graticule cells shrink with latitude by cos(lat); compare against that.
        a30, a50 = patch_area(30.0), patch_area(50.0)
        self.assertAlmostEqual(
            a50 / a30, math.cos(math.radians(50.25)) / math.cos(math.radians(30.25)), places=2
        )

    def test_antimeridian_does_not_fly_around_the_world(self):
        """Alaska and the Aleutians straddle 180 degrees. A naive lon-lon0 sends the
        far side of the dateline halfway around the planet."""
        proj = Albers(lon_0=-170.0)
        near = proj.forward(179.0, 52.0)
        far = proj.forward(-179.0, 52.0)
        self.assertLess(abs(near[0] - far[0]), 400_000.0)

    def test_auto_projection_picks_cylindrical_for_global_extent(self):
        from coincidence.projection import CylindricalEqualArea
        proj = auto_projection([0.0, 10.0], [-60.0, 60.0])
        self.assertIsInstance(proj, CylindricalEqualArea)

    def test_symmetric_parallels_rejected(self):
        with self.assertRaises(ValueError):
            Albers(lat_1=-30.0, lat_2=30.0)


class TestGrid(unittest.TestCase):
    def test_rasterize_conserves_weight(self):
        layer = Layer("t", [(-84.0, 37.2), (-92.5, 36.5)], [3.0, 7.0], tier="A")
        proj = auto_projection(layer.lons, layer.lats)
        xy = project_layer(layer, proj)
        grid = build_grid([xy], cell_km=50.0)
        self.assertAlmostEqual(sum(grid.rasterize(xy, layer.weights)), 10.0)

    def test_smoothing_conserves_mass_in_the_interior(self):
        grid = Grid(x_min=0.0, y_min=0.0, cell_m=1000.0, nx=41, ny=41)
        values = [0.0] * grid.n_cells
        values[20 * 41 + 20] = 100.0
        out = smooth(values, grid, sigma_cells=2.0)
        self.assertAlmostEqual(sum(out), 100.0, places=6)

    def test_points_outside_grid_are_not_silently_wrapped(self):
        grid = Grid(x_min=0.0, y_min=0.0, cell_m=1000.0, nx=5, ny=5)
        self.assertIsNone(grid.cell_of(-10.0, 0.0))
        self.assertIsNone(grid.cell_of(0.0, 999999.0))


class TestNulls(unittest.TestCase):
    def test_no_confounds_gives_one_stratum_flagged_uniform(self):
        grid = Grid(0.0, 0.0, 1000.0, 4, 4)
        strata = build_strata(grid, {})
        self.assertEqual(strata.n_strata, 1)
        self.assertTrue(strata.is_uniform)

    def test_zero_is_its_own_stratum(self):
        """'None here' is categorically different from 'a little here'. Letting zero
        dissolve into the bottom quantile smooths a hard precondition into a gradient."""
        grid = Grid(0.0, 0.0, 1000.0, 4, 1)
        strata = build_strata(grid, {"c": [0.0, 0.0, 5.0, 9.0]}, n_bins=2)
        self.assertEqual(strata.of_cell[0], strata.of_cell[1])
        self.assertNotEqual(strata.of_cell[0], strata.of_cell[2])

    def test_surrogate_conserves_mass_per_stratum(self):
        grid = Grid(0.0, 0.0, 1000.0, 6, 1)
        strata = build_strata(grid, {"c": [0.0, 0.0, 0.0, 9.0, 9.0, 9.0]}, n_bins=2)
        raster = [10.0, 0.0, 0.0, 0.0, 0.0, 6.0]
        totals = stratum_totals(raster, strata)
        sim = surrogate(totals, strata, random.Random(1))
        self.assertAlmostEqual(sum(sim), 16.0, places=6)
        for stratum, total in totals.items():
            got = sum(sim[i] for i in strata.cells[stratum])
            self.assertAlmostEqual(got, total, places=6)

    def test_surrogate_stays_inside_its_stratum(self):
        grid = Grid(0.0, 0.0, 1000.0, 6, 1)
        strata = build_strata(grid, {"c": [0.0, 0.0, 0.0, 9.0, 9.0, 9.0]}, n_bins=2)
        sim = surrogate(stratum_totals([0.0, 0.0, 0.0, 0.0, 0.0, 6.0], strata), strata,
                        random.Random(2))
        self.assertEqual(sum(sim[:3]), 0.0)


class TestColocation(unittest.TestCase):
    def test_identical_concentration_scores_high(self):
        a = [10.0, 0.0, 0.0, 0.0]
        self.assertGreater(colocation(a, a), colocation(a, [2.5] * 4))

    def test_disjoint_scores_zero(self):
        self.assertEqual(colocation([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_empty_layer_is_zero_not_an_error(self):
        self.assertEqual(colocation([0.0, 0.0], [1.0, 1.0]), 0.0)


def _cluster(rng, hotspots, n, spread):
    pts = []
    for _ in range(n):
        lon0, lat0 = hotspots[rng.randrange(len(hotspots))]
        pts.append((rng.gauss(lon0, spread), rng.gauss(lat0, spread * 0.7)))
    return pts


class TestTheThesis(unittest.TestCase):
    """The claim the whole project rests on, as an executable assertion."""

    HOTSPOTS = [(-84.0, 37.2), (-92.5, 36.5), (-104.5, 43.6),
                (-105.5, 32.2), (-121.5, 44.0), (-87.5, 20.5)]

    def setUp(self):
        rng = random.Random(20260811)
        self.a = Layer("a", _cluster(rng, self.HOTSPOTS, 220, 1.6), tier="A")
        self.b = Layer("b", _cluster(rng, self.HOTSPOTS, 260, 1.9), tier="A")
        self.c = Layer("c", _cluster(rng, self.HOTSPOTS, 900, 2.0), tier="A")

    def test_confounded_association_collapses_when_conditioned(self):
        """Two layers driven by a shared confound and independent of each other.

        The uniform null calls this a large, highly significant association. The
        conditional null shows almost all of it was the confound. This is the entire
        argument of the project, and if this test ever fails the tool is lying.
        """
        naive = test_pair(self.a, self.b, cell_km=50.0, n_sim=99, seed=7)
        conditioned = test_pair(self.a, self.b, confounds=[self.c], cell_km=50.0,
                                n_sim=99, n_bins=10, seed=7)

        self.assertGreater(naive.effect_ratio, 3.0)
        self.assertLess(conditioned.effect_ratio, 1.5)
        self.assertLess(conditioned.effect_ratio, naive.effect_ratio / 2.5)

    def test_uniform_null_is_flagged_as_uninformative(self):
        naive = test_pair(self.a, self.b, cell_km=50.0, n_sim=49, seed=3)
        self.assertTrue(naive.strata["uniform_null"])
        self.assertTrue(any("uniform null" in w for w in naive.warnings))
        self.assertIn("close to meaningless", naive.statement())

    def test_genuinely_independent_layers_show_no_association(self):
        """Two layers scattered independently across the same region must come back
        as unrelated. If the tool cannot return a negative result it is useless."""
        rng = random.Random(99)
        box = lambda n: [(rng.uniform(-120.0, -80.0), rng.uniform(28.0, 48.0)) for _ in range(n)]
        x = Layer("x", box(400), tier="A")
        y = Layer("y", box(400), tier="A")
        result = test_pair(x, y, cell_km=100.0, n_sim=99, seed=5)
        self.assertLess(abs(result.effect_ratio - 1.0), 0.1)
        self.assertFalse(result.beats_null)

    def _coupled_pair(self, jitter_deg=0.05):
        """b is a jittered copy of a — genuinely associated at ~5 km, on top of the
        same hotspot structure the confound explains."""
        rng = random.Random(5)
        a = Layer("a", _cluster(rng, self.HOTSPOTS, 220, 1.6), tier="A")
        b = Layer("b", [(lon + rng.gauss(0, jitter_deg), lat + rng.gauss(0, jitter_deg))
                        for lon, lat in a.points], tier="A")
        c = Layer("c", _cluster(rng, self.HOTSPOTS, 900, 2.0), tier="A")
        return a, b, c

    def test_genuine_association_is_still_detected(self):
        """The noise floor must not be so high that the tool can no longer find
        anything. A layer built by jittering another must survive conditioning on the
        confound that explains their shared coarse structure."""
        a, b, c = self._coupled_pair()
        result = test_pair(a, b, confounds=[c], cell_km=50.0, n_sim=99, n_bins=10,
                           seed=7, sigma_cells=1.0)
        self.assertGreater(result.effect_ratio, 1.3)
        self.assertTrue(result.beats_null)
        self.assertIn("co-locate", result.statement())

    def test_bandwidth_is_the_scale_of_the_question(self):
        """Not a bug and not an artifact: the kernel bandwidth sets which spatial
        scale is being interrogated. Layers coupled at ~5 km read as a strong
        association under a tight kernel and as almost nothing under a wide one. Both
        are correct answers to different questions, which is exactly why the bandwidth
        has to be reported next to the ratio."""
        a, b, c = self._coupled_pair()
        tight = test_pair(a, b, confounds=[c], cell_km=50.0, n_sim=49, n_bins=10,
                          seed=7, sigma_cells=0.5)
        wide = test_pair(a, b, confounds=[c], cell_km=50.0, n_sim=49, n_bins=10,
                         seed=7, sigma_cells=4.0)
        self.assertGreater(tight.effect_ratio, wide.effect_ratio * 2.0)
        self.assertAlmostEqual(tight.bandwidth_km, 25.0)
        self.assertAlmostEqual(wide.bandwidth_km, 200.0)

    def test_sensitivity_sweeps_both_axes(self):
        a, b, c = self._coupled_pair()
        sweeps = sensitivity(a, b, confounds=[c], cell_sizes=(50.0, 100.0),
                             sigmas=(1.0, 2.0), n_sim=19, n_bins=5, seed=1)
        self.assertEqual(len(sweeps["cell_size"]), 2)
        self.assertEqual(len(sweeps["bandwidth"]), 2)
        self.assertNotEqual(sweeps["bandwidth"][0].bandwidth_km,
                            sweeps["bandwidth"][1].bandwidth_km)

    def test_tiny_effect_with_small_p_is_reported_as_no_association(self):
        """A significant p on a trivial effect is a property of the simulation count,
        not evidence. The statement has to say so."""
        from coincidence.analysis import NOISE_FLOOR, TestResult
        r = TestResult(
            layer_a="a", layer_b="b", observed=1.02, null_mean=1.0, null_sd=0.005,
            null_lo=0.99, null_hi=1.01, p_value=0.001, n_sim=999,
            effect_ratio=1.02, z_score=4.0, grid={}, strata={"confounds": ["c"]},
            tier="A", descriptive_only=False,
        )
        self.assertLess(1.02 - 1.0, NOISE_FLOOR)
        self.assertFalse(r.beats_null)
        self.assertIn("noise floor", r.statement())

    def test_null_respects_the_observation_window(self):
        """Regression test for a false-positive generator.

        A grid is a rectangle; the region data actually occupies is not. Left
        unmasked, roughly three quarters of the grid for a projected lon/lat box is
        territory no observation could have come from. A null that scatters surrogates
        into that void makes the real data look concentrated together, and two
        independent layers came back at 1.23x, p = 0.01 before the window was added.
        """
        from coincidence.grid import build_grid, observation_window, project_layer
        from coincidence.projection import auto_projection

        rng = random.Random(99)
        pts = [(rng.uniform(-120.0, -80.0), rng.uniform(28.0, 48.0)) for _ in range(400)]
        layer = Layer("x", pts, tier="A")
        proj = auto_projection(layer.lons, layer.lats)
        xy = project_layer(layer, proj)
        grid = build_grid([xy], cell_km=100.0)
        window = observation_window([xy], grid, dilate_cells=1)

        self.assertLess(sum(window), grid.n_cells,
                        "window must exclude the empty margin")
        self.assertGreater(sum(window), 0)

    def test_window_excludes_cells_from_the_statistic(self):
        a = [1.0, 0.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0, 0.0]
        full = colocation(a, b)
        masked = colocation(a, b, [True, True, False, False])
        self.assertNotAlmostEqual(full, masked)
        self.assertAlmostEqual(masked, 2.0)

    def test_tier_c_input_is_marked_descriptive_only(self):
        asserted = Layer("clusters", self.b.points, tier="C")
        result = test_pair(self.a, asserted, confounds=[self.c], cell_km=50.0, n_sim=49)
        self.assertEqual(result.tier, "C")
        self.assertTrue(result.descriptive_only)
        self.assertTrue(any("no denominator" in w for w in result.warnings))

    def test_result_bundle_carries_its_own_provenance(self):
        result = test_pair(self.a, self.b, confounds=[self.c], cell_km=100.0, n_sim=49)
        d = result.to_dict()
        self.assertEqual(d["null"]["specification"]["confounds"], ["c"])
        self.assertIn("statement", d)
        self.assertEqual(d["evidence_tier"], "A")

    def test_small_sample_is_warned_about(self):
        tiny = Layer("tiny", self.a.points[:12], tier="A")
        result = test_pair(tiny, self.b, confounds=[self.c], cell_km=100.0, n_sim=49)
        self.assertTrue(any("Small sample" in w for w in result.warnings))

    def test_p_value_can_never_be_zero(self):
        result = test_pair(self.a, self.b, cell_km=50.0, n_sim=19, seed=1)
        self.assertGreater(result.p_value, 0.0)


class TestFastNullIsTheSameNull(unittest.TestCase):
    """The simulation loop does not smooth. It hoists the convolution onto the fixed
    side using the fact that Gaussian smoothing is self-adjoint, which is an exact
    rearrangement — so it has to agree with the literal version to floating point, not
    approximately. If this ever drifts, every number the tool prints is wrong."""

    def setUp(self):
        rng = random.Random(4)
        hot = [(-84.0, 37.2), (-100.0, 40.0), (-115.0, 35.0)]
        self.a = Layer("a", _cluster(rng, hot, 150, 1.5), tier="A")
        self.b = Layer("b", _cluster(rng, hot, 170, 1.8), tier="A")
        self.c = Layer("c", _cluster(rng, hot, 500, 2.0), tier="A")

    def test_matches_the_literal_smooth_every_surrogate_version(self):
        from coincidence.analysis import _simulate, colocation, prepare
        from coincidence.nulls import stratum_totals, surrogate

        prep = prepare(self.a, self.b, confounds=[self.c], cell_km=75.0, n_bins=6)
        observed = colocation(prep.intensity_a, prep.intensity_b, prep.window)

        totals = stratum_totals(prep.raster_a, prep.strata)
        rng = random.Random(11)
        slow = [
            colocation(prep.intensity(surrogate(totals, prep.strata, rng)),
                       prep.intensity_b, prep.window)
            for _ in range(20)
        ]
        fast = _simulate(prep, move_raster=prep.raster_a, fixed=prep.intensity_b,
                         label="a", observed=observed, n_sim=20, seed=11).values

        for s, f in zip(slow, fast):
            self.assertAlmostEqual(s, f, places=9)

    def test_smoothing_is_self_adjoint(self):
        """The identity the whole rearrangement rests on."""
        grid = Grid(0.0, 0.0, 1000.0, 13, 11)
        rng = random.Random(0)
        s = [rng.random() for _ in range(grid.n_cells)]
        t = [rng.random() for _ in range(grid.n_cells)]
        self.assertAlmostEqual(
            sum(x * y for x, y in zip(smooth(s, grid, 1.7), t)),
            sum(x * y for x, y in zip(s, smooth(t, grid, 1.7))),
            places=10,
        )

    def test_surrogate_dot_agrees_with_building_the_surrogate(self):
        from coincidence.nulls import surrogate_dot
        grid = Grid(0.0, 0.0, 1000.0, 8, 1)
        strata = build_strata(grid, {"c": [0.0, 0.0, 1.0, 1.0, 5.0, 5.0, 9.0, 9.0]},
                              n_bins=3)
        totals = stratum_totals([4.0, 0.0, 3.0, 0.0, 0.0, 6.0, 2.0, 0.0], strata)
        weights = [float(i) for i in range(8)]
        built = surrogate(totals, strata, random.Random(3))
        dotted = surrogate_dot(totals, strata, random.Random(3), [weights])
        self.assertAlmostEqual(sum(x * w for x, w in zip(built, weights)), dotted[0],
                               places=9)


class TestWeightedLayersTerminate(unittest.TestCase):
    def test_a_heavily_weighted_layer_does_not_draw_forever(self):
        """A layer weighted by population can total millions. One draw per unit of
        weight would make the tool appear to hang; the cap keeps the realization
        plausible and the mass exact."""
        from coincidence.nulls import MAX_DRAWS, surrogate
        grid = Grid(0.0, 0.0, 1000.0, 4, 1)
        strata = build_strata(grid, {"c": [1.0, 1.0, 1.0, 1.0]}, n_bins=2)
        sim = surrogate({0: 5_000_000.0}, strata, random.Random(0))
        self.assertAlmostEqual(sum(sim), 5_000_000.0, places=3)
        self.assertLessEqual(MAX_DRAWS, 50_000)


class TestBothDirectionsOfTheNull(unittest.TestCase):
    """Resampling A against a fixed B and resampling B against a fixed A are different
    tests of the same hypothesis. Reporting only the first makes the answer depend on
    argument order."""

    def setUp(self):
        rng = random.Random(31)
        hot = [(-84.0, 37.2), (-100.0, 40.0), (-115.0, 35.0)]
        self.a = Layer("a", _cluster(rng, hot, 160, 1.5), tier="A")
        self.b = Layer("b", _cluster(rng, hot, 300, 2.4), tier="A")
        self.c = Layer("c", _cluster(rng, hot, 600, 2.0), tier="A")

    def test_both_directions_are_run_and_recorded(self):
        r = test_pair(self.a, self.b, confounds=[self.c], n_sim=49, seed=2)
        self.assertEqual(len(r.nulls), 2)
        self.assertEqual({n.resampled for n in r.nulls}, {"a", "b"})
        self.assertEqual(len(r.to_dict()["null"]["directions"]), 2)

    def test_the_conservative_direction_is_the_one_reported(self):
        r = test_pair(self.a, self.b, confounds=[self.c], n_sim=49, seed=2)
        claims = [abs(n.effect_ratio - 1.0) for n in r.nulls]
        self.assertAlmostEqual(abs(r.effect_ratio - 1.0), min(claims))
        self.assertAlmostEqual(r.p_value, max(n.p_value for n in r.nulls))

    def test_argument_order_no_longer_changes_the_verdict(self):
        forward = test_pair(self.a, self.b, confounds=[self.c], n_sim=99, seed=2)
        reverse = test_pair(self.b, self.a, confounds=[self.c], n_sim=99, seed=2)
        self.assertEqual(forward.verdict, reverse.verdict)
        self.assertAlmostEqual(forward.effect_ratio, reverse.effect_ratio, places=9)

    def test_one_way_is_still_available_and_is_asymmetric(self):
        r = test_pair(self.a, self.b, confounds=[self.c], n_sim=49, seed=2,
                      both_directions=False)
        self.assertEqual(len(r.nulls), 1)
        self.assertEqual(r.nulls[0].resampled, "a")


class TestSensitivitySweepsIsolateOneThing(unittest.TestCase):
    def setUp(self):
        rng = random.Random(77)
        hot = [(-84.0, 37.2), (-100.0, 40.0), (-115.0, 35.0)]
        self.a = Layer("a", _cluster(rng, hot, 200, 1.5), tier="A")
        self.b = Layer("b", _cluster(rng, hot, 200, 1.5), tier="A")

    def test_cell_size_sweep_holds_the_bandwidth_fixed_in_km(self):
        """Regression test for a false-positive generator.

        Bandwidth was specified in CELLS, so sweeping cell size swept bandwidth with
        it: 25/50/100 km cells carried 61/122/244 km kernels. The tool then attributed
        a scale effect to the modifiable areal unit problem and advised discarding it.
        """
        sweeps = sensitivity(self.a, self.b, cell_sizes=(25.0, 50.0, 100.0),
                             cell_km=50.0, n_sim=19, seed=1)
        bandwidths = [r.bandwidth_km for r in sweeps["cell_size"]]
        for bw in bandwidths[1:]:
            self.assertAlmostEqual(bw, bandwidths[0], places=6)
        self.assertEqual(len({r.grid["cell_km"] for r in sweeps["cell_size"]}), 3)

    def test_bandwidth_sweep_holds_the_cell_size_fixed(self):
        sweeps = sensitivity(self.a, self.b, sigmas=(1.0, 2.0, 4.0), cell_km=50.0,
                             n_sim=19, seed=1)
        self.assertEqual({r.grid["cell_km"] for r in sweeps["bandwidth"]}, {50.0})
        self.assertEqual([r.bandwidth_km for r in sweeps["bandwidth"]],
                         [50.0, 100.0, 200.0])


def _crescent_ring(n=72):
    """A deliberately concave study region. Its convex hull covers roughly twice the
    area, which is the geometry the inferred window handles worst."""
    ring = []
    for k in range(n + 1):
        t = math.radians(-140 + k * (280 / n))
        ring.append((-100 + 6.0 * math.cos(t), 40 + 4.0 * math.sin(t)))
    for k in range(n + 1):
        t = math.radians(140 - k * (280 / n))
        ring.append((-100 + 3.4 * math.cos(t), 40 + 2.3 * math.sin(t)))
    return ring


class TestDeclaredBoundary(unittest.TestCase):
    """A supplied study boundary replaces the inferred convex hull.

    This is not a convenience. On a concave region the hull is not approximately right,
    it is wrong in a way that manufactures findings.
    """

    def setUp(self):
        from coincidence.boundary import Boundary, rings_contain
        self.ring = _crescent_ring()
        self.boundary = Boundary(rings=[self.ring], source="crescent")
        rng = random.Random(4242)

        def inside(n):
            out = []
            while len(out) < n:
                p = (rng.uniform(-107.0, -93.0), rng.uniform(34.0, 46.0))
                if rings_contain([self.ring], *p):
                    out.append(p)
            return out

        self.x = Layer("x", inside(350), tier="A")
        self.y = Layer("y", inside(350), tier="A")

    def test_the_hull_manufactures_a_finding_the_boundary_removes(self):
        """Regression test for a false-positive generator, and the reason --boundary
        exists. Two layers scattered independently inside a crescent read as strongly
        associated under the inferred hull, because the hull's null scatters surrogates
        across the empty middle. The measured effect is ~1.3x — three times the noise
        floor that is supposed to suppress exactly this."""
        hull = test_pair(self.x, self.y, cell_km=40.0, n_sim=99, seed=3)
        bounded = test_pair(self.x, self.y, cell_km=40.0, n_sim=99, seed=3,
                            boundary=self.boundary)

        self.assertGreater(hull.effect_ratio, 1.20)
        self.assertTrue(hull.beats_null)          # the false positive
        self.assertLess(abs(bounded.effect_ratio - 1.0), 0.04)
        self.assertFalse(bounded.beats_null)      # corrected

    def test_the_window_shrinks_to_the_declared_region(self):
        hull = test_pair(self.x, self.y, cell_km=40.0, n_sim=19, seed=3)
        bounded = test_pair(self.x, self.y, cell_km=40.0, n_sim=19, seed=3,
                            boundary=self.boundary)
        self.assertLess(bounded.strata["window_cells"], hull.strata["window_cells"] * 0.75)
        self.assertTrue(bounded.window["declared"])
        self.assertFalse(hull.window["declared"])

    def test_declaring_a_boundary_lowers_the_noise_floor(self):
        from coincidence.analysis import BOUNDED_NOISE_FLOOR, NOISE_FLOOR
        hull = test_pair(self.x, self.y, cell_km=40.0, n_sim=19, seed=3)
        bounded = test_pair(self.x, self.y, cell_km=40.0, n_sim=19, seed=3,
                            boundary=self.boundary)
        self.assertEqual(hull.noise_floor, NOISE_FLOOR)
        self.assertEqual(bounded.noise_floor, BOUNDED_NOISE_FLOOR)
        self.assertLess(BOUNDED_NOISE_FLOOR, NOISE_FLOOR)

    def test_a_concave_inferred_window_is_warned_about(self):
        """The floor does not catch this case, so the tool has to say so out loud."""
        hull = test_pair(self.x, self.y, cell_km=40.0, n_sim=19, seed=3)
        self.assertTrue(any("--boundary" in w for w in hull.warnings))

    def test_a_convex_extent_is_not_warned_about(self):
        rng = random.Random(11)
        box = lambda n: [(rng.uniform(-105.0, -95.0), rng.uniform(36.0, 44.0))
                         for _ in range(n)]
        r = test_pair(Layer("p", box(300), tier="A"), Layer("q", box(300), tier="A"),
                      cell_km=40.0, n_sim=19, seed=3)
        self.assertFalse(any("--boundary" in w for w in r.warnings))

    def test_observations_outside_the_boundary_are_dropped_and_reported(self):
        """Keeping them would let an outside point smooth into the window and raise the
        observed statistic while contributing nothing to the null."""
        stray = Layer("x", self.x.points + [(-130.0, 55.0), (-131.0, 56.0)], tier="A")
        r = test_pair(stray, self.y, cell_km=40.0, n_sim=19, seed=3,
                      boundary=self.boundary)
        self.assertEqual(r.window["points_outside"], {"x": 2})
        self.assertTrue(any("outside the declared boundary" in w for w in r.warnings))

    def test_a_boundary_missing_the_data_is_an_error_not_a_silent_zero(self):
        from coincidence.boundary import Boundary
        far = Boundary(rings=[[(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0)]],
                       source="elsewhere")
        with self.assertRaises(ValueError):
            test_pair(self.x, self.y, cell_km=40.0, n_sim=9, boundary=far)


class TestBoundaryLoading(unittest.TestCase):
    def _geojson(self, geometry) -> str:
        return _tmp("bnd.geojson", json.dumps(geometry))

    def test_feature_collection_polygon(self):
        from coincidence.boundary import load_boundary
        ring = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
        path = self._geojson({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": [ring]}}]})
        b = load_boundary(path)
        self.assertEqual(len(b), 1)
        self.assertEqual(b.n_vertices, 4)  # closing vertex dropped

    def test_multipolygon_and_bare_geometry(self):
        from coincidence.boundary import load_boundary
        sq = lambda x: [[x, 0.0], [x + 1, 0.0], [x + 1, 1.0], [x, 1.0], [x, 0.0]]
        self.assertEqual(len(load_boundary(self._geojson(
            {"type": "MultiPolygon", "coordinates": [[sq(0.0)], [sq(5.0)]]}))), 2)
        self.assertEqual(len(load_boundary(self._geojson(
            {"type": "Polygon", "coordinates": [sq(0.0)]}))), 1)

    def test_holes_are_holes(self):
        from coincidence.boundary import load_boundary, rings_contain
        outer = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
        hole = [[4.0, 4.0], [6.0, 4.0], [6.0, 6.0], [4.0, 6.0], [4.0, 4.0]]
        b = load_boundary(self._geojson(
            {"type": "Polygon", "coordinates": [outer, hole]}))
        self.assertTrue(rings_contain(b.rings, 1.0, 1.0))
        self.assertFalse(rings_contain(b.rings, 5.0, 5.0))   # in the hole
        self.assertFalse(rings_contain(b.rings, 20.0, 20.0))  # outside entirely

    def test_a_line_is_not_a_study_region(self):
        from coincidence.boundary import BoundaryError, load_boundary
        with self.assertRaises(BoundaryError):
            load_boundary(self._geojson(
                {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}))

    def test_long_edges_are_densified_before_projection(self):
        from coincidence.boundary import densify
        ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        self.assertGreater(len(densify(ring, max_deg=0.25)), 100)
        self.assertEqual(len(densify(ring, max_deg=0.0)), 4)

    def test_a_non_geojson_boundary_is_refused_clearly(self):
        from coincidence.boundary import BoundaryError, load_boundary
        with self.assertRaises(BoundaryError):
            load_boundary(_tmp("b.csv", "lon,lat\n0,0\n"))


class TestPresentation(unittest.TestCase):
    """The display must not be able to argue for a conclusion the numbers have not
    earned — but it does have to be readable."""

    def test_null_plot_marks_an_observation_outside_the_null(self):
        from coincidence.console import Style, null_plot
        rng = random.Random(0)
        values = [rng.gauss(1.0, 0.02) for _ in range(400)]
        lines = null_plot(values, 1.4, Style(False), cols=80)
        self.assertTrue(any("▲" in line for line in lines))
        self.assertTrue(any("outside" in line for line in lines))

    def test_null_plot_survives_a_degenerate_null(self):
        from coincidence.console import Style, null_plot
        self.assertEqual(null_plot([], 1.0, Style(False)), [])
        self.assertTrue(null_plot([1.0] * 40, 1.0, Style(False)))

    def test_style_is_inert_when_disabled(self):
        from coincidence.console import Style
        self.assertEqual(Style(False)("x", "bold", "red"), "x")
        self.assertIn("x", Style(True)("x", "bold"))

    def test_report_is_one_self_contained_file(self):
        import base64
        import re
        import struct

        from coincidence.analysis import prepare
        from coincidence.report import render

        rng = random.Random(8)
        hot = [(-84.0, 37.2), (-100.0, 40.0)]
        a = Layer("a", _cluster(rng, hot, 120, 1.5), tier="A")
        b = Layer("b", _cluster(rng, hot, 140, 1.5), tier="A")
        c = Layer("c", _cluster(rng, hot, 400, 2.0), tier="A")

        prep = prepare(a, b, confounds=[c], cell_km=100.0, n_bins=4)
        result = test_pair(a, b, confounds=[c], cell_km=100.0, n_sim=49, prep=prep)
        bundle = {"tool": "coincidence", "version": "test",
                  "inputs": [a.provenance(), b.provenance(), c.provenance()],
                  "parameters": {"seed": 0}, "result": result.to_dict()}
        page = render(result, prep, bundle)

        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)
        self.assertIn(result.verdict, page.lower())
        pngs = re.findall(r"data:image/png;base64,([A-Za-z0-9+/=]+)", page)
        self.assertEqual(len(pngs), 4)  # a, b, a-under-null, and the confound
        raw = base64.b64decode(pngs[0])
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
        w, h = struct.unpack(">II", raw[16:24])
        self.assertEqual((w, h), (prep.grid.nx, prep.grid.ny))

    def test_a_negative_result_gets_the_same_treatment_as_a_positive(self):
        """Not a style preference. A UI that renders 'no association' as smaller or
        greyer undoes in presentation what the engine exists to do."""
        from coincidence.cli import VERDICT_LABEL
        self.assertEqual(len(VERDICT_LABEL), 3)
        for label, colour in VERDICT_LABEL.values():
            self.assertTrue(label.isupper())
            self.assertTrue(colour)


class TestCommandLine(unittest.TestCase):
    def _run(self, argv) -> tuple[int, str]:
        from coincidence.cli import main
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_demo_runs_and_shows_the_collapse(self):
        code, out = self._run(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("worked example", out)
        self.assertIn("confound", out)

    def test_describe_reports_drops_without_guessing(self):
        path = _tmp("d.csv", "lon,lat\n-84.0,37.2\n,\n-92.5,36.5\n")
        code, out = self._run(["describe", path])
        self.assertEqual(code, 0)
        self.assertIn("dropped", out)

    def test_unidentifiable_columns_show_what_the_file_actually_has(self):
        path = _tmp("d.csv", "alpha,beta\n1.5,2.5\n")
        code, out = self._run(["describe", path])
        self.assertEqual(code, 2)
        self.assertIn("alpha", out)
        self.assertIn("2.5", out)  # a sample value, not just the column name
        self.assertIn("--lat", out)

    def test_test_command_writes_a_bundle_and_a_report(self):
        d = tempfile.mkdtemp()
        rows = "lon,lat\n" + "\n".join(
            f"{-100 + i * 0.1},{40 + (i % 7) * 0.1}" for i in range(60)
        )
        a, b = _tmp("a.csv", rows), _tmp("b.csv", rows)
        bundle, report = os.path.join(d, "x.json"), os.path.join(d, "x.html")
        code, out = self._run(["test", a, b, "--sim", "19", "--no-color",
                               "--export", bundle, "--report", report])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(bundle))
        self.assertTrue(os.path.exists(report))
        with open(bundle, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertIn("statement", saved["result"])
        self.assertIn("uniform", out.lower())  # no confounds: it must say so

    def test_boundary_flag_end_to_end(self):
        ring = [[list(p) for p in _crescent_ring(24)]]
        ring[0].append(ring[0][0])
        bnd = _tmp("area.geojson", json.dumps(
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": ring}}))
        rng = random.Random(9)
        from coincidence.boundary import rings_contain
        poly = [tuple(p) for p in ring[0]]
        pts = []
        while len(pts) < 120:
            p = (rng.uniform(-107.0, -93.0), rng.uniform(34.0, 46.0))
            if rings_contain([poly], *p):
                pts.append(p)
        rows = "lon,lat\n" + "\n".join(f"{x},{y}" for x, y in pts)
        code, out = self._run(["test", _tmp("a.csv", rows), _tmp("b.csv", rows),
                               "--boundary", bnd, "--cell-km", "40", "--sim", "19",
                               "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn("declared boundary", out)
        self.assertIn("floor 4%", out)

    def test_a_bad_boundary_file_fails_cleanly(self):
        code, out = self._run(["test", _tmp("a.csv", "lon,lat\n-100,40\n-101,41\n"),
                               _tmp("b.csv", "lon,lat\n-100,40\n-101,41\n"),
                               "--boundary", _tmp("b.geojson", "{}"), "--sim", "9"])
        self.assertEqual(code, 2)
        self.assertIn("Polygon", out)

    def test_json_output_is_parseable(self):
        rows = "lon,lat\n" + "\n".join(
            f"{-100 + i * 0.1},{40 + (i % 5) * 0.1}" for i in range(40)
        )
        code, out = self._run(["test", _tmp("a.csv", rows), _tmp("b.csv", rows),
                               "--sim", "19", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["tool"], "coincidence")


def _shoelace(pts):
    return 0.5 * sum(
        pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
        for i in range(len(pts))
    )


if __name__ == "__main__":
    unittest.main()
