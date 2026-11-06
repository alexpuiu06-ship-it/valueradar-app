#!/usr/bin/env python3
"""Validate generated dashboard contracts and preservation of frozen forecasts."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runner

SETTLEMENT_FIELDS = {"settled", "settled_at", "actual_outcome", "actual_over", "actual_total"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamp requires an explicit timezone")
    return parsed.astimezone(timezone.utc)


def probability(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def log_id(row):
    # Preserve the original identity strings as well as probabilities.
    return (*tuple(row.get(k) for k in ("league", "date", "home", "away", "market")),
            row.get("line") if row.get("market") != "h2h" else "h2h",
            row.get("pipeline_version", "legacy_unversioned"))


def validate_log(log, original=None):
    require(isinstance(log, list), "Forecast journal must be a list")
    current = {}
    for row in log:
        require(isinstance(row, dict), "Invalid journal record")
        key = log_id(row)
        require(None not in key[:5] and key not in current, "Duplicate or incomplete journal identity")
        current[key] = row
    canonical=[runner.forecast_identity(row) for row in log]
    require(len(set(canonical))==len(canonical), "Duplicate canonical forecast identity")
    old_keys = set()
    for before in original or []:
        key = log_id(before)
        require(key in current, "Previously frozen forecast was removed")
        old_keys.add(key)
        after = current[key]
        for field, value in before.items():
            if not before.get("settled") and field in SETTLEMENT_FIELDS:
                continue
            require(field in after and after[field] == value, "Previously frozen forecast was rewritten: " + field)
        require(not before.get("settled") or after.get("settled"), "Settlement cannot be undone")
    for key, row in current.items():
        if original is not None and key not in old_keys:
            require(row.get("kickoff_utc"), "New prospective forecast lacks a known kickoff")
            require(stamp(row["created_at"]) < stamp(row["kickoff_utc"]), "New forecast was not frozen before kickoff")


def validate_latest(data, now):
    require(isinstance(data, dict), "Latest snapshot must be an object")
    generated = stamp(data["generated_at"])
    require(now - timedelta(hours=12) <= generated <= now + timedelta(minutes=5), "Generated snapshot is stale or future dated")
    require(data.get("history_rows", 0) >= 100, "Insufficient real history")
    fixtures = data.get("fixtures")
    require(isinstance(fixtures, list) and fixtures, "No future fixtures")
    identities = set()
    predictions = 0
    for fixture in fixtures:
        identity = runner.key(fixture)
        require(identity not in identities, "Duplicate fixture in snapshot")
        identities.add(identity)
        require(runner.future_match(fixture, generated), "Snapshot includes a fixture already started at generation")
        require(runner.norm(fixture["home"]) != runner.norm(fixture["away"]), "Fixture plays against itself")
        for market, estimate in fixture.get("markets", {}).items():
            if estimate is None:
                continue
            require(probability(estimate.get("over")) and probability(estimate.get("under")), "Invalid total probability")
            require(abs(estimate["over"] + estimate["under"] - 1) <= 0.00002, "Unnormalized over/under")
            h2h = estimate.get("h2h")
            if h2h is not None:
                require(set(h2h) == {"home", "draw", "away"} and all(probability(v) for v in h2h.values()), "Invalid 1X2 distribution")
                require(abs(sum(h2h.values()) - 1) <= 0.00002, "Unnormalized 1X2")
            explanation = estimate.get("explanation")
            require(isinstance(explanation, dict), "Prediction lacks an arithmetic explanation")
            require(explanation.get("historical_cutoff_exclusive") == fixture["date"], "Prediction cutoff differs from fixture")
            latest = explanation.get("last_observation_date")
            if latest:
                require(latest < fixture["date"], "Training includes same-day or future outcomes")
            require(abs(explanation["predicted_home_mean"] + explanation["predicted_away_mean"] - explanation["predicted_total_mean"]) < 0.001,
                    "Explanation cannot reconstruct the predicted total")
            require(estimate.get("status") == "experimental", "Production estimate incorrectly promoted")
            predictions += 1
    require(predictions > 0, "No supported forecasts in snapshot")
    return len(fixtures), predictions


def validate_safety(watch, audit):
    require(isinstance(watch, dict) and watch.get("items") == [], "Unvalidated selections must never enter the watchlist")
    require(watch.get("live_ro_supported") is False, "RO provider support has not been evidenced")
    require(isinstance(audit, dict), "Market audit must be an object")
    require(audit.get("initial_positive_ev_signals", 0) == 0 and audit.get("signals_settled", 0) == 0,
            "Unvalidated odds must not produce confirmed signals")
    require(audit.get("hypothetical_roi") is None, "Unvalidated prices must not produce a profit claim")
    require(audit.get("model_is_verified") is False and audit.get("quotes_are_verified_romania") is False,
            "Evidence gate must remain closed")


def validate_ro_monitor(report):
    """A coverage observation has no capability to publish prices or unlock value."""
    top={"schema_version","provider","generated_at","max_quote_age_seconds","requested_books",
         "operator_prices_independently_verified","verified_value","raw_odds_saved",
         "authenticated_requests","source_run","leagues"}
    require(isinstance(report,dict) and not set(report)-top,"Unexpected RO monitor fields")
    require(report.get("schema_version")==1 and report.get("provider")=="PropLine","Unknown RO monitor schema")
    require(all(report.get(k) is False for k in ("verified_value","operator_prices_independently_verified","raw_odds_saved")),
            "RO monitor must remain aggregate and unverified")
    require(report.get("max_quote_age_seconds")==120,"RO acceptance age cannot be relaxed")
    books={"superbet_ro","netbet_ro"}
    require(report.get("requested_books")==["superbet_ro","netbet_ro"],"Unknown RO bookmaker scope")
    generated=stamp(report.get("generated_at"))
    require(generated<=datetime.now(timezone.utc)+timedelta(minutes=5),"Future RO observation")
    def count(value):return isinstance(value,int) and not isinstance(value,bool) and 0<=value<10**10
    requests=report.get("authenticated_requests")
    require(requests is None or count(requests) and requests<=5,"RO pass exceeds five requests")
    def counts(values,keys=None):
        require(isinstance(values,dict) and all(isinstance(k,str) and count(v) for k,v in values.items()),"Invalid RO counters")
        if keys is not None:require(not set(values)-keys,"Unknown RO counter key")
    rows=report.get("leagues")
    require(isinstance(rows,list) and len(rows)==5,"RO monitor requires all five league statuses")
    seen=set()
    for row in rows:
        allowed={"league","status","received_at","analysis_generated_at","requested_max_delivery_age_seconds","quality","quota","error"}
        require(isinstance(row,dict) and not set(row)-allowed,"Unexpected RO league fields")
        league=row.get("league")
        require(league in runner.LEAGUES and league not in seen,"Duplicate or unknown RO league")
        seen.add(league)
        require(row.get("requested_max_delivery_age_seconds") in (120,3600),"Unknown RO delivery filter")
        require(row.get("status") in {"diagnostic_only","incomplete_quote_validation","needs_api_key","provider_error",
                "stale_analysis","invalid_schema","diagnostic_error"},"Unknown RO diagnostic state")
        for field in ("received_at","analysis_generated_at"):
            if row.get(field) is not None:require(stamp(row[field])<=generated+timedelta(minutes=5),"Future RO source timestamp")
        if "error" in row:require(isinstance(row["error"],str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}",row["error"]),"Unsafe RO error text")
        counts(row.get("quota",{}),{"x-daily-limit","x-daily-used","x-daily-remaining"})
        quality=row.get("quality")
        if quality is None:continue
        quality_fields={"events_received","books_received","complete_recent_markets","matched_current_model_markets",
                        "book_diagnostics","rejection_counts","book_status_scope"}
        require(isinstance(quality,dict) and set(quality)==quality_fields,"RO report contains unsupported data")
        require(count(quality["events_received"]),"Invalid RO event count")
        for field in ("books_received","complete_recent_markets","matched_current_model_markets"):counts(quality[field],books)
        counts(quality["rejection_counts"])
        require(isinstance(quality["book_status_scope"],str),"Missing RO scope explanation")
        diagnostics=quality["book_diagnostics"]
        require(isinstance(diagnostics,dict) and set(diagnostics)==books,"Missing RO bookmaker diagnostics")
        for book,diag in diagnostics.items():
            require(isinstance(diag,dict) and set(diag)=={"status","received_blocks","complete_recent_markets","matched_current_model_markets","rejection_counts"},"Unexpected RO book fields")
            require(diag["status"] in {"absent","received_but_rejected","complete_markets_without_model_match","partially_matched","matched_current_model"},"Unknown RO book state")
            for field in ("received_blocks","complete_recent_markets","matched_current_model_markets"):require(count(diag[field]),"Invalid RO book count")
            require(diag["received_blocks"]==quality["books_received"].get(book,0) and
                    diag["complete_recent_markets"]==quality["complete_recent_markets"].get(book,0) and
                    diag["matched_current_model_markets"]==quality["matched_current_model_markets"].get(book,0),"Inconsistent RO counters")
            require(diag["matched_current_model_markets"]<=diag["complete_recent_markets"]<=diag["received_blocks"],"Impossible RO counts")
            counts(diag["rejection_counts"])


def read(path):
    def bad_constant(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=bad_constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    parser.add_argument("--original-log", type=Path)
    args = parser.parse_args()
    original = read(args.original_log) if args.original_log else None
    data = read(args.docs / "latest.json")
    counts = validate_latest(data, datetime.now(timezone.utc))
    validate_log(read(args.docs / "forecast_log.json"), original)
    validate_safety(read(args.docs / "odds_watchlist.json"), read(args.docs / "market_audit.json"))
    if (args.docs/"ro_feed_status.json").exists():validate_ro_monitor(read(args.docs/"ro_feed_status.json"))
    if data.get("pipeline_execution",{}).get("monitoring_schema_version")==1:
        import monitoring
        monitoring.validate_bundle(data,read(args.docs/"forecast_log.json"),read(args.docs/"settlement_report.json"),
          read(args.docs/"ro_feed_history.json"),read(args.docs/"operations_report.json"))
    for path in args.docs.glob("*.json"):
        read(path)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"generated_at={data['generated_at']}\n")
    print(f"Output contracts passed: {counts[0]} fixtures, {counts[1]} forecasts; zero verified value; frozen journal preserved")


if __name__ == "__main__":
    main()
