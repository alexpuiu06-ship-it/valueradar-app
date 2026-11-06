#!/usr/bin/env python3
"""Validate generated dashboard contracts and preservation of frozen forecasts."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
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
    for path in args.docs.glob("*.json"):
        read(path)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"generated_at={data['generated_at']}\n")
    print(f"Output contracts passed: {counts[0]} fixtures, {counts[1]} forecasts; zero verified value; frozen journal preserved")


if __name__ == "__main__":
    main()
