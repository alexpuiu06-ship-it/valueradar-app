"""Synthetic score API evidence; these fixtures never enter the public results."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import oddspapi_probe as api
import runner
import scores_probe as probe
from test_oddspapi_probe import account, SECRET

NOW = datetime(2026, 11, 7, 1, tzinfo=timezone.utc)
START = datetime(2026, 11, 6, 19, 30, tzinfo=timezone.utc)


def forecast(league="Premier League"):
    return {"league": league, "date": "2026-11-06", "home": "Arsenal", "away": "Chelsea",
            "kickoff_utc": START.isoformat(), "market": "h2h", "settled": False,
            "created_at": (START-timedelta(days=1)).isoformat(),
            "pipeline_version": runner.PIPELINE_VERSION,
            "probabilities": {"home": .5, "draw": .25, "away": .25}}


def fixture(league="Premier League"):
    return {"fixtureId": "synthetic-score-"+str(api.TOURNAMENTS[league][0]),
            "sportId": 10, "tournamentId": api.TOURNAMENTS[league][0],
            "participant1Id": 1, "participant2Id": 2,
            "participant1Name": "Arsenal FC", "participant2Name": "Chelsea",
            "statusId": 2, "statusName": "Finished", "hasOdds": False,
            "startTime": START.isoformat(), "trueStartTime": START.isoformat(),
            "trueEndTime": (START+timedelta(minutes=112)).isoformat()}


def score(league="Premier League"):
    return {"fixtureId": fixture(league)["fixtureId"], "scores": {"periods": {
        "fulltime": {"participant1Score": 2, "participant2Score": 1,
                     "updatedAt": (START+timedelta(minutes=110)).isoformat()},
        # Extra time deliberately differs from the 90 minute result.
        "result": {"participant1Score": 4, "participant2Score": 3}}}}


class ScoresProbeTests(unittest.TestCase):
    def test_only_current_prospective_pending_matches_with_known_past_kickoff(self):
        valid = forecast()
        invalid = []
        for changes in ({"pipeline_version": "legacy"}, {"settled": True, "actual_outcome": "home"},
                        {"created_at": START.isoformat()}, {"kickoff_utc": None},
                        {"kickoff_utc": (NOW-timedelta(hours=1)).isoformat()},
                        {"kickoff_utc": (NOW-timedelta(days=8)).isoformat()},
                        {"probabilities": {"home": 1, "draw": 1, "away": 1}}):
            invalid.append({**valid, **changes})
        self.assertEqual(probe.pending_forecasts([valid, *invalid], runner.PIPELINE_VERSION, NOW), [valid])
        self.assertEqual(probe.pending_forecasts([valid], runner.PIPELINE_VERSION, NOW, "La Liga"), [])
        with self.assertRaises(api.ProbeError):
            probe.pending_forecasts([valid, valid], runner.PIPELINE_VERSION, NOW)
        with self.assertRaises(api.ProbeError):
            probe.pending_forecasts({}, runner.PIPELINE_VERSION, NOW)

    def test_exact_identity_orientation_kickoff_and_duplicate_quarantine(self):
        first = fixture()
        key = runner.key(forecast())
        self.assertEqual(probe.match_fixtures([first], [forecast()]), {key: first})
        for changed in ({"fixtureId": "other"}, {"startTime": (START+timedelta(seconds=20)).isoformat()}):
            self.assertEqual(probe.match_fixtures([first, {**first, **changed}], [forecast()]), {})
        self.assertEqual(probe.match_fixtures([first, first], [forecast()]), {})
        for changes in ({"participant1Name": "Other club"}, {"participant1Name": "Chelsea", "participant2Name": "Arsenal"},
                        {"tournamentId": 8}, {"sportId": 11}, {"participant1Id": True},
                        {"participant1Id": 2}, {"startTime": (START+timedelta(seconds=61)).isoformat()},
                        {"startTime": START.replace(tzinfo=None).isoformat()}):
            self.assertEqual(probe.match_fixtures([{**first, **changes}], [forecast()]), {})

    def test_explicit_finished_status_and_completion_time_are_required(self):
        self.assertIsNotNone(probe.terminal_fixture(fixture(), "Premier League", NOW)["end"])
        self.assertIsNone(probe.terminal_fixture({**fixture(), "trueEndTime": None}, "Premier League", NOW)["end"])
        for changes in ({"statusName": None}, {"statusName": "In-Play"}, {"statusName": "Cancelled"},
                        {"statusId": 1}, {"statusId": True}, {"trueStartTime": "unparsed"},
                        {"trueEndTime": "unparsed"}, {"trueEndTime": (NOW+timedelta(seconds=1)).isoformat()},
                        {"trueEndTime": (START+timedelta(minutes=89)).isoformat()},
                        {"trueStartTime": (NOW-timedelta(minutes=10)).isoformat()}):
            with self.subTest(changes=changes), self.assertRaises(api.ProbeError):
                probe.terminal_fixture({**fixture(), **changes}, "Premier League", NOW)

    def test_only_named_fulltime_period_is_used_and_extra_time_is_never_substituted(self):
        self.assertEqual(probe.fulltime_score(score(), fixture()["fixtureId"], NOW)[0], (2, 1))
        for payload in ({"fixtureId": fixture()["fixtureId"], "scores": {"0": {"participant1Score": 2, "participant2Score": 1}}},
                        {"fixtureId": fixture()["fixtureId"], "scores": {"periods": {"result": {"participant1Score": 4, "participant2Score": 3}}}},
                        {**score(), "fixtureId": "other"}):
            with self.assertRaises(api.ProbeError):probe.fulltime_score(payload, fixture()["fixtureId"], NOW)
        for bad in (True, False, None, -1, 31, 1.2, "2", float("nan"), float("inf")):
            payload = score();payload["scores"]["periods"]["fulltime"]["participant1Score"] = bad
            with self.subTest(bad=bad), self.assertRaises(api.ProbeError):
                probe.fulltime_score(payload, fixture()["fixtureId"], NOW)
        payload = score();payload["scores"]["periods"]["fulltime"]["updatedAt"] = (NOW+timedelta(seconds=1)).isoformat()
        with self.assertRaises(api.ProbeError):probe.fulltime_score(payload, fixture()["fixtureId"], NOW)

    def run_probe(self, folder, *, remaining=232, limit=250, change=None, error=None, candidates=None):
        root = Path(folder)
        (root/"latest.json").write_text(json.dumps({"generated_at": NOW.isoformat(), "pipeline_version": runner.PIPELINE_VERSION}))
        candidates = candidates if candidates is not None else [forecast(league) for league in runner.LEAGUES]
        (root/"forecast_log.json").write_text(json.dumps(candidates))
        def fetch(path, params, key):
            self.assertEqual(key, SECRET)
            if error:return None, error
            if path == "/account":
                payload = account();payload["subscriptions"][0].update(request_limit=limit, request_count=limit-remaining)
            elif path == "/tournaments":
                payload = [{"tournamentId": ident, "categorySlug": cat, "tournamentSlug": slugs[0]}
                           for ident, cat, slugs in api.TOURNAMENTS.values()]
            elif path == "/fixtures":
                self.assertNotIn("hasOdds", params)
                payload = [fixture(league) for league in runner.LEAGUES]
            else:
                league = next(name for name in runner.LEAGUES if fixture(name)["fixtureId"] == params["fixtureId"])
                payload = score(league) if path == "/scores" else fixture(league)
            if change:payload = change(path, params, payload)
            return payload, None
        clock = MagicMock();clock.now.return_value = NOW
        stream = io.StringIO()
        with patch.object(runner, "OUT", root), patch.object(probe, "datetime", clock), \
             patch.dict("os.environ", {"ODDSPAPI_API_KEY": SECRET}), patch.object(api, "fetch", side_effect=fetch) as network, \
             patch.object(probe.time, "sleep"), redirect_stdout(stream):
            code = probe.run(True, output=root/"report.json")
        return code, json.loads((root/"report.json").read_text()), stream.getvalue(), network

    def test_all_five_candidates_use_at_most_twelve_metered_calls_and_redacted_account(self):
        with tempfile.TemporaryDirectory() as folder:code, report, logged, network = self.run_probe(folder)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "diagnostic_scores_for_review")
        self.assertEqual(report["metered_requests_attempted"], 12)
        self.assertEqual(report["unmetered_requests_attempted"], 2)
        self.assertEqual(network.call_count, 14)
        self.assertEqual(report["observed_matches"], 5)
        self.assertEqual(report["reviewable_matches"], 5)
        self.assertFalse(report["production_settlement_enabled"])
        self.assertFalse(report["verified_value"])
        for forbidden in (SECRET, "private-test", '"api_key"', '"scores"', '"subscriptions"', '"participant1Name"'):
            self.assertNotIn(forbidden, logged);self.assertNotIn(forbidden, json.dumps(report))
        self.assertEqual({row["fulltime_home"] for row in report["observations"]}, {2})

    def test_partial_coverage_never_reports_complete_validation(self):
        def partial(path, params, payload):
            if path == "/fixtures":return payload[:1]
            return payload
        with tempfile.TemporaryDirectory() as folder:code, report, _, _ = self.run_probe(folder, change=partial)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "incomplete_scores_validation")
        self.assertEqual(report["reviewable_matches"], 1)
        self.assertEqual(report["rejections"], {"missing_or_ambiguous_fixture_match": 4})

    def test_missing_final_time_is_diagnostic_only_and_recheck_changes_are_quarantined(self):
        def missing_end(path, params, payload):
            if path == "/fixtures":return [{**row, "trueEndTime": None} for row in payload]
            if path == "/fixture":return {**payload, "trueEndTime": None}
            return payload
        with tempfile.TemporaryDirectory() as folder:code, report, _, _ = self.run_probe(folder, change=missing_end)
        self.assertEqual(code, 2);self.assertEqual(report["reviewable_matches"], 0)
        self.assertEqual(report["observed_matches"], 5)
        def changed(path, params, payload):
            if path == "/fixture":return {**payload, "participant1Id": 500}
            return payload
        with tempfile.TemporaryDirectory() as folder:code, report, _, _ = self.run_probe(folder, change=changed)
        self.assertEqual(code, 2);self.assertEqual(report["observations"], [])
        self.assertEqual(report["rejections"], {"fixture_changed_during_score_request": 5})

    def test_free_account_and_quota_guards_stop_before_metered_requests(self):
        for remaining, limit, reason in ((21, 250, "quota_reserve_guard"), (232, 500, "free_soccer_account_not_confirmed")):
            with tempfile.TemporaryDirectory() as folder:code, report, _, network = self.run_probe(folder, remaining=remaining, limit=limit)
            self.assertEqual(code, 2);self.assertEqual(report["reason"], reason)
            self.assertEqual(report["metered_requests_attempted"], 0);self.assertEqual(network.call_count, 1)

    def test_no_pending_matches_no_key_and_unauthenticated_modes_do_not_call_network(self):
        with tempfile.TemporaryDirectory() as folder:code, report, _, network = self.run_probe(folder, candidates=[])
        self.assertEqual(code, 0);self.assertEqual(report["status"], "no_pending_completed_matches");network.assert_not_called()
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"ODDSPAPI_API_KEY": ""}), \
             patch.object(api, "fetch") as network, redirect_stdout(io.StringIO()):
            output = Path(folder)/"report.json"
            self.assertEqual(probe.run(output=output), 0)
            self.assertEqual(probe.run(authenticated=True, output=output), 2)
        network.assert_not_called()

    def test_unknown_error_and_exception_messages_cannot_leak_query_credentials(self):
        with tempfile.TemporaryDirectory() as folder:code, report, logged, network = self.run_probe(folder, error="https://test.invalid/?apiKey="+SECRET)
        self.assertEqual(code, 2);self.assertEqual(report["reason"], "provider_error");self.assertEqual(network.call_count, 1)
        self.assertNotIn(SECRET, logged)
        def fail(path, params, payload):raise RuntimeError(SECRET)
        with tempfile.TemporaryDirectory() as folder:code, report, logged, _ = self.run_probe(folder, change=fail)
        self.assertEqual(report["reason"], "RuntimeError");self.assertNotIn(SECRET, logged)


if __name__ == "__main__":unittest.main()
