"""Chronological settlement tests use synthetic matches, never published results."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner
import settlement
from scripts.validate_outputs import validate_log
from test_data_integrity import prediction_fixture,result

CREATED=datetime(2026,11,6,18,tzinfo=timezone.utc)
FINISHED=datetime(2026,11,7,17,5,tzinfo=timezone.utc)


def all_markets():
    f=prediction_fixture()
    for name,(_,_,line,_) in runner.MARKETS.items():
        if name!="goals":f["markets"][name]={"line":line,"over":.6}
    return f


def full_result(**changes):
    return result("2026-11-07",time="16:00",yh=2,ya=3,ch=5,ca=6,fh=12,fa=13,
                  source_ids=["synthetic-test-source"],**changes)


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.patch=patch.object(runner,"OUT",self.out);self.patch.start();self.addCleanup(self.patch.stop)

    def log(self):return json.loads((self.out/"forecast_log.json").read_text())
    def report(self):return json.loads((self.out/"settlement_report.json").read_text())
    def freeze(self):
        runner.prospective([],[all_markets()],CREATED.isoformat())
        return self.log()

    def test_complete_chronology_partial_statistics_then_late_statistics(self):
        frozen=self.freeze()
        self.assertEqual(len(frozen),5)
        runner.prospective([full_result()],[],"2026-11-07T16:30:00Z")
        self.assertEqual(self.log(),frozen)
        self.assertEqual(self.report()["counts"],{"in_progress":5})
        runner.prospective([result("2026-11-07",time="16:00")],[],FINISHED.isoformat())
        partial=self.log()
        self.assertEqual(sum(r["settled"] for r in partial),2)
        self.assertEqual(self.report()["counts"],{"settled_with_evidence":2,"awaiting_statistics":3})
        sources=[{"ok":True,"league":"Premier League","kind":"results","source_id":"synthetic-test-source","content_sha256":"a"*64,"fetched_at":FINISHED.isoformat()}]
        scores,_=runner.prospective([full_result()],[],(FINISHED+timedelta(hours=1)).isoformat(),sources)
        complete=self.log()
        validate_log(complete,frozen)
        for before,after in zip(partial,complete):
            if before["settled"]:self.assertEqual(before,after)
        for market in (*runner.MARKETS,"h2h"):self.assertEqual(scores[market]["n"],1)
        self.assertEqual(self.report()["counts"],{"settled_with_evidence":5})
        self.assertEqual(self.report()["ready_but_unsettled"],0)
        settlement.validate_report(self.report())
        self.assertEqual(complete[1]["settlement_evidence"]["source_snapshots"],sources and [{k:v for k,v in sources[0].items() if k!="ok"}])

    def test_kickoff_change_is_quarantined_without_settling_or_rewriting_forecast(self):
        frozen=self.freeze()
        changed=full_result();changed["time"]="12:00"
        scores,_=runner.prospective([changed],[],FINISHED.isoformat())
        self.assertEqual(self.log(),frozen)
        self.assertEqual(self.report()["counts"],{"blocked_kickoff_conflict":5})
        self.assertFalse(runner.prospective_eligible(frozen[0],changed))
        self.assertEqual(scores["h2h"]["n"],0)

    def test_conflicting_results_never_settle_and_missing_outcomes_are_not_zero(self):
        self.freeze()
        changed=full_result();changed["gh"]=0
        runner.prospective([full_result(),changed],[],FINISHED.isoformat())
        self.assertEqual(self.report()["result_conflicts_quarantined"],1)
        self.assertEqual(self.report()["counts"],{"awaiting_result":5})
        self.assertFalse(any(r["settled"] for r in self.log()))

    def test_result_revision_quarantines_scores_preserves_settled_evidence_and_benchmark(self):
        self.freeze()
        runner.prospective([full_result()],[],FINISHED.isoformat())
        original=deepcopy(self.log())
        corrected=full_result();corrected.update(gh=3,ga=0)
        at=FINISHED+timedelta(days=1)
        scores,_=runner.prospective([corrected],[],at.isoformat())
        self.assertEqual(self.log(),original)
        self.assertEqual(scores["h2h"]["n"],0)
        self.assertEqual(scores["goals"]["n"],0)
        report=self.report()
        self.assertEqual(report["counts"]["settled_result_conflict"],2)
        self.assertEqual(len(settlement.eligible_forecasts(original,report,at.isoformat())),3)
        self.assertFalse(any(r["market"]=="h2h" for r in settlement.eligible_forecasts(original,report,at.isoformat())))
        self.assertEqual(settlement.eligible_forecasts(original,report,CREATED.isoformat()),[])
        older=deepcopy(report);older["schema_version"]=1
        older["excluded_settled_ids"]=[settlement.forecast_id(row,legacy=True) for row in original if row["market"] in ("h2h","goals")]
        self.assertEqual(len(settlement.eligible_forecasts(original,older,at.isoformat())),3)

    def test_archived_valid_settlements_survive_a_later_missing_result_feed(self):
        self.freeze()
        runner.prospective([full_result()],[],FINISHED.isoformat())
        before=deepcopy(self.log())
        scores,_=runner.prospective([],[],(FINISHED+timedelta(days=1)).isoformat())
        self.assertEqual(self.log(),before)
        self.assertTrue(all(row["n"]==1 for row in scores.values()))
        self.assertEqual(self.report()["counts"],{"settled_with_evidence":5})

    def test_forged_or_missing_settlement_evidence_cannot_enter_scores(self):
        self.freeze();runner.prospective([full_result()],[],FINISHED.isoformat())
        original=deepcopy(self.log())
        for modification in ("missing_time","too_early","future","bad_hash","missing_proof"):
            log=deepcopy(original);row=next(r for r in log if r["market"]=="h2h")
            if modification=="missing_time":row.pop("settled_at")
            if modification=="too_early":row["settled_at"]="2026-11-07T15:01:00Z"
            if modification=="future":row["settled_at"]="2026-11-10T18:00:00Z"
            if modification=="bad_hash":row["settlement_evidence"]["result_sha256"]="0"*64
            if modification=="missing_proof":row.pop("settlement_evidence",None)
            (self.out/"forecast_log.json").write_text(json.dumps(log))
            scores,_=runner.prospective([full_result()],[],(FINISHED+timedelta(hours=1)).isoformat())
            with self.subTest(modification=modification):self.assertEqual(scores["h2h"]["n"],0)

    def test_overdue_forecasts_are_explicit_and_versions_remain_separate(self):
        self.freeze()
        with patch.object(runner,"PIPELINE_VERSION","second_synthetic_pipeline"):
            runner.prospective([],[all_markets()],(CREATED+timedelta(minutes=1)).isoformat())
        runner.prospective([],[],(FINISHED+timedelta(days=3)).isoformat())
        report=self.report()
        self.assertEqual(report["forecasts"],10);self.assertEqual(report["unique_fixtures"],1)
        self.assertEqual(report["overdue_forecasts"],10)
        self.assertEqual(set(report["by_pipeline_version"]),{runner.PIPELINE_VERSION,"second_synthetic_pipeline"})
        self.assertEqual(report["by_market"]["h2h"],{"awaiting_result":2})
        self.assertLessEqual(len(report["samples"]),10)
        self.assertFalse(report["verified_value"])

    def test_a_result_cannot_settle_before_the_frozen_start_even_if_date_is_old(self):
        self.freeze();log=self.log()
        for row in log:row["kickoff_utc"]="2026-11-10T15:00:00Z"
        (self.out/"forecast_log.json").write_text(json.dumps(log))
        runner.prospective([result("2026-11-07")],[],"2026-11-08T12:00:00Z")
        self.assertFalse(any(row["settled"] for row in self.log()))

    def test_legacy_records_without_a_start_are_not_reported_as_live_matches(self):
        self.freeze();legacy=deepcopy(self.log()[0]);legacy.pop("kickoff_utc");legacy.pop("forecast_schema_version")
        self.assertEqual(settlement.state(legacy,None,CREATED),"upcoming")
        self.assertEqual(settlement.state(legacy,None,FINISHED),"awaiting_kickoff_evidence")

    def test_completion_guard_uses_the_later_start_within_identity_tolerance(self):
        frozen=self.freeze()[0];played=full_result();played["kickoff_utc"]="2026-11-07T15:00:59Z"
        self.assertEqual(settlement.completion_floor(frozen,played),datetime(2026,11,7,17,0,59,tzinfo=timezone.utc))
        self.assertEqual(settlement.state(frozen,played,datetime(2026,11,7,17,0,30,tzinfo=timezone.utc)),"in_progress")

    def test_source_fingerprint_excludes_other_leagues_fixtures_and_failed_imports(self):
        self.freeze()
        source={"source_id":"synthetic-test-source","content_sha256":"a"*64,"fetched_at":FINISHED.isoformat(),"ok":True,"league":"Premier League","kind":"results"}
        reports=[source,{**source,"league":"La Liga"},{**source,"kind":"fixtures"},{**source,"ok":False}]
        runner.prospective([full_result()],[],FINISHED.isoformat(),reports)
        for row in self.log():
            self.assertEqual(row["settlement_evidence"]["source_snapshots"],[{k:v for k,v in source.items() if k!="ok"}])

    def test_future_alias_changes_cannot_invalidate_an_immutable_result_fingerprint(self):
        self.freeze();runner.prospective([full_result()],[],FINISHED.isoformat())
        row=self.log()[0];identity=settlement.forecast_id(row)
        with patch.dict(runner.ALIASES,{"arsenal":"synthetic_future_alias"}):
            self.assertTrue(settlement.evidence_valid(row))
            self.assertEqual(settlement.forecast_id(row),identity)

    def test_older_evidence_schema_remains_readable_without_rewriting_the_journal(self):
        self.freeze();runner.prospective([full_result()],[],FINISHED.isoformat())
        records=self.log()
        for row in records:
            proof=row["settlement_evidence"];proof["schema_version"]=1
            fingerprint={"identity":runner.key(row),"market":row["market"],"actual_home":proof["actual_home"],
                         "actual_away":proof["actual_away"],"source_kickoff_utc":proof["source_kickoff_utc"]}
            proof["result_sha256"]=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
        (self.out/"forecast_log.json").write_text(json.dumps(records))
        scores,_=runner.prospective([full_result()],[],(FINISHED+timedelta(days=1)).isoformat())
        self.assertEqual(self.log(),records)
        self.assertTrue(all(row["n"]==1 for row in scores.values()))
        self.assertEqual(self.report()["schema_version"],2)

    def test_audit_contract_rejects_profit_flags_inconsistent_groups_and_price_fields(self):
        self.freeze();report=self.report();settlement.validate_report(report)
        for field,value in (("verified_value",True),("operator_settlement_verified",True),("forecasts",100),("price",2)):
            bad=deepcopy(report);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):settlement.validate_report(bad)


if __name__=="__main__":unittest.main()
