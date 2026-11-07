"""Evaluation-only score observations must never leak into model training."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner
import score_evidence as evidence
import settlement
from scripts.validate_outputs import validate_log
from test_scores_probe import NOW, START, forecast


def observation():
    f=forecast()
    return evidence.seal({"validation_version":evidence.VERSION,
      **{k:f[k] for k in ("league","date","home","away","kickoff_utc")},
      "source_fixture_id":"synthetic-only", "fulltime_home":2,"fulltime_away":1,
      "received_at":NOW.isoformat(),"verified_at":NOW.isoformat(),
      "score_updated_at":(START+timedelta(minutes=110)).isoformat(),
      "final_time":(START+timedelta(minutes=112)).isoformat(),"actual_start":START.isoformat(),
      "status_name":"Finished","status_id":2,"participant_ids":[1,2],"ready_for_review":True,
      "score_sha256":evidence.score_digest("synthetic-only",2,1)})


def report():
    return {"validation_version":evidence.VERSION,"pipeline_version":runner.PIPELINE_VERSION,
      "verified_value":False,"production_settlement_enabled":False,"checked_at":NOW.isoformat(),
      "finished_at":NOW.isoformat(),"status":"incomplete_scores_validation","observations":[observation()]}


def source(row):
    return {"ok":True,"league":row["league"],"kind":"settlement_only","source_id":row["source_ids"][0],
      "content_sha256":row["settlement_observation"]["observation_sha256"],"fetched_at":NOW.isoformat()}


class ScoreEvidenceTests(unittest.TestCase):
    def test_qualified_rows_can_be_used_individually_in_an_incomplete_probe(self):
        rows=evidence.results(report(),[forecast()],NOW)
        self.assertEqual(len(rows),1);self.assertEqual((rows[0]["gh"],rows[0]["ga"]),(2,1))
        for missing in ("yh","ya","ch","ca","fh","fa"):self.assertNotIn(missing,rows[0])
        for changes in ({"status":"probe_blocked"},{"pipeline_version":"legacy"},{"verified_value":True},
                        {"checked_at":(NOW-timedelta(hours=13)).isoformat()},
                        {"finished_at":(NOW+timedelta(seconds=1)).isoformat()}):
            self.assertEqual(evidence.results({**report(),**changes},[forecast()],NOW),[])

    def test_tampering_unsupported_periods_counts_status_or_chronology_fail_closed(self):
        self.assertTrue(evidence.valid(observation(),NOW))
        for changes in ({"fulltime_home":True},{"fulltime_home":-1},{"fulltime_home":1.2},
                        {"status_name":"In-Play"},{"status_id":True},{"participant_ids":[1,1]},
                        {"validation_version":"inferred_numeric_zero"},{"final_time":None},
                        {"actual_start":(NOW-timedelta(minutes=10)).isoformat()},
                        {"verified_at":(NOW+timedelta(seconds=1)).isoformat()},
                        {"final_time":(START+timedelta(minutes=89)).isoformat()},
                        {"score_sha256":"a"*64},{"bookmakerOdds":{"forbidden":True}}):
            row=evidence.seal({**observation(),**changes})
            with self.subTest(changes=changes):self.assertFalse(evidence.valid(row,NOW))
        row=observation();row["fulltime_home"]=0
        self.assertFalse(evidence.valid(row,NOW))

    def test_matching_requires_frozen_identity_kickoff_and_pre_match_current_prediction(self):
        for changes in ({"home":"Arsenal FC"},{"kickoff_utc":(START+timedelta(minutes=2)).isoformat()},
                        {"pipeline_version":"legacy"},{"created_at":START.isoformat()}):
            self.assertEqual(evidence.results(report(),[{**forecast(),**changes}],NOW),[])
        self.assertEqual(evidence.results(report(),[forecast(),forecast()],NOW),[])
        doubled={**report(),"observations":[observation(),observation()]}
        self.assertEqual(evidence.results(doubled,[forecast()],NOW),[])

    def freeze(self,out):
        base=forecast();rows=[]
        for market in (*runner.MARKETS,"h2h"):
            row={**base,"market":market}
            if market!="h2h":row.pop("probabilities");row.update(line=runner.MARKETS[market][2],p_over=.6)
            rows.append(row)
        (out/"forecast_log.json").write_text(json.dumps(rows))
        return rows

    def test_only_h2h_and_goals_settle_with_complete_provenance_and_immutable_forecasts(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(runner,"OUT",Path(folder)):
            out=Path(folder);before=self.freeze(out)
            rows=evidence.results(report(),before,NOW)
            scores,_=runner.prospective(rows,[],NOW.isoformat(),[source(rows[0])])
            after=json.loads((out/"forecast_log.json").read_text())
            validate_log(after,before)
            self.assertEqual({r["market"] for r in after if r["settled"]},{"h2h","goals"})
            self.assertEqual(scores["h2h"]["n"],1);self.assertEqual(scores["goals"]["n"],1)
            for row in after:
                if row["settled"]:
                    self.assertEqual(row["settlement_evidence"]["schema_version"],3)
                    self.assertTrue(settlement.evidence_valid(row))
            audit=json.loads((out/"settlement_report.json").read_text())
            self.assertEqual(audit["counts"],{"awaiting_statistics":3,"settled_with_evidence":2})
            runner.prospective([],[],(NOW+timedelta(hours=1)).isoformat())
            self.assertEqual(json.loads((out/"forecast_log.json").read_text()),after)
            repeated=json.loads((out/"settlement_report.json").read_text())
            self.assertEqual(repeated["counts"],{"awaiting_statistics":3,"settled_with_evidence":2})
            changed={**rows[0],"gh":0};changed.pop("settlement_observation")
            scores,_=runner.prospective([changed],[],(NOW+timedelta(hours=2)).isoformat())
            self.assertEqual(json.loads((out/"forecast_log.json").read_text()),after)
            self.assertEqual(scores["h2h"]["n"],0);self.assertEqual(scores["goals"]["n"],0)
            # Conflicting current sources must also quarantine archived scores,
            # rather than looking like a temporarily missing result.
            original_source={**rows[0]};original_source.pop("settlement_observation")
            scores,_=runner.prospective([original_source,changed],[],(NOW+timedelta(hours=3)).isoformat())
            self.assertEqual(scores["h2h"]["n"],0);self.assertEqual(scores["goals"]["n"],0)
            self.assertEqual(json.loads((out/"forecast_log.json").read_text()),after)

    def test_external_proof_cannot_be_removed_or_mutated_or_used_for_other_statistics(self):
        rows=evidence.results(report(),[forecast()],NOW);row=rows[0]
        frozen=forecast();settlement.freeze_result(frozen,row,NOW,[source(row)])
        for change in ("remove","counts","snapshot"):
            modified=deepcopy(frozen);proof=modified["settlement_evidence"]
            if change=="remove":proof.pop("external_result")
            elif change=="counts":proof["external_result"]["fulltime_home"]=0
            else:proof["source_snapshots"][0]["content_sha256"]="a"*64
            self.assertFalse(settlement.evidence_valid(modified))
        legacy={**forecast(),"pipeline_version":"legacy"}
        with self.assertRaises(ValueError):settlement.freeze_result(legacy,row,NOW,[source(row)])

    def test_supplementary_outcomes_do_not_change_training_inputs_or_prediction_freshness(self):
        hist=[{"league":"Premier League","date":(START-timedelta(days=i+2)).date().isoformat(),
               "home":"Arsenal","away":"Chelsea","gh":2,"ga":1} for i in range(110)]
        future={"league":"Premier League","date":"2026-11-08","time":"16:00","home":"Arsenal","away":"Chelsea"}
        data=(hist,[future],[{"ok":True,"league":"Premier League","kind":"results"}])
        with tempfile.TemporaryDirectory() as folder,patch.object(runner,"OUT",Path(folder)):
            out=Path(folder);before=self.freeze(out)
            runner.run(imported=data,run_at=NOW)
            baseline=json.loads((out/"latest.json").read_text())
            rows=evidence.results(report(),before,NOW)
            runner.run(imported=data,run_at=NOW,settlement_results=rows)
            current=json.loads((out/"latest.json").read_text())
        for key in ("fixtures","history_rows","last_stat_date","data_audit","backtest","source_report","data_health"):
            self.assertEqual(baseline[key],current[key],key)
        self.assertEqual(current["prospective"]["h2h"]["n"],1)
        self.assertEqual(len(hist),110)
