#!/usr/bin/env python3
"""Evaluate free final scores for archived forecasts; never infer periods or settle bets."""
from collections import Counter
from datetime import datetime,timedelta,timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

import oddspapi_probe as api
import odds_scanner as odds
import runner

REPORT=Path(__file__).resolve().parent/"work"/"scores_preflight.json"
MAX_MATCHES=5
MAX_REQUESTS=12
TERMINAL={"Finished","Ended"}


def pending_forecasts(log,version,at,league="All leagues"):
    if not isinstance(log,list):raise api.ProbeError("invalid_forecast_log_schema")
    rows={}
    for entry in log:
        if not runner.valid_forecast_record(entry) or entry.get("settled") is not False or entry.get("market")!="h2h" or entry.get("pipeline_version")!=version:continue
        start=runner.fixture_kickoff(entry)
        if not start or not at-timedelta(days=7)<=start<=at-timedelta(hours=2) or not runner.prospective_eligible(entry):continue
        if league!="All leagues" and entry["league"]!=league:continue
        key=runner.key(entry)
        if key in rows:raise api.ProbeError("duplicate_pending_forecast")
        rows[key]=entry
    return sorted(rows.values(),key=lambda row:(runner.fixture_kickoff(row),runner.key(row)))[:MAX_MATCHES]


def fixture_identity(row,league):
    if not isinstance(row,dict) or row.get("sportId")!=10 or row.get("tournamentId")!=api.TOURNAMENTS[league][0]:return None
    if any(not isinstance(row.get(k),str) or not row[k].strip() for k in ("fixtureId","participant1Name","participant2Name")):return None
    if any(not api.integer(row.get(k)) or row[k]<=0 for k in ("participant1Id","participant2Id")) or row["participant1Id"]==row["participant2Id"]:return None
    start=runner.timestamp(row.get("startTime"))
    home,away=odds.canonical(row["participant1Name"]),odds.canonical(row["participant2Name"])
    if not start or not home or not away or home==away:return None
    return (league,home,away,start)


def match_fixtures(payload,candidates):
    if not isinstance(payload,list):raise api.ProbeError("invalid_fixture_list")
    ids=Counter(r.get("fixtureId") for r in payload if isinstance(r,dict) and isinstance(r.get("fixtureId"),str))
    selected={};mapped=Counter();canonical=Counter();pairs=[]
    for row in payload:
        for league in {f["league"] for f in candidates}:
            identity=fixture_identity(row,league)
            if identity is None:continue
            canonical[identity]+=1
            matches=[f for f in candidates if f["league"]==league and odds.canonical(f["home"])==identity[1]
              and odds.canonical(f["away"])==identity[2] and abs((runner.fixture_kickoff(f)-identity[3]).total_seconds())<=60]
            if len(matches)==1:
                key=runner.key(matches[0]);mapped[key]+=1;pairs.append((key,row,identity))
    for key,row,identity in pairs:
        if ids[row["fixtureId"]]==1 and canonical[identity]==1 and mapped[key]==1:selected[key]=row
    return selected


def terminal_fixture(row,league,at):
    identity=fixture_identity(row,league)
    if identity is None:raise api.ProbeError("invalid_result_identity")
    # The two official docs disagree on numeric codes; neither a numeric code
    # alone nor hasOdds (false after finish) establishes a completed match.
    if row.get("statusName") not in TERMINAL or not api.integer(row.get("statusId")) or row["statusId"] not in (2,3):raise api.ProbeError("not_explicitly_finished")
    start=identity[3];actual=runner.timestamp(row.get("trueStartTime"));end=runner.timestamp(row.get("trueEndTime"))
    if row.get("trueStartTime") is not None and actual is None:raise api.ProbeError("invalid_actual_start")
    if row.get("trueEndTime") is not None and end is None:raise api.ProbeError("invalid_final_time")
    if at<max(start,actual or start)+timedelta(hours=2):raise api.ProbeError("completion_guard")
    if end and (end>at or end<max(start,actual or start)+timedelta(minutes=90)):raise api.ProbeError("implausible_final_time")
    return {"identity":identity,"fixture_id":row["fixtureId"],"participant_ids":(row["participant1Id"],row["participant2Id"]),
            "actual_start":actual,"end":end}


