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


def execute(research=False,scan_odds=False,imported=None,run_at=None):
    at=run_at or datetime.now(timezone.utc)
    data=imported if imported is not None else runner.load_all(at)
    code=runner.run(imported=data,run_at=at)
    if code:
        return code
    if scan_odds:
        odds_scanner.fetch_scan()
    else:
        odds_scanner.close_watchlist("no_scan_requested")
    performance.run()
    if research:
        hist,fixtures,_=data
        observations=json.loads((runner.OUT/"odds_observations.json").read_text())
        forecasts=json.loads((runner.OUT/"forecast_log.json").read_text())
        comparison=calibration.compare_1x2(hist,fixtures,as_of=at,observations=observations,forecasts=forecasts)
        runner.write_json_atomic(runner.OUT/"calibration_report.json",comparison)
        runner.write_json_atomic(runner.OUT/"model_lab.json",model_lab.experiment(hist,as_of=at))
        elo=elo_challenger.evaluate(hist,fixtures,as_of=at,comparison=comparison)
        elo["market_diagnostic"]=elo_challenger.market_diagnostic(elo,json.loads((runner.OUT/"odds_diagnostics.json").read_text()))
        runner.write_json_atomic(runner.OUT/"elo_challenger.json",elo)
    latest=json.loads((runner.OUT/"latest.json").read_text())
    sources=sorted((r.get("source_url"),r.get("content_sha256")) for r in data[2] if r.get("source_url"))
    revision=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    latest["pipeline_execution"]={"source_commit":revision,"research_refreshed":research,
      "odds_scan_requested":scan_odds,"single_import":True,
      "sources_sha256":hashlib.sha256(json.dumps(sources,separators=(",",":")).encode()).hexdigest()}
    runner.write_json_atomic(runner.OUT/"latest.json",latest)
    print("Coherent pipeline completed; research:",research,"odds scan:",scan_odds)
    return 0


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research",action="store_true")
    parser.add_argument("--scan-odds",action="store_true")
    args=parser.parse_args()
    sys.exit(execute(args.research or os.getenv("REFRESH_RESEARCH")=="true",
                     args.scan_odds or os.getenv("SCAN_ODDS")=="true"))
