"""Leakage, calibration and reproducibility checks using explicitly synthetic data."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

import calibration as c
import elo_challenger as elo
import model_lab
import runner

AS_OF = datetime(2026, 11, 6, 18, tzinfo=timezone.utc)


def sample(n=260, leagues=("Premier League", "Ligue 1")):
    rows = []
    for i in range(n):
        for offset, league in enumerate(leagues):
            rows.append({"league": league, "date": (date(2025, 1, 1)+timedelta(days=i)).isoformat(),
                         "home": "Team A" if i % 2 else "Team B",
                         "away": "Team B" if i % 2 else "Team A",
                         "gh": (i+offset) % 4, "ga": (i*3+offset) % 3,
                         "yh": i % 4, "ya": 2, "ch": 4+i % 4, "ca": 5,
                         "fh": 10+i % 5, "fa": 11})
    return rows


class DataAndSplits(unittest.TestCase):
    def test_duplicates_conflicts_and_future_are_not_independent_examples(self):
        row = sample(1)[0]
        conflict = {**row, "date": "2025-01-02", "gh": 1}
        future = {**row, "date": "2026-11-06"}
        rows, audit = c.prepare_history([row, dict(row), conflict, {**conflict, "gh": 2}, future], AS_OF)
        self.assertEqual(len(rows), 1)
        self.assertEqual(audit["rejected"]["duplicate_copy"], 1)
        self.assertEqual(audit["rejected"]["conflicting_event"], 2)
        self.assertEqual(audit["rejected"]["today_or_future_result"], 1)
        self.assertEqual(c.prepare_history([row], AS_OF)[1]["input_sha256"], audit["input_sha256"])

    def test_snapshot_hash_is_order_and_numeric_representation_invariant(self):
        rows = sample(12)
        reverse = [{**r, "gh": float(r["gh"])} for r in reversed(rows)]
        self.assertEqual(c.prepare_history(rows, AS_OF)[1]["input_sha256"],
                         c.prepare_history(reverse, AS_OF)[1]["input_sha256"])

    def test_malformed_team_identities_and_noninteger_counts_are_rejected(self):
        row = sample(1)[0]
        rows, audit = c.prepare_history([{**row, "home": None}, {**row, "gh": .5},
                                         {**row, "ga": float("nan")}, {**row, "gh": True}], AS_OF)
        self.assertEqual(rows, [])
        self.assertEqual(audit["rejected"]["invalid_row"], 4)

    def test_one_global_day_boundary_prevents_cross_league_time_leakage(self):
        rows = sample(120)
        # One league has fewer observations, but cannot obtain an earlier holdout boundary.
        rows = [r for r in rows if r["league"] == "Ligue 1" or r["date"] < "2025-02-01"]
        boundaries = c.date_splits(rows)
        groups = {phase: {r["date"] for r in rows if c.split_for(r["date"], boundaries) == phase}
                  for phase in ("training", "validation", "calibration", "holdout")}
        phases = list(groups)
        for a, b in zip(phases, phases[1:]):
            self.assertLess(max(groups[a]), min(groups[b]))
        for day in set(r["date"] for r in rows):
            self.assertEqual(len({c.split_for(r["date"], boundaries) for r in rows if r["date"] == day}), 1)

    def test_missing_data_has_json_null_not_nonstandard_infinity(self):
        report = c.compare_1x2([], as_of=AS_OF)
        self.assertEqual(report["holdout"]["n"], 0)
        self.assertIsNone(report["holdout"]["models"]["elo"]["log_loss"])
        self.assertFalse(report["production_model_changed"])
        json.dumps(report, allow_nan=False)


class EloChronology(unittest.TestCase):
    def setUp(self):
        self.params = elo.CANDIDATES["elo_balanced"]

    def test_replay_prediction_never_uses_results_after_replay_date(self):
        rows = sample(100, ("Premier League",))
        target = {**rows[60], "date": rows[60]["date"]}
        all_history = elo.process(rows, self.params, [target], AS_OF)[1]
        prior_history = elo.process(rows[:60], self.params, [target], AS_OF)[1]
        self.assertEqual(all_history[runner.key(target)], prior_history[runner.key(target)])
        self.assertEqual(all_history[runner.key(target)]["games_home"], 60)

    def test_same_day_predictions_use_same_prior_ratings(self):
        rows = [{"league": "Premier League", "date": "2025-08-01", "home": "Team A", "away": "Team B", "gh": 3, "ga": 0},
                {"league": "Premier League", "date": "2025-08-01", "home": "Team A", "away": "Team C", "gh": 1, "ga": 0}]
        history, _ = elo.process(rows, self.params, as_of=AS_OF)
        self.assertTrue(all(r["rating_home"] == elo.BASE for r in history.values()))

    def test_same_names_in_different_leagues_never_share_ratings(self):
        rows = sample(40, ("Premier League",))
        target = {"league": "Ligue 1", "date": "2025-05-01", "home": "Team A", "away": "Team B"}
        p = elo.process(rows, self.params, [target], AS_OF)[1][runner.key(target)]
        self.assertEqual(p["games_home"], 0)
        self.assertEqual(p["rating_home"], elo.BASE)

    def test_upcoming_new_season_applies_regression_before_prediction(self):
        row = {"league": "Premier League", "date": "2024-08-01", "home": "Team A", "away": "Team B", "gh": 3, "ga": 0}
        fixture = {**row, "date": "2026-08-01"}
        p = elo.process([row], self.params, [fixture], AS_OF)[1][runner.key(fixture)]
        delta = self.params["k"]*(1-elo.expected_points(elo.probs(elo.BASE, elo.BASE, self.params)))
        self.assertAlmostEqual(p["rating_home"], round(elo.BASE+delta*elo.RETURN_FACTOR**2, 1))
        self.assertEqual(p["games_home"], 1)

    def test_future_result_cannot_change_ratings(self):
        row = sample(1, ("Premier League",))[0]
        future = {**row, "date": "2026-12-01", "gh": 9}
        target = {**row, "date": "2026-11-07"}
        a = elo.process([row], self.params, [target], AS_OF)[1]
        b = elo.process([row, future], self.params, [target], AS_OF)[1]
        self.assertEqual(a, b)


class CalibrationAndEvaluation(unittest.TestCase):
    def test_temperature_softens_overconfidence_on_calibration_only(self):
        records = [{"p": {"home": .96, "draw": .02, "away": .02}, "y": ("home", "draw", "away")[i % 3]}
                   for i in range(60)]
        temperature, status = c.choose_temperature(records, "p")
        self.assertGreater(temperature, 1)
        raw = sum(c.logloss(r["p"], r["y"]) for r in records)
        softened = sum(c.logloss(c.temperature_scale(r["p"], temperature), r["y"]) for r in records)
        self.assertLess(softened, raw)
        self.assertEqual(status, "fit_on_calibration_window_only")
        self.assertEqual(c.choose_temperature(records[:3], "p")[0], 1.)
        for record in records:
            self.assertAlmostEqual(sum(c.temperature_scale(record["p"], temperature).values()), 1)
        with self.assertRaises(ValueError):
            c.temperature_scale({"home": .9, "draw": .9, "away": .9}, 1.)

    def test_final_outcomes_do_not_choose_candidates_weight_or_temperature(self):
        rows = sample(240)
        first = c.compare_1x2(rows, as_of=AS_OF)
        boundary = first["protocol"]["split_dates"]["holdout_start"]
        modified = [{**r, "gh": 0, "ga": 7} if r["date"] >= boundary else r for r in rows]
        second = c.compare_1x2(modified, as_of=AS_OF)
        self.assertEqual(first["selected"], second["selected"])
        self.assertEqual(first["selection_scores"], second["selection_scores"])
        self.assertNotEqual(first["holdout"]["models"]["poisson"]["log_loss"],
                            second["holdout"]["models"]["poisson"]["log_loss"])
        n = first["holdout"]["n"]
        self.assertGreater(n, 0)
        self.assertTrue(all(v["n"] == n for v in first["holdout"]["models"].values()))
        self.assertFalse(first["verified_value"])
        self.assertEqual(first["market_baseline"]["status"], "unavailable")
        json.dumps(first, allow_nan=False)

    def test_week_block_interval_does_not_count_same_week_as_independent_blocks(self):
        points = [("2025-01-01", .1)]*30
        insufficient = c.weekly_interval(points)
        self.assertEqual(insufficient["blocks"], 1)
        self.assertIsNone(insufficient["approx_95_ci"])
        points += [("2025-02-01", .2), ("2025-03-01", -.3), ("2025-04-01", .4)]
        first = c.weekly_interval(points)
        self.assertEqual(first, c.weekly_interval(list(reversed(points))))
        self.assertEqual(first["blocks"], 4)
        self.assertEqual(first["n"], 33)
        self.assertEqual(len(first["approx_95_ci"]), 2)

    def test_calibration_bins_do_not_double_count_exact_boundaries(self):
        records = [{"date": "2025-01-01", "p": {"home": .2, "draw": .4, "away": .4}, "y": "home"}]
        report = c.summarize(records, "p")
        for outcome in c.OUTCOMES:
            self.assertEqual(sum(b["n"] for b in report["bins"] if b["outcome"] == outcome), 1)


class MarketProvenance(unittest.TestCase):
    def setUp(self):
        self.event = {"league": "Premier League", "date": "2025-08-01", "home": "Team A", "away": "Team B"}
        self.frozen = {**self.event, "market": "h2h", "created_at": "2025-08-01T09:00:00Z",
                       "kickoff_utc": "2025-08-01T18:00:00Z", "settled_at": "2025-08-01T21:00:00Z",
                       "settled": True, "actual_outcome": "home", "pipeline_version": "test_v2",
                       "probabilities": {"home": .6, "draw": .2, "away": .2}}
        self.record = {**self.event, "event": runner.key(self.event), "y": "home",
                       "pipeline_version": "test_v2",
                       "poisson": {"home": .5, "draw": .25, "away": .25}}
        self.observations = [{**self.event, "outcome": outcome, "odds": price, "bookmaker_id": "synthetic-test",
                              "market_key": "h2h", "line": None, "quote_timestamp": "2025-08-01T10:00:00Z",
                              "model_pipeline_version": "test_v2",
                              "model_generated_at": "2025-08-01T09:55:00Z",
                              "provider": "Synthetic fixture", "provider_region": "uk", "provider_event_id": "test-event",
                              "observed_at": "2025-08-01T10:05:00Z", "commence_time": self.frozen["kickoff_utc"],
                              "settlement_rules_status": "verified", "settlement_rule": "90_minutes_plus_stoppage",
                              "settlement_evidence": "Synthetic fixture, never used in published output"}
                             for outcome, price in (("home", 2.), ("draw", 3.5), ("away", 4.))]

    def baseline(self, observations=None, forecasts=None):
        return c.aligned_market_baseline([self.record], self.observations if observations is None else observations,
                                         [self.frozen] if forecasts is None else forecasts)

    def test_complete_timestamped_prospective_quote_can_be_a_descriptive_baseline(self):
        self.assertEqual(self.baseline()["n"], 1)
        self.assertFalse(self.baseline()["verified_value"])
        self.assertAlmostEqual(self.baseline()["paired_frozen_model_scores"]["log_loss"], -__import__("math").log(.6), places=5)
        self.assertAlmostEqual(self.baseline()["recomputed_research_poisson_scores"]["log_loss"], -__import__("math").log(.5), places=5)

    def test_forecast_probability_and_pipeline_provenance_are_required(self):
        invalid = {**self.frozen, "probabilities": {"home": .8, "draw": .8, "away": .8}}
        self.assertEqual(self.baseline(forecasts=[invalid])["n"], 0)
        self.assertEqual(self.baseline([{**r, "model_pipeline_version": "legacy_unversioned"} for r in self.observations])["n"], 0)
        # Another pipeline's journal entry is separate evidence, not a duplicate of this pipeline.
        other = {**self.frozen, "pipeline_version": "legacy_unversioned"}
        self.assertEqual(self.baseline(forecasts=[self.frozen, other])["n"], 1)
        self.assertEqual(self.baseline(forecasts=[self.frozen, {**other, "actual_outcome": "away"}])["n"], 0)

    def test_incompatible_line_or_spliced_provider_snapshot_is_rejected(self):
        self.assertEqual(self.baseline([{**r, "line": .5} for r in self.observations])["n"], 0)
        for field, value in (("provider_event_id", "different"), ("provider_region", "different"),
                             ("quote_timestamp", "2025-08-01T10:01:00Z"),
                             ("model_generated_at", "2025-08-01T09:54:00Z")):
            with self.subTest(field=field):
                spliced = [dict(r) for r in self.observations]
                spliced[0][field] = value
                self.assertEqual(self.baseline(spliced)["n"], 0)

    def test_current_unverified_rules_and_legacy_missing_provenance_are_unavailable(self):
        unverified = [{**r, "settlement_rules_status": "unverified"} for r in self.observations]
        self.assertEqual(self.baseline(unverified)["status"], "unavailable")
        legacy = [{k: v for k, v in r.items() if k not in ("quote_timestamp", "commence_time")} for r in self.observations]
        self.assertEqual(self.baseline(legacy)["n"], 0)

    def test_after_kickoff_or_ambiguous_snapshots_and_settlements_are_rejected(self):
        late = [{**r, "observed_at": "2025-08-01T20:00:00Z", "quote_timestamp": "2025-08-01T19:00:00Z"} for r in self.observations]
        self.assertEqual(self.baseline(late)["n"], 0)
        self.assertEqual(self.baseline(self.observations+[self.observations[0]])["n"], 0)
        self.assertEqual(self.baseline(forecasts=[self.frozen, dict(self.frozen)])["n"], 0)
        self.assertEqual(self.baseline(forecasts=[{**self.frozen, "settled_at": "2025-08-01T17:00:00Z"}])["n"], 0)
        self.assertEqual(self.baseline(forecasts=[{**self.frozen, "created_at": "2025-08-01T12:00:00Z"}])["n"], 0)


if __name__ == "__main__":
    unittest.main()
