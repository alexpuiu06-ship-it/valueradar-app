#!/usr/bin/env python3
"""One captured import, one production writer, coherent reports and site artifact."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import runner
import odds_scanner
import performance
import calibration
import model_lab
import elo_challenger
import ro_feed_probe
import settlement
import monitoring
import scores_probe
import score_evidence


def execute(research=False,scan_odds=False,imported=None,run_at=None,probe_ro=False,probe_scores=False):
    at=run_at or datetime.now(timezone.utc)
    data=imported if imported is not None else runner.load_all(at)
    extra=[]
    score_status={"requested":False,"training_use":False,"value_enabled":False}
    if probe_scores:
        # The diagnostic never writes docs. Only individually qualified rows
        # enter paper outcomes, even when other candidates were rejected.
        report_path=ROOT/"work"/"scores_preflight.json"
        scores_probe.run(authenticated=True,output=report_path)
        report=json.loads(report_path.read_text())
        log=json.loads((runner.OUT/"forecast_log.json").read_text())
        extra=score_evidence.results(report,log,datetime.now(timezone.utc))
        score_status.update(requested=True,status=report["status"],qualified_matches=len(extra),
          pending_matches_checked=report.get("pending_unique_matches",0),rejections=report.get("rejections",{}),
          metered_requests_attempted=report["metered_requests_attempted"],checked_at=report["checked_at"],
          notice="At most five pending matches; qualified 90-minute outcomes only. No training data, operator settlement or value validation.")
    code=runner.run(imported=data,run_at=at,settlement_results=extra)
    if code:
        return code
    if scan_odds:
        odds_scanner.fetch_scan()
    else:
        odds_scanner.close_watchlist("no_scan_requested")
    performance.run()
    if probe_ro:
        if (runner.OUT/"ro_feed_status.json").exists() and not (runner.OUT/"ro_feed_history.json").exists():
            monitoring.update_ro_history(runner.OUT/"ro_feed_status.json",runner.OUT/"ro_feed_history.json")
        ro_feed_probe.monitor(output=runner.OUT/"ro_feed_status.json")
    if research:
        hist,fixtures,_=data
        observations=json.loads((runner.OUT/"odds_observations.json").read_text())
        forecasts=json.loads((runner.OUT/"forecast_log.json").read_text())
        latest_for_audit=json.loads((runner.OUT/"latest.json").read_text())
        audit=json.loads((runner.OUT/"settlement_report.json").read_text())
        forecasts=settlement.eligible_forecasts(forecasts,audit,latest_for_audit.get("generated_at"))
        comparison=calibration.compare_1x2(hist,fixtures,as_of=at,observations=observations,forecasts=forecasts)
        runner.write_json_atomic(runner.OUT/"calibration_report.json",comparison)
        runner.write_json_atomic(runner.OUT/"model_lab.json",model_lab.experiment(hist,as_of=at))
        elo=elo_challenger.evaluate(hist,fixtures,as_of=at,comparison=comparison)
        elo["market_diagnostic"]=elo_challenger.market_diagnostic(elo,json.loads((runner.OUT/"odds_diagnostics.json").read_text()))
        runner.write_json_atomic(runner.OUT/"elo_challenger.json",elo)
    latest=json.loads((runner.OUT/"latest.json").read_text())
    audit=json.loads((runner.OUT/"settlement_report.json").read_text())
    log=json.loads((runner.OUT/"forecast_log.json").read_text())
    evaluated=settlement.eligible_forecasts(log,audit,latest.get("generated_at"))
    supplemented=[r for r in evaluated if r.get("pipeline_version")==runner.PIPELINE_VERSION
                  and r.get("settlement_evidence",{}).get("schema_version")==3]
    score_status["eligible_forecasts"]=len(supplemented)
    score_status["eligible_matches"]=len({runner.key(r) for r in supplemented})
    score_status["last_qualified_at"]=max((r["settlement_evidence"]["external_result"]["verified_at"] for r in supplemented),default=None)
    sources=sorted((r.get("source_url"),r.get("content_sha256")) for r in data[2] if r.get("source_url"))
    revision=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    latest["pipeline_execution"]={"source_commit":revision,"research_refreshed":research,
      "odds_scan_requested":scan_odds,"ro_probe_requested":probe_ro,"single_import":True,
      "monitoring_schema_version":1,"settlement_policy_version":"observed_results_v1",
      "supplementary_scores":score_status,
      "sources_sha256":hashlib.sha256(json.dumps(sources,separators=(",",":")).encode()).hexdigest()}
    runner.write_json_atomic(runner.OUT/"latest.json",latest)
    monitoring.refresh()
    print("Coherent pipeline completed; research:",research,"odds scan:",scan_odds,"RO diagnostic:",probe_ro)
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research",action="store_true")
    parser.add_argument("--scan-odds",action="store_true")
    parser.add_argument("--probe-ro",action="store_true",help="Run the bounded RO aggregate diagnostic; never enables value selections")
    parser.add_argument("--probe-scores",action="store_true",help="Check up to five pending 90-minute outcomes using the free account, evaluation only")
    args=parser.parse_args(argv)
    return execute(args.research or os.getenv("REFRESH_RESEARCH")=="true",
                   args.scan_odds or os.getenv("SCAN_ODDS")=="true",
                   probe_ro=args.probe_ro or os.getenv("PROBE_RO")=="true",
                   probe_scores=args.probe_scores or os.getenv("PROBE_SCORES")=="true")


if __name__=="__main__":
    sys.exit(main())
