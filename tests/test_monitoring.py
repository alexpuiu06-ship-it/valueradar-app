"""Aggregate monitoring contracts, persistence and real-world time boundaries."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monitoring
import runner
from test_data_integrity import prediction_fixture,result

NOW=datetime(2026,11,7,tzinfo=timezone.utc)
ROOT=Path(__file__).resolve().parents[1]


def status(at=NOW):
    # Test-time timestamps over a real aggregate shape; no invented public odds.
    report=json.loads((ROOT/"docs/ro_feed_status.json").read_text())
    report["generated_at"]=at.isoformat()
    for row in report["leagues"]:row["received_at"]=(at-timedelta(seconds=1)).isoformat()
    return report


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name);self.source=self.out/"status.json";self.history=self.out/"history.json"

    def store(self,report):self.source.write_text(json.dumps(report))

    def test_repeated_refresh_never_duplicates_or_refreshes_an_observation(self):
        self.store(status())
        first=monitoring.update_ro_history(self.source,self.history,NOW)
        later=monitoring.update_ro_history(self.source,self.history,NOW+timedelta(hours=4))
        self.assertEqual(first["records"],later["records"])
        self.assertEqual(len(later["records"]),1)
        self.assertEqual(later["records"][0]["observed_at"],NOW.isoformat())
        self.assertNotEqual(first["generated_at"],later["generated_at"])
        text=json.dumps(later)
        for field in ('"price"','"outcomes"','"quota"','"unmatched_fixture_samples"','"unsupported_selection_samples"'):
            self.assertNotIn(field,text)

    def test_history_preserves_failures_as_unknown_instead_of_zero_valid_quotes(self):
        first=status();self.store(first);monitoring.update_ro_history(self.source,self.history,NOW)
        error=status(NOW+timedelta(days=1))
        for row in error["leagues"]:row.update(status="provider_error",quality=None,error="http_503",received_at=None)
        self.store(error)
        report=monitoring.update_ro_history(self.source,self.history,NOW+timedelta(days=1))
        self.assertEqual(len(report["records"]),2)
        row=report["records"][-1]["leagues"][0]
        self.assertEqual(row["error"],"http_503")
        self.assertIsNone(row["books"]["superbet_ro"]["matched"])
        self.assertIsNone(row["books"]["netbet_ro"]["received"])

    def test_observed_snapshot_cannot_be_rewritten(self):
        self.store(status());monitoring.update_ro_history(self.source,self.history,NOW)
        original=self.history.read_bytes();changed=status()
        changed["leagues"][0]["status"]="provider_error"
        self.store(changed)
        with self.assertRaisesRegex(ValueError,"rewritten"):monitoring.update_ro_history(self.source,self.history,NOW)
        self.assertEqual(self.history.read_bytes(),original)

    def test_missing_days_are_not_filled_and_retention_does_not_reinsert_expired_data(self):
        self.store(status());monitoring.update_ro_history(self.source,self.history,NOW)
        self.store(status(NOW+timedelta(days=3)))
        report=monitoring.update_ro_history(self.source,self.history,NOW+timedelta(days=3))
        self.assertEqual([r["day_ro"] for r in report["records"]],["2026-11-07","2026-11-10"])
        expired=monitoring.update_ro_history(self.source,self.history,NOW+timedelta(days=94))
        self.assertEqual(expired["records"],[])

    def test_calendar_day_uses_romania_and_acceptance_threshold_stays_strict(self):
        at=datetime(2026,11,6,23,30,tzinfo=timezone.utc)
        report=status(at)
        for row in report["leagues"]:row["requested_max_delivery_age_seconds"]=3600
        record=monitoring.compact_status(report,at)
        self.assertEqual(record["day_ro"],"2026-11-07")
        self.assertEqual(record["max_quote_age_seconds"],120)
        self.assertEqual(record["leagues"][0]["delivery_filter_seconds"],3600)

    def test_invalid_input_or_corrupt_history_preserves_the_last_good_file(self):
        self.store(status());monitoring.update_ro_history(self.source,self.history,NOW)
        before=self.history.read_bytes()
        for field,value in (("verified_value",True),("raw_odds_saved",True),("max_quote_age_seconds",3600),
                            ("generated_at",(NOW+timedelta(hours=1)).isoformat())):
            bad=status();bad[field]=value;self.store(bad)
            with self.subTest(field=field),self.assertRaises(ValueError):monitoring.update_ro_history(self.source,self.history,NOW)
            self.assertEqual(self.history.read_bytes(),before)
        self.store(status());self.history.write_text("{broken")
        with self.assertRaises(ValueError):monitoring.update_ro_history(self.source,self.history,NOW)
        self.assertEqual(self.history.read_text(),"{broken")

    def test_no_source_does_not_fabricate_a_successful_probe(self):
        report=monitoring.update_ro_history(self.source,self.history,NOW)
        self.assertEqual(report["records"],[])
        monitoring.validate_history(report,NOW)

    def test_history_rejects_raw_nested_fields_oversized_lists_and_false_counts(self):
        self.store(status());good=monitoring.update_ro_history(self.source,self.history,NOW)
        for change in ("raw","oversize","counts","duplicate","bad_date"):
            bad=deepcopy(good)
            if change=="raw":bad["records"][0]["leagues"][0]["books"]["superbet_ro"]["price"]=2
            if change=="oversize":bad["records"]*=513
            if change=="counts":bad["records"][0]["leagues"][0]["books"]["superbet_ro"]["matched"]=999999
            if change=="duplicate":bad["records"]*=2
            if change=="bad_date":bad["records"][0]["day_ro"]="2026-11-06"
            with self.subTest(change=change),self.assertRaises(ValueError):monitoring.validate_history(bad,NOW)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.at=datetime(2026,11,3,17,5,tzinfo=timezone.utc)
        with patch.object(runner,"OUT",self.out):
            runner.prospective([],[prediction_fixture(date="2026-11-03")],"2026-11-02T12:00:00Z")
            scores,_=runner.prospective([result("2026-11-03",time="16:00")],[],self.at.isoformat())
        self.latest={"generated_at":self.at.isoformat(),"pipeline_version":runner.PIPELINE_VERSION,"prospective":scores,
          "source_success":1,"source_total":1,"source_report":[{"league":"Premier League","kind":"results","ok":True}]}
        (self.out/"latest.json").write_text(json.dumps(self.latest))
        self.operations=monitoring.refresh(output=self.out,at=self.at)
        self.audit=monitoring.read(self.out/"settlement_report.json")
        self.history=monitoring.read(self.out/"ro_feed_history.json")
        self.log=monitoring.read(self.out/"forecast_log.json")

    def validate(self,latest=None,operations=None):
        monitoring.validate_bundle(latest or self.latest,self.log,self.audit,self.history,operations or self.operations)

    def test_operational_bundle_is_coherent_and_has_no_fabricated_ro_samples(self):
        self.validate()
        self.assertEqual(self.operations["ro_history"],{"records":0,"days_observed":0,"last_observed_at":None})
        self.assertEqual(self.operations["settlement"]["counts"],{"settled_with_evidence":2})
        self.assertEqual(self.latest["prospective"]["h2h"]["n"],1)

    def test_forecast_scores_cannot_borrow_counts_or_drop_a_pipeline_group(self):
        for changed in ("count","version"):
            latest=deepcopy(self.latest)
            if changed=="count":latest["prospective"]["h2h"]["n"]+=1
            else:latest["prospective"]["h2h"]["by_pipeline_version"]={}
            with self.subTest(changed=changed),self.assertRaises(ValueError):self.validate(latest=latest)

    def test_a_report_from_another_analysis_cannot_be_published_as_current(self):
        ops=deepcopy(self.operations);ops["pipeline_version"]="other_pipeline"
        with self.assertRaises(ValueError):self.validate(operations=ops)
        ops=deepcopy(self.operations);ops["analysis_generated_at"]="2026-11-02T12:00:00Z"
        with self.assertRaises(ValueError):self.validate(operations=ops)

    def test_operations_contract_rejects_profit_flags_false_sources_and_unexpected_fields(self):
        for changed in ("value","roi","source","raw"):
            ops=deepcopy(self.operations)
            if changed=="value":ops["verified_value"]=True
            if changed=="roi":ops["hypothetical_roi"]=.5
            if changed=="source":ops["sources"]["successful"]=2
            if changed=="raw":ops["price"]=2
            with self.subTest(changed=changed),self.assertRaises(ValueError):monitoring.validate_operations(ops)

    def test_public_summary_cannot_contradict_the_settlement_audit(self):
        ops=deepcopy(self.operations);ops["ro_history"]["records"]=1
        with self.assertRaises(ValueError):self.validate(operations=ops)


if __name__=="__main__":unittest.main()
