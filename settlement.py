"""Audit observed match results without rewriting frozen forecasts or claiming ROI."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
import re

import runner

STATES=("upcoming","in_progress","awaiting_kickoff_evidence","awaiting_result","awaiting_statistics","ready_to_settle",
        "blocked_creation_evidence","blocked_kickoff_conflict","settled_with_evidence",
        "settled_timing_unverifiable","settled_result_conflict","settled_evidence_missing")


def counts(entry,played):
    if not played:return None
    if played.get("settlement_observation") and entry.get("pipeline_version")!=runner.PIPELINE_VERSION:return None
    home,away=("gh","ga") if entry["market"]=="h2h" else runner.MARKETS[entry["market"]][:2]
    values=runner.number(played.get(home)),runner.number(played.get(away))
    return values if None not in values else None


def completion_floor(entry,played=None):
    starts=[runner.fixture_kickoff(entry),runner.fixture_kickoff(played) if played else None]
    if entry.get("settled"):
        proof=entry.get("settlement_evidence")
        if isinstance(proof,dict):starts.append(runner.timestamp(proof.get("source_kickoff_utc")))
    start=max((value for value in starts if value is not None),default=None)
    if start:return start.astimezone(timezone.utc)+timedelta(hours=2)
    # Unknown kickoff on a historical fixed-offset date: wait until even the
    # latest possible kickoff + two hours. This is an operational guard.
    day=datetime.fromisoformat(entry["date"]).replace(tzinfo=timezone(timedelta(hours=1)))
    return day+timedelta(days=1,hours=2)


def evidence_valid(entry):
    proof=entry.get("settlement_evidence")
    if not isinstance(proof,dict) or proof.get("schema_version") not in (1,2,3):return False
    if proof.get("kind")!="observed_public_result_not_operator_verification":return False
    if proof.get("observed_at")!=entry.get("settled_at"):return False
    values=runner.number(proof.get("actual_home")),runner.number(proof.get("actual_away"))
    if None in values:return False
    start=proof.get("source_kickoff_utc")
    if start is not None and runner.timestamp(start) is None:return False
    frozen=runner.fixture_kickoff(entry)
    if frozen and start and abs((frozen-runner.timestamp(start)).total_seconds())>60:return False
    identity=runner.key(entry) if proof["schema_version"]==1 else tuple(entry[k] for k in ("league","date","home","away"))
    fingerprint={"identity":identity,"market":entry["market"],"actual_home":values[0],"actual_away":values[1],"source_kickoff_utc":start}
    digest=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
    if proof.get("result_sha256")!=digest:return False
    if proof["schema_version"]==3:
        import score_evidence
        observed=proof.get("external_result")
        at=runner.timestamp(proof.get("observed_at"))
        if not at or not score_evidence.valid(observed,at) or entry.get("pipeline_version")!=runner.PIPELINE_VERSION:return False
        if any(observed[k]!=entry[k] for k in ("league","date","home","away")) or start!=observed["kickoff_utc"]:return False
        if values!=(observed["fulltime_home"],observed["fulltime_away"]) or entry["market"] not in ("h2h","goals"):return False
        source_id="OddsPapi:90min:"+observed["source_fixture_id"]
        snapshots=proof.get("source_snapshots")
        if source_id not in proof.get("source_ids",[]) or not isinstance(snapshots,list) or not any(
          s.get("source_id")==source_id and s.get("league")==entry["league"] and s.get("kind")=="settlement_only"
          and s.get("content_sha256")==observed["observation_sha256"] and s.get("fetched_at")==observed["verified_at"]
          for s in snapshots if isinstance(s,dict)):return False
    if entry["market"]=="h2h":
        actual="home" if values[0]>values[1] else "away" if values[0]<values[1] else "draw"
        return entry.get("actual_outcome")==actual
    return (entry.get("actual_total")==sum(values) and
            entry.get("actual_over")==int(sum(values)>entry["line"]))


def state(entry,played,at):
    created=runner.timestamp(entry.get("created_at"))
    if not created or created>at or not runner.prospective_eligible(entry):return "blocked_creation_evidence"
    if played and played.get("result_conflict") is True:return "settled_result_conflict" if entry.get("settled") else "awaiting_result"
    frozen=runner.fixture_kickoff(entry)
    actual=runner.fixture_kickoff(played) if played else None
    if frozen and actual and abs((frozen-actual).total_seconds())>60:return "blocked_kickoff_conflict"
    if not runner.prospective_eligible(entry,played):return "blocked_creation_evidence"
    minimum=completion_floor(entry,played)
    observed=counts(entry,played)
    if entry.get("settled"):
        settled=runner.timestamp(entry.get("settled_at"))
        if not settled or not minimum<=settled<=at:return "settled_timing_unverifiable"
        if observed:
            proof=entry.get("settlement_evidence")
            if evidence_valid(entry) and observed!=(proof["actual_home"],proof["actual_away"]):return "settled_result_conflict"
            if entry["market"]=="h2h":
                outcome="home" if observed[0]>observed[1] else "away" if observed[0]<observed[1] else "draw"
                consistent=entry.get("actual_outcome")==outcome
            else:consistent=(entry.get("actual_total")==sum(observed) and entry.get("actual_over")==int(sum(observed)>entry["line"]))
            if not consistent:return "settled_result_conflict"
        return "settled_with_evidence" if evidence_valid(entry) else "settled_evidence_missing"
    start=frozen or actual
    if start and at<start:return "upcoming"
    if start is None:
        earliest=minimum-timedelta(days=1,hours=2)
        if at<earliest:return "upcoming"
        if at<minimum:return "awaiting_kickoff_evidence"
    if at<minimum:return "in_progress"
    if not played:return "awaiting_result"
    if observed is None:return "awaiting_statistics"
    return "ready_to_settle"


def freeze_result(entry,played,at,source_report=()):
    if state(entry,played,at)!="ready_to_settle":raise ValueError("Settlement requires an eligible completed result")
    external=played.get("settlement_observation")
    if external:
        import score_evidence
        if not score_evidence.valid(external,at):raise ValueError("Invalid external result evidence")
    home,away=counts(entry,played)
    if entry["market"]=="h2h":entry["actual_outcome"]="home" if home>away else "away" if home<away else "draw"
    else:entry.update(actual_total=home+away,actual_over=int(home+away>entry["line"]))
    stamp=at.astimezone(timezone.utc).isoformat()
    source_ids=sorted({v for v in played.get("source_ids",[]) if isinstance(v,str)})
    source_start=runner.fixture_kickoff(played)
    fingerprint={"identity":tuple(entry[k] for k in ("league","date","home","away")),"market":entry["market"],"actual_home":home,"actual_away":away,
                 "source_kickoff_utc":source_start.astimezone(timezone.utc).isoformat() if source_start else None}
    snapshots=[{k:source[k] for k in ("league","kind","source_id","content_sha256","fetched_at") if k in source}
               for source in source_report if source.get("source_id") in source_ids and source.get("ok") is True
               and source.get("league")==played["league"] and source.get("kind") in ("results","historical","settlement_only")]
    entry.update(settled=True,settled_at=stamp,settlement_evidence={"schema_version":3 if external else 2,
      "kind":"observed_public_result_not_operator_verification","observed_at":stamp,
      "actual_home":home,"actual_away":away,"result_sha256":hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest(),
      "source_kickoff_utc":fingerprint["source_kickoff_utc"],"source_ids":source_ids,"source_snapshots":snapshots})
    if external:entry["settlement_evidence"]["external_result"]=external


def audit(log,outcomes,at,integrity=None):
    states=Counter();versions=defaultdict(Counter);markets=defaultdict(Counter);leagues=defaultdict(Counter)
    fixtures=set();samples=[];overdue=0;ready=0;excluded=[]
    for entry in log:
        status=state(entry,outcomes.get(runner.key(entry)),at)
        states[status]+=1
        versions[entry.get("pipeline_version","legacy_unversioned")][status]+=1
        markets[entry["market"]][status]+=1;leagues[entry["league"]][status]+=1
        fixtures.add(runner.key(entry))
        late=status in ("awaiting_result","awaiting_statistics") and at-completion_floor(entry,outcomes.get(runner.key(entry)))>=timedelta(hours=48)
        if entry.get("settled") and status!="settled_with_evidence":excluded.append(forecast_id(entry))
        overdue+=int(late);ready+=int(status=="ready_to_settle")
        if status not in ("upcoming","settled_with_evidence"):
            samples.append({**{k:entry[k] for k in ("league","date","home","away","market")},
              "pipeline_version":entry.get("pipeline_version","legacy_unversioned"),"status":status,
              "kickoff_utc":entry.get("kickoff_utc"),"overdue":bool(late)})
    samples.sort(key=lambda row:(row["date"],row["league"],row["home"],row["market"],row["pipeline_version"]))
    return {"schema_version":2,"generated_at":at.astimezone(timezone.utc).isoformat(),"forecasts":len(log),
      "unique_fixtures":len(fixtures),"counts":dict(states),"by_pipeline_version":{k:dict(v) for k,v in versions.items()},
      "settled_records":sum(r.get("settled") is True for r in log),"excluded_settled_ids":sorted(excluded),
      "by_market":{k:dict(v) for k,v in markets.items()},"by_league":{k:dict(v) for k,v in leagues.items()},
      "overdue_after_hours":48,"overdue_forecasts":overdue,"ready_but_unsettled":ready,
      "result_conflicts_quarantined":(integrity or {}).get("conflicting_events_quarantined",0),"samples":samples[:10],
      "verified_value":False,"operator_settlement_verified":False,
      "counting_policy":"Counts are forecasts, including separate markets/pipeline versions; unique_fixtures counts matches.",
      "completion_policy":"Result source plus at least two hours after known kickoff; timing guard is not independent final-status or bookmaker-rule verification."}


def forecast_id(entry,legacy=False):
    # Freeze literal journal identity; future name aliases cannot change an
    # archived fingerprint or a quarantined forecast's identity.
    identity=runner.forecast_identity(entry) if legacy else tuple(entry[k] for k in ("league","date","home","away","market"))+(entry.get("line") if entry["market"]!="h2h" else None,entry.get("pipeline_version","legacy_unversioned"))
    return hashlib.sha256(json.dumps(identity,separators=(",",":")).encode()).hexdigest()


def validate_report(report,summary=False):
    keys={"schema_version","generated_at","forecasts","unique_fixtures","counts","by_pipeline_version","by_market","by_league",
          "settled_records","excluded_settled_ids","overdue_after_hours","overdue_forecasts","ready_but_unsettled",
          "result_conflicts_quarantined","samples","verified_value","operator_settlement_verified","counting_policy","completion_policy"}
    if summary:keys.remove("excluded_settled_ids")
    if not isinstance(report,dict) or set(report)!=keys:raise ValueError("Unexpected settlement audit fields")
    if not isinstance(report,dict) or report.get("schema_version") not in (1,2):raise ValueError("Invalid settlement audit schema")
    if report.get("verified_value") is not False or report.get("operator_settlement_verified") is not False:raise ValueError("Settlement observations cannot verify betting value")
    if runner.timestamp(report.get("generated_at")) is None:raise ValueError("Settlement audit needs a timezone")
    def integer(v):return isinstance(v,int) and not isinstance(v,bool) and v>=0
    for field in ("forecasts","unique_fixtures","settled_records","overdue_forecasts","ready_but_unsettled","result_conflicts_quarantined"):
        if not integer(report.get(field)):raise ValueError("Invalid settlement audit counts")
    counters=report.get("counts")
    if not isinstance(counters,dict) or set(counters)-set(STATES) or not all(integer(v) for v in counters.values()) or sum(counters.values())!=report["forecasts"]:
        raise ValueError("Inconsistent settlement audit states")
    for field in ("by_pipeline_version","by_market","by_league"):
        grouped=report.get(field)
        if not isinstance(grouped,dict):raise ValueError("Missing settlement audit grouping")
        summed=Counter()
        for name,rows in grouped.items():
            if not isinstance(name,str) or not isinstance(rows,dict) or set(rows)-set(STATES) or not all(integer(v) for v in rows.values()):raise ValueError("Invalid settlement audit grouping")
            summed.update(rows)
        if summed!=Counter(counters):raise ValueError("Settlement groups disagree")
    if not counters.get("settled_with_evidence",0)<=report["settled_records"]<=report["forecasts"] or report["unique_fixtures"]>report["forecasts"] or report["overdue_forecasts"]>report["forecasts"]:raise ValueError("Impossible settlement counts")
    if not summary:
        excluded=report.get("excluded_settled_ids")
        if not isinstance(excluded,list) or any(not isinstance(v,str) or not re.fullmatch(r"[0-9a-f]{64}",v) for v in excluded) or len(set(excluded))!=len(excluded):raise ValueError("Invalid settlement quarantine identities")
        if len(excluded)+counters.get("settled_with_evidence",0)!=report["settled_records"]:raise ValueError("Settlement eligibility counts disagree")
    if report["ready_but_unsettled"]!=counters.get("ready_to_settle",0) or report["ready_but_unsettled"]!=0:raise ValueError("Eligible results were not settled")
    if not isinstance(report.get("samples"),list) or len(report["samples"])>10:raise ValueError("Unbounded settlement diagnostic samples")
    for sample in report["samples"]:
        if not isinstance(sample,dict) or set(sample)!={"league","date","home","away","market","pipeline_version","status","kickoff_utc","overdue"}:raise ValueError("Unexpected settlement sample fields")
        if sample["league"] not in runner.LEAGUES or sample["market"] not in (*runner.MARKETS,"h2h") or sample["status"] not in STATES or not isinstance(sample["overdue"],bool):raise ValueError("Invalid settlement sample")
    if report["overdue_after_hours"]!=48:raise ValueError("Unexpected settlement monitoring deadline")


def eligible_forecasts(log,report,expected_generated_at):
    """A benchmark must use the same settlement audit as the current pipeline."""
    try:validate_report(report)
    except (ValueError,TypeError,KeyError):return []
    if report["generated_at"]!=expected_generated_at:return []
    excluded=set(report["excluded_settled_ids"]);at=runner.timestamp(report["generated_at"])
    return [row for row in (log if isinstance(log,list) else []) if runner.valid_forecast_record(row) and row.get("settled") is True and forecast_id(row,legacy=report["schema_version"]==1) not in excluded
            and state(row,None,at)=="settled_with_evidence"]
