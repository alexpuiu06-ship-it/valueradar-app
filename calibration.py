#!/usr/bin/env python3
"""Reproducible chronological research; never promote a model or verify a bet.

The fixed protocol is an exploratory re-analysis of already inspected history,
not a claim that the historical holdout has never been inspected before.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import runner

OUT = Path(__file__).resolve().parent / "docs"
OUTCOMES = ("home", "draw", "away")
TEMPERATURES = (0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 1.8, 2.0)
ENSEMBLE_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
MIN_SELECTION = 30
BOOTSTRAP_SEED = 1729
BOOTSTRAP_REPEATS = 800
PROTOCOL_VERSION = "global_date_expanding_origin_v2"


def prepare_history(hist, as_of=None):
    """Reject invalid/future rows and quarantine conflicting duplicate events.

    Today's results are excluded because these sources lack a trustworthy result
    publication timestamp. Canonical IDs, not spelling, identify a match.
    """
    at = as_of or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("as_of must include timezone")
    today = at.astimezone(timezone.utc).date().isoformat()
    grouped = defaultdict(list)
    rejected = Counter()
    fields = tuple(c for value in runner.MARKETS.values() for c in value[:2])
    for raw in hist:
        if not isinstance(raw, dict):
            rejected["invalid_row"] += 1
            continue
        try:
            d = date.fromisoformat(raw["date"])
            if d.isoformat() != raw["date"] or raw["league"] not in runner.LEAGUES:
                raise ValueError("invalid date or league")
            if raw["date"] >= today:
                rejected["today_or_future_result"] += 1
                continue
            if not isinstance(raw["home"], str) or not isinstance(raw["away"], str):
                raise ValueError("Team identities must be strings")
            home, away = runner.norm(raw["home"]), runner.norm(raw["away"])
            if not home or not away or home == away:
                raise ValueError("invalid teams")
            row = {k: raw[k] for k in ("league", "date", "home", "away")}
            for field in fields:
                value = raw.get(field)
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("non-numeric statistic")
                if not math.isfinite(value) or value < 0 or not float(value).is_integer():
                    raise ValueError("invalid count")
                row[field] = int(value)
            if row.get("gh") is None or row.get("ga") is None:
                raise ValueError("missing result")
            grouped[runner.key(row)].append(row)
        except (KeyError, TypeError, ValueError):
            rejected["invalid_row"] += 1
    cleaned = []
    for event, copies in sorted(grouped.items()):
        if any(len({r[f] for r in copies if f in r}) > 1 for f in fields):
            rejected["conflicting_event"] += len(copies)
            continue
        merged = dict(min(copies, key=lambda r: (r["home"], r["away"])))
        for field in fields:
            values = [r[field] for r in copies if field in r]
            if values:
                merged[field] = values[0]
        rejected["duplicate_copy"] += len(copies) - 1
        cleaned.append(merged)
    cleaned.sort(key=lambda r: (r["date"], runner.key(r)))
    canonical = [{**r, "home": runner.norm(r["home"]), "away": runner.norm(r["away"])} for r in cleaned]
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return cleaned, {"input_rows": len(hist), "eligible_rows": len(cleaned),
                     "rejected": dict(rejected), "input_sha256": digest,
                     "as_of": at.isoformat(), "today_results_excluded": True}


def date_splits(rows):
    """One calendar boundary shared by all leagues; no date crosses a split."""
    days = sorted({r["date"] for r in rows})
    if len(days) < 5:
        return None
    indices = [int(len(days) * fraction) for fraction in (0.55, 0.70, 0.80)]
    if len(set(indices)) != 3 or min(indices) == 0:
        return None
    return dict(zip(("validation_start", "calibration_start", "holdout_start"),
                    (days[i] for i in indices)))


def split_for(day, boundaries):
    if not boundaries or day < boundaries["validation_start"]:
        return "training"
    if day < boundaries["calibration_start"]:
        return "validation"
    if day < boundaries["holdout_start"]:
        return "calibration"
    return "holdout"


def normalized(p):
    if not isinstance(p, dict) or set(p) != set(OUTCOMES):
        raise ValueError("Expected a complete 1X2 distribution")
    if any(isinstance(p[k], bool) or not isinstance(p[k], (int, float)) or
           not math.isfinite(p[k]) or p[k] < 0 or p[k] > 1 for k in OUTCOMES):
        raise ValueError("Invalid probability")
    total = sum(p.values())
    if not 0.999 <= total <= 1.001:
        raise ValueError("Probabilities must sum to one")
    return {k: p[k] / total for k in OUTCOMES}


def temperature_scale(p, temperature):
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("Temperature must be positive")
    p = normalized(p)
    logs = {k: math.log(max(1e-12, p[k])) / temperature for k in OUTCOMES}
    largest = max(logs.values())
    weights = {k: math.exp(v - largest) for k, v in logs.items()}
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def blend(poisson, elo, weight):
    if not 0 <= weight <= 1:
        raise ValueError("Invalid ensemble weight")
    a, b = normalized(poisson), normalized(elo)
    return {k: weight * a[k] + (1 - weight) * b[k] for k in OUTCOMES}


def logloss(p, y):
    return -math.log(max(1e-12, normalized(p)[y]))


def brier(p, y):
    p = normalized(p)
    return sum((p[k] - float(k == y)) ** 2 for k in OUTCOMES) / 3


def weekly_interval(points, repeats=BOOTSTRAP_REPEATS):
    """Paired cluster bootstrap: resample complete ISO weeks across all leagues."""
    weeks = defaultdict(list)
    for day, value in points:
        d = date.fromisoformat(day)
        weeks[d.isocalendar()[:2]].append(value)
    clusters = [(sum(v), len(v)) for _, v in sorted(weeks.items())]
    n = sum(v[1] for v in clusters)
    mean = sum(v[0] for v in clusters) / n if n else None
    interval = None
    if len(clusters) >= 4:
        rng = random.Random(BOOTSTRAP_SEED)
        samples = []
        for _ in range(repeats):
            draw = [clusters[rng.randrange(len(clusters))] for _ in clusters]
            samples.append(sum(v[0] for v in draw) / sum(v[1] for v in draw))
        samples.sort()
        interval = [round(samples[int(repeats * .025)], 6),
                    round(samples[min(repeats - 1, int(repeats * .975))], 6)]
    return {"n": n, "mean": round(mean, 6) if mean is not None else None,
            "approx_95_ci": interval, "blocks": len(clusters),
            "method": "paired_ISO_week_cluster_percentile_bootstrap",
            "resamples": repeats, "seed": BOOTSTRAP_SEED}


def wilson(successes, n):
    z = 1.96
    p = successes / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return [round(max(0, center-half), 5), round(min(1, center+half), 5)]


def summarize(records, name):
    """Scores on exactly the same events; classwise ECE uses disjoint bins."""
    losses = [(r["date"], logloss(r[name], r["y"])) for r in records]
    briers = [(r["date"], brier(r[name], r["y"])) for r in records]
    bins = []
    error = 0.
    for outcome in OUTCOMES:
        for index in range(5):
            group = [r for r in records if min(4, int(normalized(r[name])[outcome] * 5)) == index]
            if not group:
                continue
            predicted = sum(normalized(r[name])[outcome] for r in group) / len(group)
            successes = sum(r["y"] == outcome for r in group)
            observed = successes / len(group)
            error += len(group) * abs(predicted-observed)
            bins.append({"outcome": outcome, "range": f"{index*20}-{(index+1)*20}%",
                         "n": len(group), "predicted": round(predicted, 5),
                         "observed": round(observed, 5),
                         "observed_approx_95_wilson": wilson(successes, len(group))})
    ll, br = weekly_interval(losses), weekly_interval(briers)
    return {"n": len(records), "log_loss": ll["mean"], "brier": br["mean"],
            "log_loss_approx_95_range": ll["approx_95_ci"],
            "brier_approx_95_range": br["approx_95_ci"], "weeks": ll["blocks"],
            "ece": round(error / (3 * len(records)), 6) if records else None,
            "ece_definition": "equal_width_5_bins_classwise_mean_absolute_gap",
            "bins": bins}


def choose_temperature(records, name):
    if len(records) < MIN_SELECTION:
        return 1.0, "insufficient_calibration_examples_identity_retained"
    choices = [(sum(logloss(temperature_scale(r[name], t), r["y"]) for r in records) / len(records),
                abs(t-1), t) for t in TEMPERATURES]
    return min(choices)[2], "fit_on_calibration_window_only"


def protocol(rows, audit, boundaries):
    counts = Counter(split_for(r["date"], boundaries) for r in rows)
    return {"version": PROTOCOL_VERSION, "split_dates": boundaries,
            "counts_by_split": dict(counts), **audit,
            "model_pipeline_version": getattr(runner, "PIPELINE_VERSION", "legacy_unversioned"),
            "split_rule": "global unique dates: first 55% training, next 15% selection, next 10% calibration, last 20% evaluation",
            "features": "expanding origin; results strictly before each match date, same-day batch never updates before prediction",
            "selection": "Elo and ensemble weight on validation only; temperatures on later calibration only; holdout used for reporting only",
            "fixed_grids_before_run": {"temperature": list(TEMPERATURES), "poisson_weight": list(ENSEMBLE_WEIGHTS)},
            "registration": "fixed_exploratory_protocol_not_a_prospective_preregistration",
            "uncertainty": "ISO-week cluster bootstrap; bins show descriptive Wilson intervals assuming independent events",
            "holdout_warning": "History was already inspected in earlier research; this is an exploratory re-analysis, not a fresh confirmatory holdout."}


def aligned_market_baseline(records, observations, forecasts):
    """Only complete, aligned, genuinely pre-kickoff snapshots are scored.

    Legacy observations lack the required provenance and cannot be upgraded by
    guessing kickoff, publication time or settlement rules from the result.
    """
    def timestamp(value):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else None
        except (ValueError, TypeError):
            return None
    frozen_groups = defaultdict(list)
    settled_outcomes = defaultdict(set)
    for f in forecasts or []:
        if not isinstance(f, dict):
            continue
        try:
            created, kickoff = timestamp(f.get("created_at")), timestamp(f.get("kickoff_utc"))
            settled = timestamp(f.get("settled_at"))
            if f.get("market") == "h2h":
                version = f.get("pipeline_version", "legacy_unversioned")
                event = runner.key(f)
                frozen_groups[(event, version)].append((f, created, kickoff, settled))
                if f.get("settled") is True and f.get("actual_outcome") in OUTCOMES:
                    settled_outcomes[event].add(f["actual_outcome"])
        except (KeyError, TypeError):
            continue
    eligible = {}
    for event_version, copies in frozen_groups.items():
        # A duplicated journal event is ambiguous; do not choose the most convenient entry.
        if len(copies) != 1 or len(settled_outcomes[event_version[0]]) > 1:
            continue
        f, created, kickoff, settled = copies[0]
        if (f.get("settled") is True and f.get("actual_outcome") in OUTCOMES and
            created and kickoff and settled and created < kickoff <= settled):
            try:
                normalized(f.get("probabilities"))
            except (ValueError, TypeError):
                continue
            eligible[event_version] = f
    groups = defaultdict(dict)
    for o in observations or []:
        if not isinstance(o, dict):
            continue
        try:
            event = runner.key(o)
            version = o.get("model_pipeline_version")
            if not isinstance(version, str) or not version:
                continue
            event_version = (event, version)
            frozen = eligible.get(event_version)
            observed = timestamp(o.get("observed_at"))
            quote = timestamp(o.get("quote_timestamp") or o.get("source_updated_at"))
            kickoff = timestamp(o.get("commence_time") or o.get("kickoff_utc"))
            model_stamp = timestamp(o.get("model_generated_at"))
            rule = o.get("settlement_rule") or o.get("settlement_rules")
            provenance = tuple(o.get(k) for k in ("provider", "provider_event_id", "provider_region", "bookmaker_id", "settlement_evidence"))
            if (not frozen or not all((observed, quote, kickoff, model_stamp)) or
                any(not isinstance(v, str) or not v.strip() for v in provenance) or
                (o.get("market_key") or o.get("market")) != "h2h" or
                "line" not in o or o["line"] is not None or
                o.get("settlement_rules_status") != "verified" or rule != "90_minutes_plus_stoppage" or
                not isinstance(o.get("settlement_evidence"), str) or not o["settlement_evidence"].strip() or
                not quote <= observed < kickoff or (observed-quote).total_seconds() > 7200 or
                not model_stamp <= observed or
                timestamp(frozen["kickoff_utc"]) != kickoff or
                timestamp(frozen["created_at"]) > observed):
                continue
            price = float(o["odds"])
            if not math.isfinite(price) or price <= 1 or o.get("outcome") not in OUTCOMES:
                continue
            coherence = provenance + (quote.isoformat(), kickoff.isoformat(), model_stamp.isoformat(), rule)
            batch = (event_version, observed.isoformat(), coherence)
            if o["outcome"] in groups[batch]:
                groups[batch]["duplicate"] = True
            groups[batch][o["outcome"]] = price
        except (KeyError, TypeError, ValueError):
            continue
    byevent = defaultdict(list)
    for (event_version, observed, coherence), quotes in groups.items():
        if set(quotes) != set(OUTCOMES):
            continue
        total = sum(1/v for v in quotes.values())
        if 0.94 <= total <= 1.18:
            byevent[event_version].append((observed, coherence, {k: (1/v)/total for k, v in quotes.items()}))
    matched = []
    for r in records:
        event_version = (r["event"], r.get("pipeline_version"))
        if byevent.get(event_version) and eligible[event_version].get("actual_outcome") == r["y"]:
            # First complete observation and deterministic bookmaker, never best price after the result.
            market = min(byevent[event_version], key=lambda x: (x[0], x[1]))[2]
            frozen = normalized(eligible[event_version]["probabilities"])
            matched.append({**r, "market_no_vig": market, "frozen_model": frozen})
    return {"status": "available_descriptive_international_baseline" if matched else "unavailable",
            "n": len(matched),
            "reason": "No aligned complete pre-kickoff odds snapshots with verified settlement evidence and timestamped settled prospective forecasts from the same pipeline." if not matched else
                      "First complete aligned bookmaker snapshot; proportional no-vig normalization. Not fair-price truth or verified Romanian odds.",
            "scores": summarize(matched, "market_no_vig") if matched else None,
            "paired_frozen_model_scores": summarize(matched, "frozen_model") if matched else None,
            "recomputed_research_poisson_scores": summarize(matched, "poisson") if matched else None,
            "paired_model_definition": "Frozen probabilities from the matching pipeline journal, created no later than odds observation. Recomputed research probabilities are a separate replay score.",
            "verified_romania": False, "verified_value": False}


def compare_1x2(hist, fixtures=None, as_of=None, observations=None, forecasts=None):
    import elo_challenger as elo
    rows, audit = prepare_history(hist, as_of)
    boundaries = date_splits(rows)
    records = []
    for league in runner.LEAGUES:
        league_rows = [r for r in rows if r["league"] == league]
        histories = {name: elo.process(league_rows, params, as_of=as_of)[0] for name, params in elo.CANDIDATES.items()}
        for i, m in enumerate(league_rows):
            phase = split_for(m["date"], boundaries)
            if phase == "training":
                continue
            p = runner.pred(league_rows[:i], m, "goals")
            if not p or not p.get("h2h"):
                continue
            event = runner.key(m)
            if any(event not in h for h in histories.values()):
                continue
            older = [r for r in league_rows[:i] if r["date"] < m["date"]][-80:]
            counts = Counter({k: 3 for k in OUTCOMES})
            counts.update(elo.result(r["gh"], r["ga"]) for r in older)
            records.append({"event": event, "date": m["date"], "league": league,
                            "pipeline_version": getattr(runner, "PIPELINE_VERSION", "legacy_unversioned"),
                            "split": phase, "y": elo.result(m["gh"], m["ga"]),
                            "poisson": normalized(p["h2h"]),
                            "league_frequency": {k: counts[k]/sum(counts.values()) for k in OUTCOMES},
                            **{name: normalized(h[event]["p"]) for name, h in histories.items()}})
    validation = [r for r in records if r["split"] == "validation"]
    scores = {name: {"n": len(validation), "logloss": round(sum(logloss(r[name], r["y"]) for r in validation)/len(validation), 6) if validation else None}
              for name in elo.CANDIDATES}
    enough = len(validation) >= MIN_SELECTION
    winner = min(elo.CANDIDATES, key=lambda k: (sum(logloss(r[k], r["y"]) for r in validation), k)) if enough else "elo_balanced"
    for r in records:
        r["elo"] = r[winner]
    weight = min(ENSEMBLE_WEIGHTS, key=lambda w: (sum(logloss(blend(r["poisson"], r["elo"], w), r["y"]) for r in validation), abs(w-.5), w)) if enough else .5
    for r in records:
        r["ensemble"] = blend(r["poisson"], r["elo"], weight)
    cal = [r for r in records if r["split"] == "calibration"]
    temperatures, calibration_status = {}, {}
    for name in ("poisson", "elo", "ensemble"):
        temperatures[name], calibration_status[name] = choose_temperature(cal, name)
        for r in records:
            r[name + "_calibrated"] = temperature_scale(r[name], temperatures[name])
    test = [r for r in records if r["split"] == "holdout"]
    names = ("poisson", "elo", "ensemble", "poisson_calibrated", "elo_calibrated", "ensemble_calibrated", "league_frequency")
    by_league = {}
    for league in runner.LEAGUES:
        group = [r for r in test if r["league"] == league]
        gains = {name: weekly_interval([(r["date"], logloss(r["poisson"], r["y"])-logloss(r[name], r["y"])) for r in group]) for name in names if name != "poisson"}
        by_league[league] = {"n": len(group), "models": {name: summarize(group, name) for name in names}, "gains_vs_poisson": gains}
    gains = {}
    for name in names:
        if name == "poisson":
            continue
        g = weekly_interval([(r["date"], logloss(r["poisson"], r["y"])-logloss(r[name], r["y"])) for r in test])
        gains[name] = {**g, "mean_logloss_gain": g["mean"]}
    return {"generated_at": (as_of or datetime.now(timezone.utc)).isoformat(),
            "status": "RESEARCH_ONLY_NOT_PROMOTED", "protocol": protocol(rows, audit, boundaries),
            "common_support_counts": dict(Counter(r["split"] for r in records)),
            "selection_scores": scores,
            "selected": {"elo_candidate": winner, "ensemble_poisson_weight": weight,
                         "selection_status": "validation_only" if enough else "insufficient_validation_default_research_settings",
                         "temperatures": temperatures, "calibration_status": calibration_status},
            "holdout": {"n": len(test), "models": {name: summarize(test, name) for name in names},
                        "by_league": by_league, "gains_vs_poisson": gains},
            "market_baseline": aligned_market_baseline(test, observations, forecasts),
            "production_model_changed": False, "verified_value": False,
            "limitations": ["Retrospective source snapshots do not prove historical publication availability.",
                            "Previously inspected history cannot establish prospective superiority.",
                            "Week blocks capture same-week dependence, not all persistent team/season dependence.",
                            "Calibration-bin Wilson intervals assume independent events; they are descriptive, not per-match probability intervals.",
                            "No referee, confirmed lineup, injury or tactical variables; no validated ROI."]}


def run(snapshot=None):
    frozen = None
    if snapshot is not None:
        frozen = json.loads(Path(snapshot).read_text(encoding="utf-8"))
        if not isinstance(frozen, dict) or not isinstance(frozen.get("history"), list):
            raise SystemExit("Snapshot must contain a history list")
        hist = frozen["history"]
    else:
        hist, _, _ = runner.load_all()
    if len(hist) < 100:
        raise SystemExit("Insufficient real history; previous calibration report preserved")
    def read(name):
        try:
            value = json.loads((OUT/name).read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, ValueError):
            return []
    snapshot_at = datetime.fromisoformat(frozen["as_of"].replace("Z", "+00:00")) if frozen and frozen.get("as_of") else None
    report = compare_1x2(hist, as_of=snapshot_at,
                         observations=frozen.get("observations", []) if frozen is not None else read("odds_observations.json"),
                         forecasts=frozen.get("forecasts", []) if frozen is not None else read("forecast_log.json"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"calibration_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("Calibration research:", report["holdout"]["n"], "holdout matches; production model unchanged")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        assert abs(sum(temperature_scale({"home": .5, "draw": .25, "away": .25}, 1.3).values())-1) < 1e-12
        print("Calibration arithmetic tests passed")
    else:
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--snapshot", help="Offline JSON containing history, optional as_of/observations/forecasts")
        run(parser.parse_args().snapshot)
