"""Regressions for real import boundaries and write-once prospective evidence."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import runner

NOW = datetime(2026, 11, 6, 18, tzinfo=timezone.utc)


def result(day="2026-10-01", **changes):
    return {"league": "Premier League", "date": day, "home": "Arsenal FC",
            "away": "Chelsea", "gh": 2., "ga": 1., **changes}


def prediction_fixture(**changes):
    return {"league": "Premier League", "date": "2026-11-07", "time": "16:00",
            "home": "Arsenal", "away": "Chelsea",
            "markets": {"goals": {"line": 2.5, "over": .6,
                                  "h2h": {"home": .5, "draw": .25, "away": .25}}},
            **changes}


class IdentitiesAndDates(unittest.TestCase):
    def test_cross_season_explicit_identities(self):
        pairs = [("Brighton & Hove Albion FC", "Brighton"), ("Newcastle United FC", "Newcastle"),
                 ("AC Milan", "Milan"), ("FC Internazionale Milano", "Internazionale"),
                 ("Bologna FC 1909", "Bologna"), ("AS Roma", "Roma"),
                 ("SSC Napoli", "Napoli"), ("Parma Calcio 1913", "Parma"),
                 ("RC Celta de Vigo", "Celta"), ("Real Sociedad de Fútbol", "Real Sociedad"),
                 ("LOSC Lille", "Lille OSC"), ("Havre Athletic Club", "Le Havre AC"),
                 ("Racing Club de Lens", "RC Lens"), ("Stade Rennais FC 1901", "Stade Rennais")]
        for first, second in pairs:
            with self.subTest(first=first):
                self.assertEqual(runner.norm(first), runner.norm(second))
        self.assertNotEqual(runner.norm("Paris FC"), runner.norm("Paris Saint-Germain"))
        self.assertNotEqual(runner.norm("Manchester United"), runner.norm("Manchester City"))
        self.assertNotEqual(runner.norm("Arsenal"), runner.norm("Arsenals"))

    def test_counts_reject_bool_fraction_nonfinite_and_negative(self):
        for bad in (True, False, -1, 1.2, "NaN", float("inf"), None, ""):
            with self.subTest(value=bad):
                self.assertIsNone(runner.number(bad))
        self.assertEqual(runner.number("0"), 0)
        self.assertEqual(runner.number("2.0"), 2)

    def test_fixed_offset_is_not_summer_dst(self):
        fixture = {"date": "2026-07-02", "time": "20:00"}
        self.assertEqual(runner.fixture_kickoff(fixture).utcoffset(), timedelta(hours=1))
        self.assertEqual(runner.local_kickoff(fixture), "22:00")

    def test_local_date_rollover_is_explicit(self):
        f = runner.local_fixture({"date": "2026-07-02", "time": "23:30"})
        self.assertEqual(f["date_ro"], "2026-07-03")
        self.assertEqual(f["time_ro"], "01:30")
        self.assertEqual(f["kickoff_utc"], "2026-07-02T22:30:00+00:00")

    def test_unknown_or_invalid_same_day_time_is_not_upcoming(self):
        for value in ("", "TBD", "25:00", None):
            self.assertFalse(runner.future_match({"date": "2026-11-06", "time": value}, NOW))
        self.assertFalse(runner.future_match({"date": "2026-11-06", "time": "19:00"}, NOW))
        self.assertTrue(runner.future_match({"date": "2026-11-06", "time": "19:01"}, NOW))

    def test_timestamp_never_invents_timezone(self):
        self.assertIsNone(runner.timestamp("2026-11-06T18:00:00"))
        self.assertEqual(runner.timestamp("2026-11-06T18:00:00Z"), NOW)

    def test_source_seasons_roll_over_in_july(self):
        jan = [url for _, _, url in runner.tasks(datetime(2027, 1, 1, tzinfo=timezone.utc))]
        july = [url for _, _, url in runner.tasks(datetime(2027, 7, 1, tzinfo=timezone.utc))]
        self.assertEqual(len(jan), 20)
        self.assertIn("results_2627.csv", jan[0])
        self.assertIn("results_2728.csv", july[0])
        self.assertTrue(any("2024-25" in u for u in jan))
        self.assertTrue(any("2026-27" in u for u in july))


class ImportIntegrity(unittest.TestCase):
    def test_duplicate_identical_result_merges_optional_data(self):
        rows, report = runner.clean_history([result(), result(home="Arsenal", yh=2)], NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["yh"], 2)
        self.assertEqual(report["duplicates_merged"], 1)

    def test_conflicting_duplicates_are_quarantined_not_first_wins(self):
        for records in ([result(), result(gh=3)], [result(gh=3), result()]):
            rows, report = runner.clean_history(records, NOW)
            self.assertEqual(rows, [])
            self.assertEqual(report["conflicting_events_quarantined"], 1)

    def test_conflicting_optional_statistics_quarantine_entire_match(self):
        rows, _ = runner.clean_history([result(yh=2), result(yh=4)], NOW)
        self.assertEqual(rows, [])

    def test_future_or_not_completed_results_are_not_training_data(self):
        records = [result("2026-11-07"), result("2026-11-06", time="19:00"),
                   result("2026-11-06", time="17:30"), result("2026-11-06", time="15:00")]
        rows, report = runner.clean_history(records, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["time"], "15:00")
        self.assertEqual(report["rejected"]["future_result"], 1)
        self.assertEqual(report["rejected"]["result_not_provably_completed"], 2)

    def test_invalid_identity_and_counts_are_rejected(self):
        records = [result(home="", away="A"), result(home="Chelsea"),
                   result(gh=-1), result(ga=.5), result(fh=float("nan")), result(gh=True), result(home=None)]
        rows, _ = runner.clean_history(records, NOW)
        self.assertEqual(rows, [])

    def test_import_validates_schema_season_and_source_hash(self):
        jobs = [("Premier League", "results", f"{runner.OM}/ENG_1_premier-league/results_2627.csv"),
                ("Premier League", "fixtures", f"{runner.OM}/ENG_1_premier-league/fixtures_2627.csv")]
        contents = {
            jobs[0][2]: "date,time,home,away,ft_home,ft_away\n"
                        "2026-10-01,16:00,Arsenal,Chelsea,2,1\n"
                        "2025-10-01,16:00,Arsenal,Chelsea,2,1\n"
                        "2026-11-07,16:00,Arsenal,Chelsea,2,1\n",
            jobs[1][2]: "date,time,home,away\n2026-11-07,16:00,Arsenal,Chelsea\n"}
        with patch.object(runner, "tasks", return_value=jobs), patch.object(runner, "get_text", side_effect=contents.__getitem__):
            history, fixtures, reports = runner.load_all(NOW)
        self.assertEqual(len(history), 1)
        self.assertEqual(len(fixtures), 1)
        source = next(r for r in reports if r["kind"] == "results")
        self.assertEqual(source["rejected"]["wrong_season"], 1)
        self.assertEqual(len(source["content_sha256"]), 64)
        integrity = next(r for r in reports if r["kind"] == "integrity")
        self.assertEqual(integrity["rejected"]["future_result"], 1)

    def test_bad_source_schema_and_network_failure_fail_closed(self):
        jobs = [("Premier League", "results", f"{runner.OM}/x/results_2627.csv")]
        for behavior in (lambda _: "date,home\n2026-10-01,Arsenal\n", lambda _: (_ for _ in ()).throw(TimeoutError())):
            with patch.object(runner, "tasks", return_value=jobs), patch.object(runner, "get_text", side_effect=behavior):
                history, fixtures, report = runner.load_all(NOW)
            self.assertEqual(history, [])
            self.assertEqual(fixtures, [])
            self.assertFalse(next(r for r in report if r["kind"] == "results")["ok"])

    def test_download_completion_order_cannot_change_results(self):
        jobs = [("Premier League", "historical", f"{runner.OF}/2025-26/en.1.json"),
                ("Premier League", "results", f"{runner.OM}/x/results_2627.csv")]
        contents = {jobs[0][2]: json.dumps({"matches": [{"date": "2025-10-01", "team1": "Arsenal FC", "team2": "Chelsea", "score": {"ft": [2, 1]}}]}),
                    jobs[1][2]: "date,home,away,ft_home,ft_away\n2026-10-01,Arsenal,Chelsea,2,1\n"}
        with patch.object(runner, "tasks", return_value=jobs), patch.object(runner, "get_text", side_effect=contents.__getitem__):
            first = runner.load_all(NOW)
            with patch.object(runner, "as_completed", side_effect=lambda futures: reversed(list(futures))):
                second = runner.load_all(NOW)
        self.assertEqual(first, second)


class ProbabilityContracts(unittest.TestCase):
    def test_invalid_poisson_intensities_rejected(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.h2h_distribution(value, 1)
        self.assertEqual(runner.h2h_distribution(0, 0), {"home": 0, "draw": 1, "away": 0})

    def test_1x2_is_normalized_and_nonnegative(self):
        for h, a in ((.05, .05), (1.2, 2.1), (20., 10.), (0, 4), (4, 0)):
            p = runner.h2h_distribution(h, a)
            self.assertAlmostEqual(sum(p.values()), 1, places=12)
            self.assertTrue(all(0 <= value <= 1 for value in p.values()))

    def test_invalid_tails_and_model_parameters_rejected(self):
        for values in ((float("nan"), 2.5, 1), (float("inf"), 2.5, 1), (-1, 2.5, 1), (2, -1, 1), (2, 2.5, .5)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                runner.over_tail(*values)
        f = prediction_fixture()
        for params in ({"half_life_days": 0}, {"half_life_days": float("nan")}, {"prior_weight": -1}):
            with self.assertRaises(ValueError):
                runner.pred([], f, "goals", **params)

    def test_large_poisson_mean_does_not_underflow_to_one(self):
        # Reference independently obtained from Poisson survival (scipy), not production recurrence.
        self.assertAlmostEqual(runner.over_tail(1000, 1000), .491590632831494, places=10)

    def test_model_excludes_same_day_and_future_features(self):
        hist = [result((datetime(2026, 1, 1) + timedelta(days=i)).date().isoformat(), source_ids=["verified_test_source:2025-26"]) for i in range(120)]
        f = prediction_fixture(date="2026-07-01")
        base = runner.pred(hist, f, "goals")
        changed = runner.pred(hist + [result("2026-07-01", gh=100), result("2026-07-02", gh=100)], f, "goals")
        self.assertEqual(base, changed)
        e = base["explanation"]
        self.assertEqual(e["source_families"], ["verified_test_source"])
        self.assertLess(e["last_observation_date"], f["date"])
        self.assertEqual(e["uncertainty"]["status"], "not_quantified")
        self.assertIsNone(e["uncertainty"]["probability_interval"])
        self.assertAlmostEqual(e["predicted_total_mean"], e["predicted_home_mean"] + e["predicted_away_mean"], places=4)

    def test_rejection_has_actual_sample_and_reason(self):
        rejected = runner.market_rejection([], prediction_fixture(), "goals")
        self.assertEqual(rejected["code"], "insufficient_league_history")
        self.assertEqual(rejected["n_league"], 0)
        self.assertEqual(rejected["minimum_league"], 70)


class ProspectiveEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        self.patch = patch.object(runner, "OUT", self.output)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def read(self):
        return json.loads((self.output / "forecast_log.json").read_text())

    def test_first_forecast_remains_identical_when_model_changes(self):
        f = prediction_fixture()
        runner.prospective([], [f], NOW.isoformat())
        original = copy.deepcopy(self.read())
        f["markets"]["goals"]["over"] = .9
        f["markets"]["goals"]["h2h"]["home"] = .8
        runner.prospective([], [f], (NOW + timedelta(minutes=1)).isoformat())
        self.assertEqual(self.read(), original)
        self.assertEqual(original[0]["pipeline_version"], runner.PIPELINE_VERSION)

    def test_corrected_pipeline_appends_forecast_without_changing_legacy(self):
        legacy = {"league": "Premier League", "date": "2026-11-07", "home": "Arsenal", "away": "Chelsea",
                  "market": "h2h", "probabilities": {"home": .8, "draw": .1, "away": .1},
                  "created_at": "2026-11-05T15:00:00Z", "settled": False}
        (self.output / "forecast_log.json").write_text(json.dumps([legacy]))
        runner.prospective([], [prediction_fixture()], NOW.isoformat())
        records = self.read()
        self.assertEqual(records[0], legacy)
        corrected = [r for r in records if r["market"] == "h2h" and r.get("pipeline_version") == runner.PIPELINE_VERSION]
        self.assertEqual(len(corrected), 1)
        self.assertEqual(corrected[0]["probabilities"]["home"], .5)
        runner.prospective([], [prediction_fixture()], (NOW + timedelta(minutes=1)).isoformat())
        self.assertEqual(self.read(), records)

    def test_corrupt_journal_is_never_silently_overwritten(self):
        path = self.output / "forecast_log.json"
        bad_probability = {"league":"Premier League","date":"2026-11-07","home":"Arsenal","away":"Chelsea","market":"h2h","created_at":"2026-11-05T12:00:00Z","settled":False,"probabilities":{"home":-1,"draw":1,"away":1}}
        for raw in ("{broken", "{}", '[{"league":"Premier League"}]', json.dumps([bad_probability])):
            path.write_text(raw)
            with self.assertRaises(RuntimeError):
                runner.prospective([], [prediction_fixture()], NOW.isoformat())
            self.assertEqual(path.read_text(), raw)

    def test_no_new_forecast_after_kickoff_or_without_known_time(self):
        runner.prospective([], [prediction_fixture(date="2026-11-06", time="19:00"), prediction_fixture(time="")], NOW.isoformat())
        self.assertEqual(self.read(), [])

    def test_future_outcomes_do_not_settle_a_forecast(self):
        runner.prospective([result("2026-11-07")], [prediction_fixture()], NOW.isoformat())
        self.assertTrue(all(r["settled"] is False for r in self.read()))

    def test_settlement_keeps_original_inputs_and_separates_versions(self):
        runner.prospective([], [prediction_fixture()], NOW.isoformat())
        original = copy.deepcopy(self.read())
        scores, _ = runner.prospective([result("2026-11-07")], [], "2026-11-08T12:00:00Z")
        for old, new in zip(original, self.read()):
            for field, value in old.items():
                if field != "settled":
                    self.assertEqual(new[field], value)
            self.assertTrue(new["settled"])
        self.assertEqual(scores["h2h"]["n"], 1)
        self.assertEqual(scores["h2h"]["by_pipeline_version"][runner.PIPELINE_VERSION]["n"], 1)

    def test_post_kickoff_legacy_forecast_cannot_enter_scores(self):
        row = {"league": "Premier League", "date": "2026-11-06", "home": "Arsenal", "away": "Chelsea",
               "market": "h2h", "probabilities": {"home": .5, "draw": .25, "away": .25},
               "created_at": "2026-11-06T16:00:00Z", "kickoff_utc": "2026-11-06T15:00:00Z", "settled": False}
        (self.output / "forecast_log.json").write_text(json.dumps([row]))
        scores, _ = runner.prospective([result("2026-11-06", time="16:00")], [], "2026-11-07T12:00:00Z")
        self.assertEqual(scores["h2h"]["n"], 0)
        self.assertFalse(self.read()[0]["settled"])
        self.assertEqual(self.read()[0]["evaluation_exclusion"], "creation_not_provably_before_kickoff")

    def test_json_serialization_failure_preserves_existing_file(self):
        path = self.output / "proof.json"
        path.write_text('{"original":true}')
        with self.assertRaises(ValueError):
            runner.write_json_atomic(path, {"probability": float("nan")})
        self.assertEqual(path.read_text(), '{"original":true}')


if __name__ == "__main__":
    unittest.main()
