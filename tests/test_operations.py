"""Regressions for stale histories, ambiguous evidence and production orchestration."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runner
import odds_scanner
from scripts import run_pipeline, validate_outputs, verify_live_site

NOW=datetime(2026,11,6,18,tzinfo=timezone.utc)


def history(last="2026-11-04"):
    end=datetime.fromisoformat(last).date()
    return [{"league":"Premier League","date":(end-timedelta(days=i)).isoformat(),
             "home":"Arsenal","away":"Chelsea","gh":2,"ga":1} for i in range(100)]


class HistoryHealthTests(unittest.TestCase):
    def availability(self,rows,report=None):
        return runner.market_availability(rows,"Premier League","goals",NOW,
            report if report is not None else [{"league":"Premier League","kind":"results","ok":True}])

    def test_new_execution_does_not_make_old_history_recent(self):
        rows=history("2026-05-24")
        fixture={"league":"Premier League","date":"2026-11-07","home":"Arsenal","away":"Chelsea"}
        prediction=runner.pred(rows,fixture,"goals")
        self.assertIsNotNone(prediction)
        self.assertFalse(runner.comparison_allowed(prediction,NOW))
        health=self.availability(rows)
        self.assertEqual(health["status"],"history_too_old")
        self.assertFalse(health["comparison_allowed"])
        self.assertGreater(health["history_age_days"],150)

    def test_failed_or_unknown_current_feed_blocks_even_recent_history(self):
        for report in ([],[{"league":"Premier League","kind":"results","ok":False}]):
            state=self.availability(history(),report)
            self.assertEqual(state["status"],"current_results_source_unavailable")
            self.assertFalse(state["comparison_allowed"])

    def test_healthy_current_feed_is_allowed_but_not_validated(self):
        state=self.availability(history())
        self.assertTrue(state["comparison_allowed"])
        self.assertEqual(state["history_age_days"],2)
        self.assertIn("not_statistically_validated",state["policy"])

    def test_summer_old_data_is_explicitly_waiting_for_recent_results(self):
        state=runner.market_availability(history("2026-05-24"),"Premier League","goals",
            datetime(2026,7,4,tzinfo=timezone.utc),[{"league":"Premier League","kind":"results","ok":True}])
        self.assertFalse(state["comparison_allowed"])
        self.assertIn("sezoane",state["message"])

    def test_freshness_guard_does_not_change_retrospective_arithmetic(self):
        rows=history("2026-05-24")
        target={"league":"Premier League","date":"2026-05-25","home":"Arsenal","away":"Chelsea"}
        before=runner.pred(rows,target,"goals")
        self.availability(rows)
        self.assertEqual(before,runner.pred(rows,target,"goals"))

    def test_quotes_refuse_old_or_explicitly_blocked_history(self):
        from test_odds_safety import fixture,event,NOW as QUOTE_NOW
        for state in ("old","missing","blocked"):
            f=fixture()
            p=f["markets"]["goals"]
            if state=="old":p["explanation"]["last_observation_date"]="2026-05-24"
            elif state=="missing":p["explanation"].pop("last_observation_date")
            else:p["availability"]={"comparison_allowed":False}
            self.assertEqual(odds_scanner.analyze_fixture(event(),f,QUOTE_NOW)[0],[])


class JournalAmbiguityTests(unittest.TestCase):
    def test_conflicting_alias_forecasts_abort_without_modifying_journal(self):
        first={"league":"Premier League","date":"2026-11-07","home":"Arsenal","away":"Chelsea","market":"h2h",
               "created_at":"2026-11-05T12:00:00Z","settled":False,
               "probabilities":{"home":.8,"draw":.1,"away":.1},"pipeline_version":runner.PIPELINE_VERSION}
        second={**first,"home":"Arsenal FC","probabilities":{"home":.2,"draw":.4,"away":.4}}
        with tempfile.TemporaryDirectory() as folder, patch.object(runner,"OUT",Path(folder)):
            path=Path(folder)/"forecast_log.json"
            for records in ([first,second],[second,first],[first,first]):
                raw=json.dumps(records)
                path.write_text(raw)
                with self.assertRaisesRegex(RuntimeError,"duplicate canonical"):
                    runner.prospective([],[],NOW.isoformat())
                self.assertEqual(path.read_text(),raw)
                with self.assertRaisesRegex(ValueError,"[Dd]uplicate"):
                    validate_outputs.validate_log(records)

    def test_blocked_prediction_does_not_enter_prospective_journal(self):
        from test_data_integrity import prediction_fixture
        f=prediction_fixture()
        f["markets"]["goals"]["availability"]={"comparison_allowed":False}
        with tempfile.TemporaryDirectory() as folder,patch.object(runner,"OUT",Path(folder)):
            _,count=runner.prospective([],[f],NOW.isoformat())
            self.assertEqual(count,0)


class PipelineTests(unittest.TestCase):
    def test_only_one_workflow_can_publish_repository_outputs(self):
        workflows=Path(__file__).resolve().parents[1]/".github"/"workflows"
        writers=[]
        for path in workflows.glob("*.yml"):
            if "contents: write" in path.read_text():writers.append(path.name)
        self.assertEqual(writers,["valueradar.yml"])
        for name in ("model_lab.yml","elo.yml"):
            text=(workflows/name).read_text()
            self.assertNotIn("valueradar-production-writer",text)
            self.assertNotIn("publish_generated.py",text)

    def test_single_import_feeds_all_reports_and_reuses_the_comparison(self):
        data=(history(),[],[{"league":"Premier League","kind":"results","ok":True,
                            "source_url":"https://example.invalid/test-only","content_sha256":"test-only"}])
        comparison={"generated_at":NOW.isoformat(),"protocol":{}}
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            out=Path(folder)
            for name in ("latest","odds_observations","forecast_log","odds_diagnostics"):
                (out/(name+".json")).write_text("[]" if name in ("odds_observations","forecast_log") else "{}")
            stack.enter_context(patch.object(runner,"OUT",out))
            load=stack.enter_context(patch.object(runner,"load_all",return_value=data))
            baseline=stack.enter_context(patch.object(runner,"run",return_value=0))
            scanner=stack.enter_context(patch.object(odds_scanner,"fetch_scan"))
            stack.enter_context(patch.object(odds_scanner,"close_watchlist"))
            stack.enter_context(patch.object(run_pipeline.performance,"run"))
            cal=stack.enter_context(patch.object(run_pipeline.calibration,"compare_1x2",return_value=comparison))
            lab=stack.enter_context(patch.object(run_pipeline.model_lab,"experiment",return_value={}))
            elo=stack.enter_context(patch.object(run_pipeline.elo_challenger,"evaluate",return_value={}))
            stack.enter_context(patch.object(run_pipeline.elo_challenger,"market_diagnostic",return_value={}))
            stack.enter_context(patch.object(run_pipeline.subprocess,"run",return_value=SimpleNamespace(stdout="revision")))
            self.assertEqual(run_pipeline.execute(research=True,run_at=NOW),0)
            load.assert_called_once_with(NOW)
            baseline.assert_called_once_with(imported=data,run_at=NOW)
            self.assertIs(cal.call_args.args[0],data[0])
            self.assertIs(lab.call_args.args[0],data[0])
            self.assertIs(elo.call_args.kwargs["comparison"],comparison)
            scanner.assert_not_called()
            self.assertTrue(json.loads((out/"latest.json").read_text())["pipeline_execution"]["single_import"])

    def test_import_failure_stops_before_quotes_research_and_publication(self):
        with patch.object(runner,"run",return_value=2),patch.object(odds_scanner,"fetch_scan") as scanner,patch.object(run_pipeline.calibration,"compare_1x2") as research:
            self.assertEqual(run_pipeline.execute(research=True,scan_odds=True,imported=([],[],[]),run_at=NOW),2)
            scanner.assert_not_called()
            research.assert_not_called()


class AssetVerificationTests(unittest.TestCase):
    def test_new_json_with_old_javascript_is_not_a_successful_release(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b"old asset"
        with tempfile.TemporaryDirectory() as folder:
            docs=Path(folder)
            for name in ("index.html","common.js","dashboard.js","odds_ui.js","model_lab_ui.js","elo_ui.js"):
                (docs/name).write_bytes(b"expected asset")
            with patch("urllib.request.urlopen",return_value=Response()):
                with self.assertRaisesRegex(RuntimeError,"assets do not match"):
                    verify_live_site.verify_assets("https://example.invalid/",docs,attempts=1)


if __name__=="__main__":unittest.main()
