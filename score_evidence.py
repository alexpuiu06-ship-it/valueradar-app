"""Validate bounded 90-minute observations for paper evaluation, never training."""
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib
import json

import runner

VERSION="named_fulltime_rechecked_v1"
FIELDS={"validation_version","league","date","home","away","source_fixture_id","kickoff_utc",
        "fulltime_home","fulltime_away","received_at","verified_at","score_updated_at","final_time",
        "actual_start","status_name","status_id","participant_ids","ready_for_review","score_sha256","observation_sha256"}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def score_digest(fixture_id,home,away):
    return digest({"fixture_id":fixture_id,"period":"fulltime","home":home,"away":away})


def seal(row):
    result=deepcopy(row)
    result["observation_sha256"]=digest({k:v for k,v in result.items() if k!="observation_sha256"})
    return result


def result_row(row):
    return {**{k:row[k] for k in ("league","date","home","away","kickoff_utc")},
      "gh":row["fulltime_home"],"ga":row["fulltime_away"],
      "source_ids":["OddsPapi:90min:"+row["source_fixture_id"]],"settlement_observation":deepcopy(row)}


def archived_results(log):
    """Keep known scores visible for statistics queues; current sources take priority."""
    import settlement
    rows={};conflicts=set()
    for entry in log:
        if entry.get("settled") is not True or entry.get("settlement_evidence",{}).get("schema_version")!=3 or not settlement.evidence_valid(entry):continue
        row=result_row(entry["settlement_evidence"]["external_result"]);key=runner.key(row)
        if key in rows and any(row[k]!=rows[key][k] for k in ("gh","ga","kickoff_utc")):conflicts.add(key)
        rows[key]=row
    return [row for key,row in rows.items() if key not in conflicts]


def valid(row,at):
    try:
        if not isinstance(row,dict) or set(row)!=FIELDS or row["validation_version"]!=VERSION:return False
        if row["ready_for_review"] is not True or row["status_name"] not in ("Finished","Ended"):return False
        if isinstance(row["status_id"],bool) or not isinstance(row["status_id"],int) or row["status_id"] not in (2,3):return False
        if row["league"] not in runner.LEAGUES or not all(isinstance(row[k],str) and 0<len(row[k])<=200 for k in ("home","away","source_fixture_id")):return False
        if runner.norm(row["home"])==runner.norm(row["away"]) or not runner.norm(row["home"]) or not runner.norm(row["away"]):return False
        if datetime.strptime(row["date"],"%Y-%m-%d").date().isoformat()!=row["date"]:return False
        ids=row["participant_ids"]
        if not isinstance(ids,list) or len(ids)!=2 or ids[0]==ids[1] or any(isinstance(v,bool) or not isinstance(v,int) or v<=0 for v in ids):return False
        values=(row["fulltime_home"],row["fulltime_away"])
        if any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=30 for v in values):return False
        start,received,verified,end=(runner.timestamp(row[k]) for k in ("kickoff_utc","received_at","verified_at","final_time"))
        if None in (start,received,verified,end):return False
        actual=runner.timestamp(row["actual_start"])
        if row["actual_start"] is not None and actual is None:return False
        latest=max(start,actual or start)
        if not latest+timedelta(minutes=90)<=end<=received<=verified<=at:return False
        if received<latest+timedelta(hours=2):return False
        updated=runner.timestamp(row["score_updated_at"])
        if row["score_updated_at"] is not None and (not updated or updated>received):return False
        if row["score_sha256"]!=score_digest(row["source_fixture_id"],*values):return False
        return row["observation_sha256"]==digest({k:v for k,v in row.items() if k!="observation_sha256"})
    except (ValueError,TypeError,KeyError,OverflowError):return False


def results(report,log,at):
    """Only individually qualified observations matched to frozen current forecasts."""
    if not isinstance(report,dict) or report.get("validation_version")!=VERSION or report.get("pipeline_version")!=runner.PIPELINE_VERSION:return []
    if report.get("status") not in ("diagnostic_scores_for_review","incomplete_scores_validation"):return []
    if report.get("verified_value") is not False or report.get("production_settlement_enabled") is not False:return []
    checked=runner.timestamp(report.get("checked_at"));finished=runner.timestamp(report.get("finished_at"))
    if not checked or not finished or not checked<=finished<=at or at-checked>timedelta(hours=12):return []
    rows=report.get("observations")
    if not isinstance(rows,list) or len(rows)>5:return []
    if not isinstance(log,list):return []
    candidates=[r for r in log if runner.valid_forecast_record(r) and r["market"]=="h2h" and r.get("pipeline_version")==runner.PIPELINE_VERSION
                and r.get("settled") is False and runner.prospective_eligible(r) and runner.fixture_kickoff(r)]
    accepted=[];keys=set();conflicts=set()
    for row in rows:
        if not valid(row,at):continue
        matches=[r for r in candidates if all(row[k]==r[k] for k in ("league","date","home","away"))
                 and abs((runner.fixture_kickoff(r)-runner.timestamp(row["kickoff_utc"])).total_seconds())<=60]
        if len(matches)!=1:continue
        key=runner.key(row)
        if key in keys:conflicts.add(key);continue
        keys.add(key)
        accepted.append(result_row(row))
    return [row for row in accepted if runner.key(row) not in conflicts]
