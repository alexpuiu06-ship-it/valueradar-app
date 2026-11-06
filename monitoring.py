"""Bounded operational evidence; no raw odds, backfilled samples or value capability."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import re
from zoneinfo import ZoneInfo

import runner
import settlement

BOOKS=("superbet_ro","netbet_ro")
RETENTION_DAYS=90
MAX_RECORDS=512
LEAGUE_STATES={"diagnostic_only","incomplete_quote_validation","needs_api_key","provider_error",
               "stale_analysis","invalid_schema","diagnostic_error"}


def count(value):return isinstance(value,int) and not isinstance(value,bool) and 0<=value<10**10


def read(path,default=None):
    if not Path(path).exists():return default
    # Corrupted evidence is not replaced by an empty successful history.
    def invalid(value):raise ValueError("Non-finite monitoring value")
    return json.loads(Path(path).read_text(),parse_constant=invalid)


def validate_record(record,at):
    fields={"observed_at","day_ro","max_quote_age_seconds","authenticated_requests","leagues"}
    if not isinstance(record,dict) or set(record)!=fields:raise ValueError("Unexpected coverage record fields")
    observed=runner.timestamp(record["observed_at"])
    if not observed or observed>at+timedelta(minutes=5):raise ValueError("Invalid coverage observation time")
    if record["day_ro"]!=observed.astimezone(ZoneInfo("Europe/Bucharest")).date().isoformat():raise ValueError("Incorrect Romanian observation date")
    if record["max_quote_age_seconds"]!=120:raise ValueError("Coverage quote age must remain 120 seconds")
    requests=record["authenticated_requests"]
    if requests is not None and (not count(requests) or requests>5):raise ValueError("Coverage pass exceeds request budget")
    rows=record["leagues"]
    if not isinstance(rows,list) or len(rows)!=5:raise ValueError("Coverage record needs five league states")
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"league","status","received_at","delivery_filter_seconds","error","books"}:raise ValueError("Unexpected coverage league fields")
        if row["league"] not in runner.LEAGUES or row["league"] in seen:raise ValueError("Duplicate or unknown coverage league")
        seen.add(row["league"])
        if row["status"] not in LEAGUE_STATES or row["delivery_filter_seconds"] not in (120,3600):raise ValueError("Invalid coverage state or delivery filter")
        if row["received_at"] is not None:
            received=runner.timestamp(row["received_at"])
            if not received or received>observed+timedelta(minutes=5):raise ValueError("Invalid coverage receipt timestamp")
        if row["error"] is not None and (not isinstance(row["error"],str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}",row["error"])):raise ValueError("Unsafe coverage error text")
        if not isinstance(row["books"],dict) or set(row["books"])!=set(BOOKS):raise ValueError("Unknown coverage bookmaker scope")
        for diag in row["books"].values():
            if not isinstance(diag,dict) or set(diag)!={"received","complete","matched","rejections"}:raise ValueError("Unexpected bookmaker coverage fields")
            values=[diag[k] for k in ("received","complete","matched")]
            if not all(v is None for v in values) and (not all(count(v) for v in values) or not values[2]<=values[1]<=values[0]):raise ValueError("Inconsistent coverage counts")
            reasons=diag["rejections"]
            if not isinstance(reasons,dict) or any(not isinstance(k,str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}",k) or not count(v) for k,v in reasons.items()):raise ValueError("Invalid coverage rejection counts")


def compact_status(report,at):
    if not isinstance(report,dict) or report.get("provider")!="PropLine" or report.get("schema_version")!=1:raise ValueError("Unknown coverage provider schema")
    if any(report.get(k) is not False for k in ("verified_value","operator_prices_independently_verified","raw_odds_saved")):raise ValueError("Coverage cannot verify value or export odds")
    if report.get("requested_books")!=list(BOOKS):raise ValueError("Unknown requested coverage books")
    observed=runner.timestamp(report.get("generated_at"))
    if not observed:raise ValueError("Missing coverage observation time")
    record={"observed_at":observed.isoformat(),"day_ro":observed.astimezone(ZoneInfo("Europe/Bucharest")).date().isoformat(),
      "max_quote_age_seconds":report.get("max_quote_age_seconds"),"authenticated_requests":report.get("authenticated_requests"),"leagues":[]}
    for row in report.get("leagues",[]):
        quality=row.get("quality");books={}
        for book in BOOKS:
            diag=(quality.get("book_diagnostics") or {}).get(book) if isinstance(quality,dict) else None
            books[book]={"received":diag.get("received_blocks") if isinstance(diag,dict) else None,
              "complete":diag.get("complete_recent_markets") if isinstance(diag,dict) else None,
              "matched":diag.get("matched_current_model_markets") if isinstance(diag,dict) else None,
              "rejections":diag.get("rejection_counts",{}) if isinstance(diag,dict) else {}}
        record["leagues"].append({"league":row.get("league"),"status":row.get("status"),"received_at":row.get("received_at"),
          "delivery_filter_seconds":row.get("requested_max_delivery_age_seconds"),"error":row.get("error"),"books":books})
    validate_record(record,at)
    return record


def validate_history(history,at=None):
    at=at or datetime.now(timezone.utc)
    fields={"schema_version","provider","generated_at","retention_days","max_records","records",
            "verified_value","operator_prices_independently_verified","raw_odds_saved"}
    if not isinstance(history,dict) or set(history)!=fields or history["schema_version"]!=1 or history["provider"]!="PropLine":raise ValueError("Invalid coverage history schema")
    if history["retention_days"]!=RETENTION_DAYS or history["max_records"]!=MAX_RECORDS:raise ValueError("Unexpected coverage retention")
    if any(history[k] is not False for k in ("verified_value","operator_prices_independently_verified","raw_odds_saved")):raise ValueError("Coverage history cannot verify value")
    stamp=runner.timestamp(history["generated_at"])
    if not stamp or stamp>at+timedelta(minutes=5):raise ValueError("Invalid coverage history generation time")
    rows=history["records"]
    if not isinstance(rows,list) or len(rows)>MAX_RECORDS:raise ValueError("Unbounded coverage history")
    previous=None
    for record in rows:
        validate_record(record,at)
        observed=runner.timestamp(record["observed_at"])
        if previous is not None and observed<=previous:raise ValueError("Duplicate or unsorted coverage history")
        previous=observed


def update_ro_history(status_path,history_path,at=None):
    at=at or datetime.now(timezone.utc)
    history=read(history_path)
    if history is None:
        history={"schema_version":1,"provider":"PropLine","generated_at":at.isoformat(),"retention_days":RETENTION_DAYS,
          "max_records":MAX_RECORDS,"records":[],"verified_value":False,"operator_prices_independently_verified":False,"raw_odds_saved":False}
    validate_history(history,at)
    report=read(status_path)
    cutoff=at-timedelta(days=RETENTION_DAYS)
    records=history["records"]
    if report is not None:
        record=compact_status(report,at)
        same=[r for r in records if runner.timestamp(r["observed_at"])==runner.timestamp(record["observed_at"])]
        if same and same[0]!=record:raise ValueError("A stored coverage observation cannot be rewritten")
        if not same and runner.timestamp(record["observed_at"])>=cutoff:records.append(record)
    history["records"]=sorted((r for r in records if runner.timestamp(r["observed_at"])>=cutoff),key=lambda r:runner.timestamp(r["observed_at"]))
    history["generated_at"]=at.isoformat()
    validate_history(history,at)
    runner.write_json_atomic(Path(history_path),history)
    return history


def refresh(output=None,at=None):
    at=at or datetime.now(timezone.utc);out=output or runner.OUT
    latest=read(out/"latest.json");audit=read(out/"settlement_report.json")
    settlement.validate_report(audit)
    if audit["generated_at"]!=latest.get("generated_at"):raise ValueError("Settlement audit belongs to a different analysis")
    history=update_ro_history(out/"ro_feed_status.json",out/"ro_feed_history.json",at)
    failed=[{"league":row.get("league"),"kind":row.get("kind")} for row in latest.get("source_report",[]) if row.get("ok") is not True]
    report={"schema_version":1,"generated_at":at.isoformat(),"analysis_generated_at":latest.get("generated_at"),
      "pipeline_version":latest.get("pipeline_version"),"verified_value":False,"hypothetical_roi":None,
      "policy":{"model_expected_interval_hours":4,"model_warning_after_hours":6,"ro_expected_interval_hours":24,"ro_warning_after_hours":30},
      "sources":{"successful":latest.get("source_success"),"total":latest.get("source_total"),"failures":failed},
      "ro_history":{"records":len(history["records"]),"days_observed":len({r["day_ro"] for r in history["records"]}),
        "last_observed_at":history["records"][-1]["observed_at"] if history["records"] else None},
      "settlement":{k:v for k,v in audit.items() if k!="excluded_settled_ids"}}
    validate_operations(report)
    runner.write_json_atomic(out/"operations_report.json",report)
    return report


def validate_operations(report):
    keys={"schema_version","generated_at","analysis_generated_at","pipeline_version","verified_value","hypothetical_roi","policy","sources","ro_history","settlement"}
    if not isinstance(report,dict) or set(report)!=keys or report["schema_version"]!=1:raise ValueError("Invalid operations report")
    if report["verified_value"] is not False or report["hypothetical_roi"] is not None:raise ValueError("Operations report cannot confirm betting profit")
    for k in ("generated_at","analysis_generated_at"):
        if runner.timestamp(report[k]) is None:raise ValueError("Invalid operations timestamp")
    if runner.timestamp(report["generated_at"])<runner.timestamp(report["analysis_generated_at"]):raise ValueError("Operations report predates its analysis")
    if not isinstance(report["pipeline_version"],str) or not report["pipeline_version"]:raise ValueError("Operations report needs pipeline identity")
    policy={"model_expected_interval_hours":4,"model_warning_after_hours":6,"ro_expected_interval_hours":24,"ro_warning_after_hours":30}
    if report["policy"]!=policy:raise ValueError("Unexpected monitoring deadlines")
    sources=report["sources"]
    if not isinstance(sources,dict) or set(sources)!={"successful","total","failures"} or not count(sources["successful"]) or not count(sources["total"]) or not sources["successful"]<=sources["total"]:raise ValueError("Invalid operations source counts")
    if not isinstance(sources["failures"],list) or len(sources["failures"])!=sources["total"]-sources["successful"]:raise ValueError("Operations source failures disagree")
    for row in sources["failures"]:
        if not isinstance(row,dict) or set(row)!={"league","kind"} or row["league"] not in runner.LEAGUES or row["kind"] not in ("results","fixtures","historical"):raise ValueError("Unexpected failed source metadata")
    history=report["ro_history"]
    if not isinstance(history,dict) or set(history)!={"records","days_observed","last_observed_at"} or not count(history["records"]) or not count(history["days_observed"]) or not history["days_observed"]<=history["records"]<=MAX_RECORDS:raise ValueError("Invalid operations history counts")
    if history["last_observed_at"] is not None and runner.timestamp(history["last_observed_at"]) is None:raise ValueError("Invalid latest RO probe time")
    audit=report["settlement"]
    if not isinstance(audit,dict) or audit.get("verified_value") is not False or audit.get("operator_settlement_verified") is not False or audit.get("generated_at")!=report["analysis_generated_at"]:raise ValueError("Incoherent operations settlement audit")
    settlement.validate_report(audit,summary=True)


def validate_bundle(latest,log,audit,history,operations):
    settlement.validate_report(audit);validate_history(history);validate_operations(operations)
    if audit["generated_at"]!=latest["generated_at"] or operations["analysis_generated_at"]!=latest["generated_at"] or operations["pipeline_version"]!=latest["pipeline_version"]:raise ValueError("Monitoring reports belong to a different analysis")
    if audit["forecasts"]!=len(log):raise ValueError("Settlement audit does not cover the frozen journal")
    if operations["settlement"]!={k:v for k,v in audit.items() if k!="excluded_settled_ids"}:raise ValueError("Public settlement summaries disagree")
    records=history["records"]
    summary={"records":len(records),"days_observed":len({r["day_ro"] for r in records}),"last_observed_at":records[-1]["observed_at"] if records else None}
    if operations["ro_history"]!=summary:raise ValueError("Coverage history summary disagrees")
    eligible=settlement.eligible_forecasts(log,audit,latest["generated_at"])
    for market in (*runner.MARKETS,"h2h"):
        rows=[r for r in eligible if r["market"]==market]
        score=latest["prospective"][market]
        if score["n"]!=len(rows) or audit["by_market"].get(market,{}).get("settled_with_evidence",0)!=len(rows):raise ValueError("Prospective scores disagree with settlement eligibility")
        versions={r.get("pipeline_version","legacy_unversioned") for r in rows}
        if set(score["by_pipeline_version"])!=versions:raise ValueError("Missing prospective pipeline score grouping")
        for version,metrics in score["by_pipeline_version"].items():
            if metrics["n"]!=sum(r.get("pipeline_version","legacy_unversioned")==version for r in rows):raise ValueError("Prospective pipeline versions were mixed")
