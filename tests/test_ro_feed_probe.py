"""Documented PropLine schema, synthetic tests only; no authenticated API calls."""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime,timedelta,timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from urllib.error import URLError

import ro_feed_probe as probe
import runner
from test_odds_safety import fixture,event

NOW=datetime(2026,11,6,17,tzinfo=timezone.utc)


def response():
    e=event()
    e.update(live=False,is_outright=False)
    template=e["bookmakers"][0]
    template["markets"][0]["last_update"]=(NOW-timedelta(seconds=20)).isoformat()
    for row,price in zip(template["markets"][0]["outcomes"],(-110,300,275)):
        row["price"]=price
        row["last_seen_at"]=(NOW-timedelta(seconds=10)).isoformat()
    e["bookmakers"]=[{**deepcopy(template),"key":book} for book in probe.BOOKS]
    return e


class ProbeTests(unittest.TestCase):
    def test_daily_monitor_is_five_serial_free_requests_and_only_aggregate_data(self):
        from scripts.validate_outputs import validate_ro_monitor
        with tempfile.TemporaryDirectory() as folder,patch.dict("os.environ",{"PROPLINE_API_KEY":"test-only"}):
            out=Path(folder)
            (out/"latest.json").write_text(json.dumps({"generated_at":NOW.isoformat(),"fixtures":[fixture()]}))
            clock=MagicMock();clock.now.return_value=NOW
            with patch.object(runner,"OUT",out),patch.object(probe,"datetime",clock),\
                 patch.object(probe,"fetch",return_value=([response()],{"X-Daily-Remaining":"999"},None)) as network,redirect_stdout(io.StringIO()):
                report=probe.monitor()
            self.assertEqual(network.call_count,5)
            self.assertEqual(report["authenticated_requests"],5)
            self.assertEqual(len(report["leagues"]),5)
            self.assertEqual(report,json.loads((out/"ro_feed_status.json").read_text()))
            self.assertTrue(all("max_age=120" in call.args[0] for call in network.call_args_list))
            validate_ro_monitor(report)
            text=json.dumps(report)
            for field in ('"price"','"outcomes"','"unmatched_fixture_samples"','"unsupported_selection_samples"','test-only'):
                self.assertNotIn(field,text)

    def test_monitor_without_key_makes_no_network_requests(self):
        from scripts.validate_outputs import validate_ro_monitor
        with tempfile.TemporaryDirectory() as folder,patch.dict("os.environ",{"PROPLINE_API_KEY":""}),\
             patch.object(probe,"fetch") as network,redirect_stdout(io.StringIO()):
            report=probe.monitor(Path(folder)/"monitor.json")
        network.assert_not_called()
        self.assertEqual(report["authenticated_requests"],0)
        self.assertTrue(all(row["status"]=="needs_api_key" for row in report["leagues"]))
        validate_ro_monitor(report)

    def test_monitor_internal_failure_isolated_without_reusing_previous_league_or_leaking_error(self):
        from scripts.validate_outputs import validate_ro_monitor
        calls=[]
        def run(**kwargs):
            calls.append(kwargs["league"])
            if len(calls)==2:raise ValueError("never-log-secret-or-response")
            kwargs["output"].write_text(json.dumps({"status":"provider_error","error":"http_503","authenticated_requests":1}))
            return 2
        with tempfile.TemporaryDirectory() as folder,patch.object(probe,"run",side_effect=run):
            report=probe.monitor(Path(folder)/"monitor.json")
        self.assertEqual(len(calls),5)
        self.assertEqual(report["leagues"][1]["status"],"diagnostic_error")
        self.assertEqual(report["leagues"][1]["error"],"ValueError")
        self.assertEqual(report["leagues"][2]["status"],"provider_error")
        self.assertIsNone(report["authenticated_requests"])
        self.assertNotIn("never-log",json.dumps(report))
        validate_ro_monitor(report)

    def test_public_monitor_contract_rejects_value_flags_prices_and_inconsistent_counts(self):
        from scripts.validate_outputs import validate_ro_monitor
        report=json.loads((Path(__file__).resolve().parents[1]/"docs/ro_feed_status.json").read_text())
        validate_ro_monitor(report)
        for field in ("verified_value","operator_prices_independently_verified","raw_odds_saved"):
            bad=deepcopy(report);bad[field]=True
            with self.assertRaises(ValueError):validate_ro_monitor(bad)
        for field in ("price","outcomes","unsupported_selection_samples"):
            bad=deepcopy(report);bad["leagues"][0]["quality"][field]=[]
            with self.assertRaises(ValueError):validate_ro_monitor(bad)
        bad=deepcopy(report);bad["leagues"][0]["quality"]["book_diagnostics"]["netbet_ro"]["matched_current_model_markets"]=100000
        with self.assertRaises(ValueError):validate_ro_monitor(bad)

    def test_inspecting_older_delivery_never_relaxes_accepted_quote_age(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict("os.environ",{"PROPLINE_API_KEY":"test-only"}):
            root=Path(folder)
            (root/"latest.json").write_text(json.dumps({"generated_at":NOW.isoformat(),"fixtures":[fixture()]}))
            payload=response()
            for book in payload["bookmakers"]:book["markets"][0]["last_update"]=(NOW-timedelta(minutes=10)).isoformat()
            clock=MagicMock();clock.now.return_value=NOW
            with patch.object(runner,"OUT",root),patch.object(probe,"datetime",clock),patch.object(probe,"fetch",return_value=([payload],{},None)) as network:
                output=root/"report.json"
                self.assertEqual(probe.run(authenticated=True,output=output,inspect_stale=True),2)
            self.assertIn("max_age=3600",network.call_args.args[0])
            report=json.loads(output.read_text())
            self.assertEqual(report["max_quote_age_seconds"],120)
            self.assertEqual(report["requested_max_delivery_age_seconds"],3600)
            self.assertEqual(report["quality"]["complete_recent_markets"],{})
            self.assertEqual(report["quality"]["rejection_counts"]["stale_market_timestamp"],2)
    def test_unknown_selection_examples_are_bounded_names_without_prices(self):
        data=[]
        for i in range(5):
            e=response();e["id"]=str(i)
            e["commence_time"]=(NOW+timedelta(days=i+1)).isoformat()
            for book in e["bookmakers"]:book["markets"][0]["outcomes"][0]["name"]="UNSUPPORTED_TEST_TEAM"
            data.append(e)
        result=probe.assess(data,[],"Premier League",NOW)
        self.assertEqual(len(result["unsupported_selection_samples"]),3)
        self.assertTrue(all(set(x)=={"bookmaker","home","away","selection_name"} for x in result["unsupported_selection_samples"]))
    def test_american_conversion_is_explicit_and_never_guesses_decimal(self):
        self.assertAlmostEqual(probe.american_decimal(-200),1.5)
        self.assertAlmostEqual(probe.american_decimal(250),3.5)
        for value in (None,True,1.95,0,-1,99,100.5,float("nan"),float("inf"),"200"):
            with self.assertRaises(ValueError):probe.american_decimal(value)

    def test_both_explicit_ro_books_can_be_assessed_without_saving_quotes(self):
        summary=probe.assess([response()],[fixture()],"Premier League",NOW)
        self.assertEqual(summary["matched_current_model_markets"],dict.fromkeys(probe.BOOKS,1))
        self.assertFalse(summary["raw_odds_saved"])
        self.assertFalse(summary["verified_value"])
        self.assertNotIn("odds",summary)

    def test_wrong_region_and_generic_book_labels_are_not_substitutes(self):
        e=response();e["bookmakers"][0]["key"]="superbet";e["bookmakers"][1]["key"]="netbet"
        self.assertEqual(probe.assess([e],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_live_started_or_outright_event_is_rejected(self):
        for changed in ({"live":True},{"is_outright":True},{"commence_time":NOW.isoformat()}):
            self.assertEqual(probe.assess([{**response(),**changed}],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_half_markets_suspensions_and_stale_deliveries_are_rejected(self):
        for changes in ({"period":"h1"},{"suspended_at":NOW.isoformat()},{"last_update":(NOW-timedelta(minutes=3)).isoformat()}):
            e=response()
            for book in e["bookmakers"]:book["markets"][0].update(changes)
            self.assertEqual(probe.assess([e],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_missing_selection_delivery_and_incomplete_market_are_rejected(self):
        for count in (2,3):
            e=response()
            for book in e["bookmakers"]:
                book["markets"][0]["outcomes"]=book["markets"][0]["outcomes"][:count]
                book["markets"][0]["outcomes"][0].pop("last_seen_at")
            self.assertEqual(probe.assess([e],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_event_identity_does_not_fuzzy_match_or_ignore_kickoff(self):
        for change in ({"home_team":"Arsenall"},{"commence_time":"2026-11-07T16:00:00Z"}):
            result=probe.assess([{**response(),**change}],[fixture()],"Premier League",NOW)
            self.assertEqual(result["matched_current_model_markets"],{})

    def test_stale_model_is_not_counted_as_matched_even_with_valid_prices(self):
        f=fixture();f["markets"]["goals"]["availability"]={"comparison_allowed":False}
        result=probe.assess([response()],[f],"Premier League",NOW)
        self.assertTrue(result["complete_recent_markets"])
        self.assertEqual(result["matched_current_model_markets"],{})

    def test_duplicate_provider_identity_is_quarantined_in_full(self):
        e=response()
        self.assertEqual(probe.assess([e,deepcopy(e)],[fixture()],"Premier League",NOW)["complete_recent_markets"],{})

    def test_new_ids_and_alias_spelling_do_not_create_independent_matches(self):
        first=response();second=deepcopy(first)
        second.update(id="another-id",home_team="Arsenal",commence_time="2026-11-07T16:00:00+01:00")
        for events in ([first,second],[second,first]):
            report=probe.assess(events,[fixture()],"Premier League",NOW)
            self.assertEqual(report["complete_recent_markets"],{})
            self.assertEqual(report["matched_current_model_markets"],{})
            self.assertEqual(report["rejection_counts"]["duplicate_canonical_event"],2)
            self.assertEqual(report["books_received"],dict.fromkeys(probe.BOOKS,2))
            for book in probe.BOOKS:
                self.assertEqual(report["book_diagnostics"][book]["status"],"received_but_rejected")
                self.assertEqual(report["book_diagnostics"][book]["rejection_counts"]["duplicate_canonical_event"],2)

    def test_multiple_provider_events_within_kickoff_tolerance_do_not_double_count(self):
        first=response();second=deepcopy(first)
        second.update(id="second-id",commence_time="2026-11-07T15:00:30Z")
        report=probe.assess([first,second],[fixture()],"Premier League",NOW)
        self.assertEqual(report["complete_recent_markets"],{})
        self.assertEqual(report["rejection_counts"]["duplicate_canonical_event"],2)

    def test_matched_model_requires_complete_valid_1x2(self):
        for distribution in (None,{"home":.5,"away":.5},{"home":.9,"draw":.2,"away":.2},
                             {"home":float("nan"),"draw":.5,"away":.5}):
            f=fixture();f["markets"]["goals"]["h2h"]=distribution
            report=probe.assess([response()],[f],"Premier League",NOW)
            self.assertEqual(report["complete_recent_markets"],dict.fromkeys(probe.BOOKS,1))
            self.assertEqual(report["matched_current_model_markets"],{})
            for book in probe.BOOKS:
                diagnostic=report["book_diagnostics"][book]
                self.assertEqual(diagnostic["status"],"complete_markets_without_model_match")
                self.assertEqual(diagnostic["rejection_counts"],{"invalid_or_missing_model_h2h":1})

    def test_outcome_specific_alternate_line_is_rejected(self):
        e=response()
        for book in e["bookmakers"]:book["markets"][0]["outcomes"][0]["line_type"]="alternate"
        report=probe.assess([e],[fixture()],"Premier League",NOW)
        self.assertEqual(report["complete_recent_markets"],{})
        self.assertEqual(report["rejection_counts"],{"unsupported_selection_line":2})

    def test_outcome_name_must_be_string_and_establish_exact_identity(self):
        for name,reason in ((["Arsenal FC"],"invalid_selection_name"),
                            ({"name":"Arsenal FC"},"invalid_selection_name"),
                            (None,"invalid_selection_name"),("Arsenall","unsupported_selection_identity")):
            e=response()
            for book in e["bookmakers"]:book["markets"][0]["outcomes"][0]["name"]=name
            report=probe.assess([e],[fixture()],"Premier League",NOW)
            self.assertEqual(report["complete_recent_markets"],{})
            self.assertEqual(report["rejection_counts"],{reason:2})

    def test_absent_book_is_distinct_from_received_invalid_market(self):
        e=response();e["bookmakers"]=[e["bookmakers"][1]]
        e["bookmakers"][0]["markets"][0]["outcomes"][0].pop("last_seen_at")
        report=probe.assess([e],[fixture()],"Premier League",NOW)
        self.assertEqual(report["books_received"],{"superbet_ro":0,"netbet_ro":1})
        self.assertEqual(report["book_diagnostics"]["superbet_ro"]["status"],"absent")
        self.assertEqual(report["book_diagnostics"]["superbet_ro"]["rejection_counts"],{})
        self.assertEqual(report["book_diagnostics"]["netbet_ro"]["status"],"received_but_rejected")
        self.assertEqual(report["book_diagnostics"]["netbet_ro"]["rejection_counts"],{"missing_selection_timestamp":1})
        self.assertIn("this filtered response",report["book_status_scope"])

    def test_selection_time_and_price_failures_have_distinct_reasons(self):
        cases=({"last_seen_at":None},"missing_selection_timestamp"),({"last_seen_at":"invalid"},"invalid_selection_timestamp"),\
          ({"last_seen_at":(NOW-timedelta(minutes=3)).isoformat()},"stale_selection_timestamp"),\
          ({"last_seen_at":(NOW+timedelta(seconds=1)).isoformat()},"future_selection_timestamp"),\
          ({"price":1.95},"invalid_american_price")
        for changes,reason in cases:
            e=response()
            for book in e["bookmakers"]:book["markets"][0]["outcomes"][0].update(changes)
            report=probe.assess([e],[fixture()],"Premier League",NOW)
            self.assertEqual(report["complete_recent_markets"],{})
            self.assertEqual(report["rejection_counts"],{reason:2})
            self.assertTrue(all(row["rejection_counts"]=={reason:1} for row in report["book_diagnostics"].values()))

    def test_bad_event_is_still_counted_as_received_book_with_reason(self):
        e=response();e["live"]=True
        report=probe.assess([e],[fixture()],"Premier League",NOW)
        self.assertEqual(report["books_received"],dict.fromkeys(probe.BOOKS,1))
        self.assertTrue(all(row["rejection_counts"]=={"not_explicitly_pre_match_football":1}
                            for row in report["book_diagnostics"].values()))

    def test_unmatched_samples_are_bounded_identity_only_and_do_not_fuzzy_match(self):
        events=[]
        for i in range(5):
            e=response();e.update(id=f"unmatched-{i}",commence_time=f"2026-11-{8+i:02d}T15:00:00Z")
            events.append(e)
        report=probe.assess(events,[fixture()],"Premier League",NOW)
        self.assertEqual(report["complete_recent_markets"],dict.fromkeys(probe.BOOKS,5))
        self.assertEqual(report["matched_current_model_markets"],{})
        self.assertEqual(len(report["unmatched_fixture_samples"]),3)
        for sample in report["unmatched_fixture_samples"]:
            self.assertEqual(set(sample),{"provider_event_id","home","away","commence_time","candidate_kickoffs_utc"})
            self.assertEqual(sample["candidate_kickoffs_utc"],["2026-11-07T15:00:00+00:00"])
        encoded=json.dumps(report,allow_nan=False)
        self.assertNotIn('"price"',encoded)
        self.assertNotIn('"outcomes"',encoded)
        self.assertNotIn('"odds"',encoded)

    def test_malformed_provider_shapes_are_not_valid_prices(self):
        for data in (None,{},{"events":[]}):
            with self.assertRaises(ValueError):probe.assess(data,[],"Premier League",NOW)
        for e in (None,{},{"id":[]},response()|{"bookmakers":[{"key":[]}]}):
            self.assertEqual(probe.assess([e],[],"Premier League",NOW)["complete_recent_markets"],{})

    def test_public_health_is_never_quote_validation(self):
        result=probe.summarize_health({"as_of":NOW.isoformat(),"bookmakers":[{"key":"superbet_ro","is_stale":False}]})
        self.assertTrue(result["books"][0]["present"])
        self.assertFalse(result["books"][1]["present"])
        self.assertIn("individual",result["books"][0]["warning"])

    def test_missing_key_makes_no_request_and_writes_actionable_status(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict("os.environ",{"PROPLINE_API_KEY":""}),patch.object(probe,"fetch") as network:
            output=Path(folder)/"report.json"
            self.assertEqual(probe.run(authenticated=True,output=output),2)
            network.assert_not_called()
            report=json.loads(output.read_text())
            self.assertEqual(report["status"],"needs_api_key")
            self.assertFalse(report["verified_value"])

    def test_run_records_response_time_analysis_and_only_logs_whitelisted_summary(self):
        fake_secret="SYNTHETIC_TEST_KEY_NOT_A_REAL_CREDENTIAL"
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"report.json"
            latest={"generated_at":NOW.isoformat(),"pipeline_version":"synthetic_test_pipeline","fixtures":[fixture()]}
            (Path(folder)/"latest.json").write_text(json.dumps(latest))
            stdout=io.StringIO()
            with patch.dict("os.environ",{"PROPLINE_API_KEY":fake_secret}),patch.object(runner,"OUT",Path(folder)),\
                 patch.object(probe,"fetch",return_value=([response()],{"X-Daily-Remaining":"999"},None)) as network,\
                 patch.object(probe,"datetime") as clock,redirect_stdout(stdout):
                clock.now.side_effect=[NOW,NOW,NOW+timedelta(seconds=2)]
                self.assertEqual(probe.run(authenticated=True,league="Premier League",output=output),0)
            report=json.loads(output.read_text())
            self.assertEqual(report["league"],"Premier League")
            self.assertEqual(report["analysis_generated_at"],NOW.isoformat())
            self.assertEqual(report["model_pipeline_version"],"synthetic_test_pipeline")
            self.assertEqual(report["received_at"],(NOW+timedelta(seconds=2)).isoformat())
            self.assertEqual(report["max_quote_age_seconds"],120)
            self.assertEqual(report["authenticated_requests"],1)
            network.assert_called_once()
            self.assertIn("max_age=120",network.call_args.args[0])
            self.assertFalse(report["verified_value"])
            self.assertFalse(report["operator_prices_independently_verified"])
            self.assertFalse(report["raw_odds_saved"])
            self.assertNotIn(fake_secret,output.read_text()+stdout.getvalue())
            lines=stdout.getvalue().splitlines()
            self.assertEqual(len(lines),1)
            self.assertTrue(lines[0].startswith("RO_FEED_DIAGNOSTIC "))
            summary=json.loads(lines[0].removeprefix("RO_FEED_DIAGNOSTIC "))
            self.assertEqual(set(summary),{"league","status","received_at","analysis_generated_at",
              "max_quote_age_seconds","requested_max_delivery_age_seconds","quality","quota"})
            self.assertEqual(summary["received_at"],report["received_at"])
            self.assertEqual(summary["max_quote_age_seconds"],120)
            self.assertEqual(summary["quota"],{"x-daily-remaining":999})

    def test_network_error_does_not_expose_key_and_redirect_cannot_forward_it(self):
        secret="TEST_ONLY_DO_NOT_LEAK"
        opener=MagicMock()
        opener.open.side_effect=URLError("provider echoed "+secret)
        with patch("urllib.request.build_opener",return_value=opener):
            payload,headers,error=probe.fetch("/freshness",secret)
        self.assertNotIn(secret,str((payload,headers,error)))
        request=opener.open.call_args.args[0]
        self.assertNotIn(secret,request.full_url)
        self.assertEqual(request.get_header("X-api-key"),secret)
        with self.assertRaises(ValueError):probe.NoRedirect().redirect_request()


if __name__=="__main__":unittest.main()