def fulltime_score(payload,fixture_id,at):
    if not isinstance(payload,dict) or payload.get("fixtureId")!=fixture_id:raise api.ProbeError("score_fixture_id_mismatch")
    scores=payload.get("scores")
    periods=scores.get("periods") if isinstance(scores,dict) else None
    # Official soccer walkthrough identifies fulltime as 90 minutes. Never
    # substitute result (can include extra time) or undocumented numeric keys.
    full=periods.get("fulltime") if isinstance(periods,dict) else None
    if not isinstance(full,dict):raise api.ProbeError("missing_named_fulltime_period")
    values=(full.get("participant1Score"),full.get("participant2Score"))
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not float(v).is_integer() or not 0<=v<=30 for v in values):raise api.ProbeError("invalid_fulltime_score")
    updated=runner.timestamp(full.get("updatedAt"))
    if full.get("updatedAt") is not None and (not updated or updated>at):raise api.ProbeError("invalid_score_update_time")
    return tuple(int(v) for v in values),updated


def run(authenticated=False,league="All leagues",output=REPORT):
    if league not in ("All leagues",*runner.LEAGUES):raise ValueError("Unsupported league")
    report={"provider":"OddsPapi","purpose":"finished_score_diagnostic_only","checked_at":datetime.now(timezone.utc).isoformat(),
      "verified_value":False,"production_settlement_enabled":False,"raw_provider_payload_saved":False,
      "metered_requests_attempted":0,"unmetered_requests_attempted":0,"max_metered_requests":MAX_REQUESTS,
      "max_matched_fixtures":MAX_MATCHES,"league":league,"observations":[],"rejections":{},"status":"not_requested" if not authenticated else "needs_api_key"}
    key=os.getenv("ODDSPAPI_API_KEY","").strip() if authenticated else "";last=None;rejected=Counter()
    def request(path,params):
        nonlocal last
        if path=="/account":report["unmetered_requests_attempted"]+=1
        else:
            if report["metered_requests_attempted"]>=MAX_REQUESTS:raise api.ProbeError("request_budget_exhausted")
            report["metered_requests_attempted"]+=1
        if last is not None:time.sleep(max(0,2.1-(time.monotonic()-last)))
        payload,error=api.fetch(path,params,key);last=time.monotonic()
        if error:
            report["failed_endpoint"]=path
            raise api.ProbeError(error)
        return payload
    code=0 if not authenticated else 2
    if key:
        try:
            latest=json.loads((runner.OUT/"latest.json").read_text());log=json.loads((runner.OUT/"forecast_log.json").read_text())
            at=datetime.now(timezone.utc);generated=runner.timestamp(latest.get("generated_at"))
            if not generated or not 0<=(at-generated).total_seconds()<=12*3600:raise api.ProbeError("stale_analysis")
            if latest.get("pipeline_version")!=runner.PIPELINE_VERSION:raise api.ProbeError("unsupported_analysis_pipeline")
            report["pipeline_version"]=latest["pipeline_version"]
            candidates=pending_forecasts(log,latest.get("pipeline_version"),at,league)
            report["pending_unique_matches"]=len(candidates)
            if not candidates:report["status"]="no_pending_completed_matches";code=0
            else:
                before=api.account_summary(request("/account",{}));report["account_before"]=before
                if before["request_limit"]!=250 or not before["soccer_included"]:raise api.ProbeError("free_soccer_account_not_confirmed")
                if before["remaining"]<MAX_REQUESTS+10:raise api.ProbeError("quota_reserve_guard")
                leagues=sorted({r["league"] for r in candidates})
                catalog=api.verified_tournaments(request("/tournaments",{"sportId":10,"language":"en"}),leagues)
                if not all(catalog.values()):raise api.ProbeError("tournament_catalog_not_confirmed")
                first=min(runner.fixture_kickoff(f) for f in candidates)-timedelta(minutes=1)
                last_start=max(runner.fixture_kickoff(f) for f in candidates)+timedelta(minutes=1)
                payload=request("/fixtures",{"sportId":10,"from":first.isoformat(),"to":last_start.isoformat(),"language":"en"})
                report["provider_fixtures_received"]=len(payload) if isinstance(payload,list) else None
                selected=match_fixtures(payload,candidates)
                report["matched_fixture_identities"]=len(selected)
                for frozen in candidates:
                    row=selected.get(runner.key(frozen))
                    if row is None:rejected["missing_or_ambiguous_fixture_match"]+=1;continue
                    try:
                        view=terminal_fixture(row,frozen["league"],datetime.now(timezone.utc))
                        scores=request("/scores",{"fixtureId":view["fixture_id"]})
                        received=datetime.now(timezone.utc);values,updated=fulltime_score(scores,view["fixture_id"],received)
                        final=request("/fixture",{"fixtureId":view["fixture_id"],"language":"en"})
                        final_view=terminal_fixture(final,frozen["league"],datetime.now(timezone.utc))
                        if view!=final_view:raise api.ProbeError("fixture_changed_during_score_request")
                        # A bounded per-forecast observation, not a bulk feed dump.
                        report["observations"].append({"league":frozen["league"],"date":frozen["date"],"home":frozen["home"],"away":frozen["away"],
                          "source_fixture_id":view["fixture_id"],"kickoff_utc":view["identity"][3].isoformat(),
                          "fulltime_home":values[0],"fulltime_away":values[1],"received_at":received.isoformat(),
                          "score_updated_at":updated.isoformat() if updated else None,"final_time":view["end"].isoformat() if view["end"] else None,
                          "ready_for_review":view["end"] is not None,
                          "score_sha256":hashlib.sha256(json.dumps({"fixture_id":view["fixture_id"],"period":"fulltime","home":values[0],"away":values[1]},sort_keys=True).encode()).hexdigest()})
                    except api.ProbeError as exc:
                        reason=str(exc)
                        if reason not in SCORE_REASONS:raise
                        rejected[reason]+=1
                report["account_after"]=api.account_summary(request("/account",{}))
                report["observed_matches"]=len(report["observations"])
                report["reviewable_matches"]=sum(r["ready_for_review"] for r in report["observations"])
                complete=len(report["observations"])==len(candidates) and all(r["ready_for_review"] for r in report["observations"])
                report["status"]="diagnostic_scores_for_review" if complete else "incomplete_scores_validation"
                if complete:code=0
        except api.ProbeError as exc:
            reason=str(exc)
            report.update(status="probe_blocked",reason=reason if reason in SCORE_REASONS or reason in api.REASONS or re.fullmatch(r"http_[45][0-9]{2}",reason) else "provider_error")
        except Exception as exc:report.update(status="internal_error",reason=type(exc).__name__)
    report["rejections"]=dict(rejected);report["finished_at"]=datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True,exist_ok=True);runner.write_json_atomic(output,report)
    print("SCORES_DIAGNOSTIC "+json.dumps(report,ensure_ascii=False,allow_nan=False))
    return code


SCORE_REASONS={"duplicate_pending_forecast","invalid_forecast_log_schema","unsupported_analysis_pipeline","invalid_fixture_list","invalid_result_identity","not_explicitly_finished",
 "invalid_actual_start","invalid_final_time","completion_guard","implausible_final_time","score_fixture_id_mismatch",
 "missing_named_fulltime_period","invalid_fulltime_score","invalid_score_update_time","free_soccer_account_not_confirmed",
 "tournament_catalog_not_confirmed","fixture_changed_during_score_request"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authenticated",action="store_true")
    parser.add_argument("--league",choices=["All leagues",*runner.LEAGUES],default=os.getenv("PROBE_LEAGUE","All leagues"))
    args=parser.parse_args()
    raise SystemExit(run(args.authenticated or os.getenv("AUTHENTICATED_PROBE")=="true",args.league))
