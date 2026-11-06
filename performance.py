#!/usr/bin/env python3
"""Audit frozen quote observations; no profit until independent evidence exists."""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import odds_scanner
import runner
import settlement

OUT = Path(__file__).resolve().parent / "docs"


def read(name, default):
    try:
        return json.loads((OUT / name).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def key(value):
    identity = (value["league"], value["date"], runner.norm(value["home"]), runner.norm(value["away"]))
    hash(identity)  # Reject nested/unhashable identifiers from malformed JSON.
    return identity


def proper_scores(probabilities, outcome):
    return {
        "log_loss": -math.log(max(1e-8, probabilities[outcome])),
        "brier": sum((probabilities[k] - float(k == outcome)) ** 2 for k in odds_scanner.OUTCOMES) / 3,
    }


def evaluate(observations, forecast):
    """Compare complete first scans, while keeping all betting gates closed.

    Three input booleans cannot establish a local price, settlement contract,
    validated model, or positive lower confidence bound. No supported verification
    implementation currently exists, so simulated ROI is deliberately unavailable.
    """
    snapshots, reasons = odds_scanner.coherent_snapshots(observations)
    finished = {}
    actual_by_event = {}
    conflicting_results = set()
    conflicting_forecasts = set()
    for entry in forecast if isinstance(forecast, list) else []:
        if not isinstance(entry, dict) or entry.get("market") != "h2h" or entry.get("settled") is not True:
            continue
        actual = entry.get("actual_outcome")
        if actual not in odds_scanner.OUTCOMES:
            continue
        try:
            event = key(entry)
        except (KeyError, TypeError):
            continue
        if event in actual_by_event and actual_by_event[event] != actual:
            conflicting_results.add(event)
            reasons["conflicting_settlement"] += 1
        actual_by_event[event] = actual
        pipeline = entry.get("pipeline_version", "legacy_unversioned")
        if not isinstance(pipeline, str):
            continue
        identity = (event, pipeline)
        if identity in conflicting_forecasts:
            continue
        if identity in finished and finished[identity] != entry:
            # A first prediction within one pipeline must be immutable. Separate
            # pipeline versions are legitimate and never replace one another.
            reasons["conflicting_forecast_within_pipeline"] += 1
            conflicting_forecasts.add(identity)
            finished[identity] = None
        else:
            finished[identity] = entry
    unverified_events = set()
    scored = []
    all_observations = sum(len(rows) for scans in snapshots.values() for books in scans.values() for rows in books.values())
    evaluation_scans = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for event, scans in snapshots.items():
        for stamp, books in scans.items():
            for book, rows in books.items():
                for row in rows:
                    pipeline = row.get("model_pipeline_version")
                    evaluation_scans[(event, pipeline)][stamp][book].append(row)
    for (event, _pipeline), scans in evaluation_scans.items():
        first = min(scans)
        first_batch = [row for rows in scans[first].values() for row in rows]
        raw_flags = [row for row in first_batch
                     if odds_scanner.finite_number(row.get("estimated_ev"), .05, 1000)
                     and row.get("model_low_sample") is False]
        if raw_flags:
            unverified_events.add(event)
        # Observational market benchmark, independent of any betting gate.
        consensus = odds_scanner.cross_book_consensus(first_batch)
        if not consensus["items"]:
            reasons["first_scan_without_complete_consensus"] += 1
            continue
        pipelines = {row.get("model_pipeline_version") for row in first_batch}
        if len(pipelines) != 1 or None in pipelines:
            reasons["missing_or_mixed_model_pipeline_version"] += 1
            continue
        pipeline = next(iter(pipelines))
        settled = finished.get((event, pipeline))
        if not settled or event in conflicting_results:
            reasons["no_unambiguous_prospective_result_for_pipeline"] += 1
            continue
        # Old observations cannot acquire kickoff/rule provenance from later
        # results. The paired model score comes from the frozen journal entry,
        # never a reconstructed current forecast or a newer quote-model version.
        frozen_probs = settled.get("probabilities")
        if not odds_scanner.valid_probabilities(frozen_probs):
            reasons["invalid_frozen_probabilities"] += 1
            continue
        created = odds_scanner.dt(settled.get("created_at"))
        settled_at = odds_scanner.dt(settled.get("settled_at"))
        frozen_start = odds_scanner.dt(settled.get("kickoff_utc"))
        starts = {odds_scanner.dt(row.get("commence_time")) for row in first_batch}
        model_dates = {odds_scanner.dt(row.get("model_generated_at")) for row in first_batch}
        quote_dates = [odds_scanner.dt(row.get("quote_timestamp")) for row in first_batch]
        if (len(starts) != 1 or None in starts or len(model_dates) != 1 or None in model_dates
                or any(value is None for value in quote_dates)):
            reasons["missing_pre_match_provenance"] += 1
            continue
        start, model_date = next(iter(starts)), next(iter(model_dates))
        if not (created and settled_at and frozen_start == start and created <= first < start <= settled_at
                and model_date <= first and runner.prospective_eligible(settled)):
            reasons["non_prospective_or_mismatched_timestamps"] += 1
            continue
        if not all(row.get("settlement_rules_status") == "verified"
                   and (row.get("settlement_rule") or row.get("settlement_rules")) == "90_minutes_plus_stoppage"
                   and isinstance(row.get("settlement_evidence"), str) and row["settlement_evidence"].strip()
                   for row in first_batch):
            reasons["settlement_rules_not_verified"] += 1
            continue
        diagnostic = consensus["items"][0]
        market = diagnostic["market_consensus_no_vig"]
        actual = settled["actual_outcome"]
        scored.append((proper_scores(frozen_probs, actual), proper_scores(market, actual), pipeline))
    n = len(scored)
    def summarize(points):
        count = len(points)
        return {"n": count,
                "model_log_loss": round(sum(model["log_loss"] for model, market, pipeline in points) / count, 5) if count else None,
                "market_log_loss": round(sum(market["log_loss"] for model, market, pipeline in points) / count, 5) if count else None,
                "model_brier": round(sum(model["brier"] for model, market, pipeline in points) / count, 5) if count else None,
                "market_brier": round(sum(market["brier"] for model, market, pipeline in points) / count, 5) if count else None}
    versions = sorted({pipeline for _, _, pipeline in scored})
    benchmark = {
        "status": "multiple_pipeline_versions_separate" if len(versions) > 1 else "observational_international_only" if n else "insufficient_provenance_or_results",
        "selection": "first stored scan per event; at least 3 complete distinct bookmaker IDs; median no-vig; same verified settlement rule",
        "model_score_source": "immutable prospective journal probabilities from matching pipeline_version",
        **summarize(scored if len(versions) <= 1 else []),
        "n": n,
        "by_pipeline_version": {pipeline: summarize([row for row in scored if row[2] == pipeline]) for pipeline in versions},
        "mixed_versions_pooled": False,
        "notice": "International quoted snapshots are not executable RO prices; source rules and bookmaker independence remain unverified.",
    }
    return {
        "status": "paper_only_not_validated", "observations": all_observations,
        "distinct_events": len(snapshots), "unverified_model_price_differences": len(unverified_events),
        "initial_positive_ev_signals": 0, "signals_settled": 0,
        "hypothetical_roi": None, "approx_95_roi_interval": None,
        "mean_price_change_vs_last_seen": None, "price_change_count": 0,
        "model_is_verified": False, "quotes_are_verified_romania": False,
        "value_blockers": odds_scanner.value_blockers(), "rejection_counts": dict(reasons),
        "market_baseline": benchmark,
        "notice": "Nu există pariuri value verificate. Diferențele de preț sunt diagnostice; ROI este indisponibil fără dovezi independente.",
    }


def selftest():
    event = {"league": "Premier League", "date": "2026-11-07", "home": "Arsenal", "away": "Chelsea"}
    # Even forged verification flags must not turn an observation into profit.
    observation = {**event, "outcome": "home", "bookmaker_id": "test", "odds": 2.1,
                   "estimated_ev": .08, "model_probability": .51, "model_low_sample": False,
                   "observed_at": "2026-11-06T15:00:00Z", "verified_ro_offer": True,
                   "ready_to_bet": True, "model_is_validated": True}
    completed = {**event, "market": "h2h", "settled": True, "actual_outcome": "home"}
    result = evaluate([observation], [completed])
    assert result["signals_settled"] == 0 and result["hypothetical_roi"] is None
    assert result["unverified_model_price_differences"] == 1
    print("Paper-tracking tests passed")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    observations = read("odds_observations.json", [])
    latest=read("latest.json",{})
    forecasts=settlement.eligible_forecasts(read("forecast_log.json",[]),read("settlement_report.json",{}),latest.get("generated_at"))
    result = evaluate(observations, forecasts)
    # A cache refresh never advances the original observation timestamp.
    audit = odds_scanner.cross_book_consensus(observations)
    diagnostic = {
        "source": "stored_derived_observations",
        "note": "Historical snapshots; refreshing this audit does not refresh the quotes.",
        **audit,
    }
    (OUT / "odds_diagnostics.json").write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (OUT / "market_audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print("Market audit:", result["observations"], "observations,", result["signals_settled"], "verified signals")


if __name__ == "__main__":
    selftest() if "--self-test" in sys.argv else run()
