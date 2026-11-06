"""Deterministic adversarial boundary checks. No live odds API requests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

import odds_scanner as odds
import performance
import runner

NOW = datetime(2026, 11, 6, 17, tzinfo=timezone.utc)


def fixture():
    return {"league": "Premier League", "date": "2026-11-07", "time": "16:00",
            "home": "Arsenal", "away": "Chelsea", "markets": {"goals": {
                "h2h": {"home": .5, "draw": .25, "away": .25}, "n_home": 20, "n_away": 20,
                "small_sample": False, "explanation": {"pipeline_version": runner.PIPELINE_VERSION}}}}


def event():
    return {"id": "event-1", "sport_key": "soccer_epl", "home_team": "Arsenal FC",
            "away_team": "Chelsea", "commence_time": "2026-11-07T15:00:00Z", "bookmakers": [{
                "key": "book-1", "title": "International book", "last_update": "2026-11-06T16:50:00Z",
                "markets": [{"key": "h2h", "outcomes": [{"name": "Arsenal FC", "price": 2.1537},
                            {"name": "Draw", "price": 3.4}, {"name": "Chelsea", "price": 3.5}]}]}]}


def observations(stamp=NOW, verified_rules=False):
    records = []
    for i in range(3):
        current = event()
        current["bookmakers"][0]["key"] = f"book-{i}"
        current["bookmakers"][0]["last_update"] = (stamp - timedelta(minutes=10)).isoformat()
        records.extend(odds.analyze_fixture(current, fixture(), stamp, (stamp - timedelta(minutes=20)).isoformat())[0])
    if verified_rules:
        for row in records:
            row.update(settlement_rules_status="verified", settlement_rule="90_minutes_plus_stoppage",
                       settlement_evidence="unit-test-only://explicit-settlement-rule")
    return records


class OddsIdentityTests(unittest.TestCase):
    def test_exact_known_alias_and_kickoff(self):
        f = fixture()
        self.assertIs(odds.match_event(event(), [f], NOW), f)

    def test_similar_spelling_does_not_establish_identity(self):
        current = event()
        current["home_team"] = "Arsenall"
        self.assertIsNone(odds.match_event(current, [fixture()], NOW))

    def test_nearby_but_different_kickoff_is_rejected(self):
        current = event()
        current["commence_time"] = "2026-11-07T16:00:00Z"
        self.assertIsNone(odds.match_event(current, [fixture()], NOW))

    def test_competition_and_orientation_match(self):
        current = event()
        current["sport_key"] = "soccer_spain_la_liga"
        self.assertIsNone(odds.match_event(current, [fixture()], NOW))
        current = event()
        current["home_team"], current["away_team"] = current["away_team"], current["home_team"]
        self.assertIsNone(odds.match_event(current, [fixture()], NOW))

    def test_ambiguous_fixture_fails_closed(self):
        self.assertIsNone(odds.match_event(event(), [fixture(), fixture()], NOW))

    def test_already_started_and_unknown_time_rejected(self):
        self.assertIsNone(odds.match_event(event(), [fixture()], NOW + timedelta(days=2)))
        current = fixture()
        current["time"] = ""
        self.assertIsNone(odds.match_event(event(), [current], NOW))

    def test_naive_datetime_not_assumed_utc(self):
        self.assertIsNone(odds.dt("2026-11-06T17:00:00"))
        self.assertIsNone(odds.dt("2026-11-06"))
        self.assertEqual(odds.dt("2026-11-06T18:00:00+01:00"), NOW)


class QuoteTests(unittest.TestCase):
    def test_accepted_quote_retains_exact_decimal_and_provenance(self):
        result, n, _ = odds.analyze_fixture(event(), fixture(), NOW, NOW.isoformat())
        self.assertEqual(n, 1)
        self.assertEqual(result[0]["odds"], 2.1537)
        self.assertEqual(result[0]["quote_timestamp"], "2026-11-06T16:50:00+00:00")
        self.assertEqual(result[0]["provider_region"], odds.REGION)
        self.assertEqual(result[0]["market_key"], "h2h")
        self.assertIsNone(result[0]["line"])
        self.assertTrue(all(row["value_blockers"] and row["ready_to_bet"] is False for row in result))

    def test_missing_stale_future_naive_source_timestamps_rejected(self):
        for stamp in (None, "2026-11-06T14:00:00Z", "2026-11-06T17:00:01Z", "2026-11-06T16:50:00"):
            with self.subTest(stamp=stamp):
                current = event()
                current["bookmakers"][0]["last_update"] = stamp
                self.assertIsNone(odds.parse_h2h(current["bookmakers"][0], current, NOW))

    def test_invalid_market_timestamp_cannot_fallback_to_book(self):
        current = event()
        current["bookmakers"][0]["markets"][0]["last_update"] = "invalid"
        self.assertIsNone(odds.parse_h2h(current["bookmakers"][0], current, NOW))

    def test_invalid_prices_extra_outcomes_and_lines_rejected(self):
        for price in (True, float("nan"), float("inf"), 0, -2, "2.15"):
            current = event()
            current["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = price
            self.assertIsNone(odds.parse_h2h(current["bookmakers"][0], current, NOW))
        for field in ("point",):
            current = event()
            current["bookmakers"][0]["markets"][0]["outcomes"][0][field] = -.5
            self.assertIsNone(odds.parse_h2h(current["bookmakers"][0], current, NOW))
        current = event()
        current["bookmakers"][0]["markets"][0]["outcomes"].append({"name": "Other", "price": 3})
        self.assertIsNone(odds.parse_h2h(current["bookmakers"][0], current, NOW))

    def test_duplicate_market_bookmaker_or_outcome_rejected(self):
        current = event()
        current["bookmakers"][0]["markets"].append(deepcopy(current["bookmakers"][0]["markets"][0]))
        self.assertIsNone(odds.parse_h2h(current["bookmakers"][0], current, NOW))
        current = event()
        current["bookmakers"].append(deepcopy(current["bookmakers"][0]))
        self.assertEqual(odds.analyze_fixture(current, fixture(), NOW)[0], [])
        current = event()
        current["bookmakers"][0]["markets"][0]["outcomes"][1]["name"] = "Arsenal"
        self.assertIsNone(odds.parse_h2h(current["bookmakers"][0], current, NOW))

    def test_invalid_probabilities_cannot_generate_comparisons(self):
        for probs in ({"home": .9, "draw": .3, "away": .2},
                      {"home": float("nan"), "draw": .3, "away": .2},
                      {"home": True, "draw": 0, "away": 0}, {"home": .5, "away": .5}):
            current = fixture()
            current["markets"]["goals"]["h2h"] = probs
            self.assertEqual(odds.analyze_fixture(event(), current, NOW)[0], [])

    def test_network_error_sanitizes_url_and_key(self):
        marker = "secret-test-do-not-log"
        with patch("urllib.request.urlopen", side_effect=URLError("https://api/?apiKey=" + marker)):
            result, headers, error = odds.get_json("https://api/?apiKey=" + marker)
        self.assertEqual(result, [])
        self.assertNotIn(marker, error)
        self.assertNotIn("apiKey", error)


class ConsensusTests(unittest.TestCase):
    def test_complete_same_scan_normalized_no_vig(self):
        result = odds.cross_book_consensus(observations())
        self.assertEqual(result["market_events_evaluated"], 1)
        self.assertEqual(result["items"][0]["books"], 3)
        self.assertAlmostEqual(sum(result["items"][0]["market_consensus_no_vig"].values()), 1, places=4)
        self.assertFalse(result["items"][0]["verified_value"])
        self.assertFalse(result["items"][0]["bookmaker_independence_verified"])

    def test_outcomes_from_different_scans_never_spliced(self):
        records = observations()
        for row in records:
            if row["outcome"] == "draw":
                row["observed_at"] = (NOW + timedelta(minutes=1)).isoformat()
        result = odds.cross_book_consensus(records)
        self.assertEqual(result["market_events_evaluated"], 0)

    def test_latest_incomplete_scan_does_not_backfill_older_quotes(self):
        records = observations()
        later = [deepcopy(row) for row in records if row["outcome"] == "home"]
        for row in later:
            row["observed_at"] = (NOW + timedelta(minutes=1)).isoformat()
        self.assertEqual(odds.cross_book_consensus(records + later)["items"], [])

    def test_conflicting_duplicate_and_metadata_rejected(self):
        records = observations()
        conflict = deepcopy(records[0])
        conflict["odds"] += .1
        self.assertEqual(odds.cross_book_consensus(records + [conflict])["items"], [])
        records = observations()
        records[0]["quote_timestamp"] = "2026-11-06T16:49:00Z"
        self.assertEqual(odds.cross_book_consensus(records)["items"], [])

    def test_invalid_probabilities_and_post_kickoff_snapshots_rejected(self):
        records = observations()
        for row in records:
            row["model_probability"] = .9
        self.assertEqual(odds.cross_book_consensus(records)["items"], [])
        records = observations()
        for row in records:
            row["commence_time"] = "2026-11-06T16:00:00Z"
        self.assertEqual(odds.cross_book_consensus(records)["items"], [])

    def test_cached_diagnostic_preserves_original_observation_date(self):
        result = odds.cross_book_consensus(observations())
        self.assertEqual(odds.dt(result["data_timestamp"]), NOW)
        self.assertEqual(odds.dt(result["items"][0]["observed_at"]), NOW)


class ScanGuardsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)
        self.patch_out = patch.object(odds, "OUT", self.out)
        self.patch_out.start()
        self.env = patch.dict(os.environ, {"ODDS_API_KEY": "test-key"})
        self.env.start()
        self.now_patch = patch.object(odds, "datetime")
        self.clock = self.now_patch.start()
        self.clock.now.return_value = NOW
        self.clock.fromisoformat.side_effect = datetime.fromisoformat
        self.write("odds_watchlist.json", {"status": "verified_ro_opportunities", "items": [{"ready_to_bet": True}]})
        self.write("latest.json", {"generated_at": NOW.isoformat(), "pipeline_version": runner.PIPELINE_VERSION, "fixtures": [fixture()]})
        self.write("odds_budget.json", {"month": "2026-11", "spent": 5, "calls": 5,
                                        "provider_reported_remaining": 495})

    def tearDown(self):
        self.now_patch.stop()
        self.env.stop()
        self.patch_out.stop()
        self.temp.cleanup()

    def write(self, name, value):
        (self.out / name).write_text(json.dumps(value), encoding="utf-8")

    def assert_closed(self):
        watch = json.loads((self.out / "odds_watchlist.json").read_text())
        self.assertEqual(watch["items"], [])
        self.assertFalse(watch["live_ro_supported"])
        return json.loads((self.out / "odds_status.json").read_text())

    def test_missing_key_clears_old_signals_without_request(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": ""}), patch.object(odds, "get_json") as request:
            odds.fetch_scan()
        request.assert_not_called()
        status = self.assert_closed()
        self.assertEqual(status["status"], "needs_api_key")
        self.assertIsNone(status["data_timestamp"])

    def test_stale_model_never_requests_quotes(self):
        self.write("latest.json", {"generated_at": (NOW - timedelta(days=1)).isoformat(), "fixtures": [fixture()]})
        with patch.object(odds, "get_json") as request:
            odds.fetch_scan()
        request.assert_not_called()
        self.assertEqual(self.assert_closed()["status"], "stale_model")

    def test_corrupt_missing_and_negative_budget_fail_closed(self):
        for content in ("{bad", "null", '{"month":"2026-11","spent":-1,"calls":0}'):
            (self.out / "odds_budget.json").write_text(content)
            with patch.object(odds, "get_json") as request:
                odds.fetch_scan()
            request.assert_not_called()
            self.assertEqual(self.assert_closed()["status"], "budget_invalid")
        (self.out / "odds_budget.json").unlink()
        with patch.object(odds, "get_json") as request:
            odds.fetch_scan()
        request.assert_not_called()

    def test_budget_and_reserve_stop_before_api(self):
        for spent, remaining in ((399, 495), (5, 70)):
            self.write("odds_budget.json", {"month": "2026-11", "spent": spent, "calls": 5,
                                            "provider_reported_remaining": remaining})
            with patch.object(odds, "get_json") as request:
                odds.fetch_scan()
            request.assert_not_called()
            self.assertEqual(self.assert_closed()["status"], "budget_guard")

    def test_no_usable_model_prevents_unnecessary_quote_request(self):
        current = fixture()
        current["markets"]["goals"]["h2h"] = None
        self.write("latest.json", {"generated_at": NOW.isoformat(), "fixtures": [current]})
        with patch.object(odds, "get_json") as request:
            odds.fetch_scan()
        request.assert_not_called()
        self.assertEqual(self.assert_closed()["status"], "missing_fixtures")

    def test_timeout_counts_conservative_credit_and_no_signals(self):
        with patch.object(odds, "get_json", return_value=([], {}, "Network/API error: TimeoutError")) as request:
            odds.fetch_scan()
        self.assertEqual(request.call_count, 1)
        budget = json.loads((self.out / "odds_budget.json").read_text())
        self.assertEqual(budget["spent"], 6)
        self.assertEqual(budget["calls"], 6)
        self.assertEqual(self.assert_closed()["status"], "api_error")

    def test_happy_path_is_still_observation_only(self):
        with patch.object(odds, "get_json", return_value=([event()], {"x-requests-last": "1", "x-requests-remaining": "494"}, None)):
            odds.fetch_scan()
        status = self.assert_closed()
        self.assertEqual(status["status"], "connected")
        self.assertEqual(status["evaluated_prices"], 3)
        self.assertEqual(status["data_timestamp"], "2026-11-06T16:50:00+00:00")
        self.assertEqual(status["watchlist_count"], 0)
        rows = json.loads((self.out / "odds_observations.json").read_text())
        self.assertTrue(all(row["model_generated_at"] == NOW.isoformat() for row in rows))


class EvidenceTests(unittest.TestCase):
    def test_forged_flags_never_enable_profit(self):
        records = observations()
        for row in records:
            row.update(verified_ro_offer=True, ready_to_bet=True, model_is_validated=True, estimated_ev=.2)
        outcome = {**fixture(), "market": "h2h", "settled": True, "actual_outcome": "home"}
        report = performance.evaluate(records, [outcome])
        self.assertEqual(report["initial_positive_ev_signals"], 0)
        self.assertEqual(report["signals_settled"], 0)
        self.assertIsNone(report["hypothetical_roi"])
        self.assertTrue(report["value_blockers"])

    def test_pre_match_market_baseline_uses_actual_same_event(self):
        outcome = {**fixture(), "market": "h2h", "settled": True, "actual_outcome": "home",
                   "created_at": "2026-11-06T16:00:00Z", "settled_at": "2026-11-07T18:00:00Z",
                   "pipeline_version": runner.PIPELINE_VERSION, "kickoff_utc": "2026-11-07T15:00:00Z",
                   "probabilities": {"home": .4, "draw": .3, "away": .3}}
        report = performance.evaluate(observations(verified_rules=True), [outcome])
        self.assertEqual(report["market_baseline"]["n"], 1)
        self.assertGreater(report["market_baseline"]["market_log_loss"], 0)
        self.assertIsNone(report["hypothetical_roi"])

    def test_late_forecast_or_missing_provenance_cannot_score_market_baseline(self):
        outcome = {**fixture(), "market": "h2h", "settled": True, "actual_outcome": "home",
                   "created_at": "2026-11-07T16:00:00Z", "settled_at": "2026-11-07T18:00:00Z",
                   "pipeline_version": runner.PIPELINE_VERSION, "kickoff_utc": "2026-11-07T15:00:00Z",
                   "probabilities": {"home": .4, "draw": .3, "away": .3}}
        self.assertEqual(performance.evaluate(observations(verified_rules=True), [outcome])["market_baseline"]["n"], 0)
        outcome["created_at"] = "2026-11-06T16:00:00Z"
        records = observations(verified_rules=True)
        for row in records:
            del row["quote_timestamp"]
        self.assertEqual(performance.evaluate(records, [outcome])["market_baseline"]["n"], 0)

    def test_pipeline_versions_do_not_conflict_and_use_frozen_probabilities(self):
        current = {**fixture(), "market": "h2h", "settled": True, "actual_outcome": "home",
                   "created_at": "2026-11-06T16:00:00Z", "settled_at": "2026-11-07T18:00:00Z",
                   "pipeline_version": runner.PIPELINE_VERSION, "kickoff_utc": "2026-11-07T15:00:00Z",
                   "probabilities": {"home": .4, "draw": .3, "away": .3}}
        legacy = {**current, "created_at": "2026-11-06T15:00:00Z",
                  "probabilities": {"home": .6, "draw": .2, "away": .2}}
        del legacy["pipeline_version"]
        result = performance.evaluate(observations(verified_rules=True), [legacy, current])
        self.assertEqual(result["market_baseline"]["n"], 1)
        self.assertAlmostEqual(result["market_baseline"]["model_log_loss"], -math.log(.4), places=5)
        self.assertEqual(performance.evaluate(observations(verified_rules=True), [legacy])["market_baseline"]["n"], 0)
        conflict = {**legacy, "actual_outcome": "away"}
        self.assertEqual(performance.evaluate(observations(verified_rules=True), [conflict, current])["market_baseline"]["n"], 0)

    def test_missing_rule_evidence_or_misaligned_kickoff_cannot_score(self):
        current = {**fixture(), "market": "h2h", "settled": True, "actual_outcome": "home",
                   "created_at": "2026-11-06T16:00:00Z", "settled_at": "2026-11-07T18:00:00Z",
                   "pipeline_version": runner.PIPELINE_VERSION, "kickoff_utc": "2026-11-07T15:00:00Z",
                   "probabilities": {"home": .4, "draw": .3, "away": .3}}
        self.assertEqual(performance.evaluate(observations(), [current])["market_baseline"]["n"], 0)
        current["kickoff_utc"] = "2026-11-07T16:00:00Z"
        self.assertEqual(performance.evaluate(observations(verified_rules=True), [current])["market_baseline"]["n"], 0)

    def test_earlier_legacy_scan_cannot_block_current_pipeline_or_pool_versions(self):
        current = {**fixture(), "market": "h2h", "settled": True, "actual_outcome": "home",
                   "created_at": "2026-11-06T16:00:00Z", "settled_at": "2026-11-07T18:00:00Z",
                   "pipeline_version": runner.PIPELINE_VERSION, "kickoff_utc": "2026-11-07T15:00:00Z",
                   "probabilities": {"home": .4, "draw": .3, "away": .3}}
        legacy = {**current, "probabilities": {"home": .6, "draw": .2, "away": .2}}
        del legacy["pipeline_version"]
        older_quotes = observations(NOW-timedelta(minutes=10), verified_rules=True)
        for row in older_quotes:
            row["model_pipeline_version"] = "legacy_unversioned"
        quotes = older_quotes+observations(verified_rules=True)
        result = performance.evaluate(quotes, [current])
        self.assertEqual(result["market_baseline"]["n"], 1)
        self.assertIn(runner.PIPELINE_VERSION, result["market_baseline"]["by_pipeline_version"])
        result = performance.evaluate(quotes, [current, legacy])
        self.assertEqual(result["market_baseline"]["n"], 2)
        self.assertIsNone(result["market_baseline"]["model_log_loss"])
        self.assertEqual(len(result["market_baseline"]["by_pipeline_version"]), 2)
        self.assertFalse(result["market_baseline"]["mixed_versions_pooled"])

    def test_malformed_observation_book_and_forecast_shapes_fail_closed(self):
        samples = [None, [], {}, 3, True, "bad", {"markets": None}, {"markets": [None, [], 3, True, "bad"]}]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertIsNone(odds.parse_h2h(sample, {}, NOW))
                self.assertEqual(odds.analyze_fixture({}, sample, NOW)[0], [])
                self.assertEqual(odds.cross_book_consensus([sample])["items"], [])
                self.assertEqual(performance.evaluate([sample], [sample])["signals_settled"], 0)
        malformed = {"market": "h2h", "settled": True, "actual_outcome": "home", "league": [], "date": "bad", "home": "A", "away": "B"}
        self.assertEqual(performance.evaluate([], [malformed])["signals_settled"], 0)


if __name__ == "__main__":
    unittest.main()
