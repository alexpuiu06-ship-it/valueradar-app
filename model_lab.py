#!/usr/bin/env python3
"""Fixed chronological model ablations. No automatic model promotion."""
from __future__ import annotations
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import calibration
import runner

OUT = Path(__file__).resolve().parent / "docs"
VARIANTS = {
    "current_v1": {"half_life_days": 185, "prior_weight": 7, "opponent_effect": True},
    "recent_90d": {"half_life_days": 90, "prior_weight": 7, "opponent_effect": True},
    "regularized_15": {"half_life_days": 185, "prior_weight": 15, "opponent_effect": True},
    "team_only": {"half_life_days": 185, "prior_weight": 7, "opponent_effect": False},
}
MARKETS = ["h2h", "yellow", "corners", "goals", "fouls"]


def brier(probs, y):
    if isinstance(probs, dict):
        return calibration.brier(probs, y)
    return (probs-y)**2


def logloss(probs, y):
    if isinstance(probs, dict):
        return calibration.logloss(probs, y)
    p = probs if y else 1-probs
    return -math.log(max(1e-12, min(1, p)))


def actual(match, market):
    if market == "h2h":
        return "home" if match["gh"] > match["ga"] else "away" if match["gh"] < match["ga"] else "draw"
    h, a, limit, _ = runner.MARKETS[market]
    return int(match[h]+match[a] > limit)


def main_probs(prediction, market):
    return prediction.get("h2h") if market == "h2h" else prediction.get("over")


def summarize(records, name, market):
    if market == "h2h":
        return calibration.summarize(records, name)
    losses = calibration.weekly_interval([(r["date"], logloss(r[name], r["y"])) for r in records])
    errors = calibration.weekly_interval([(r["date"], brier(r[name], r["y"])) for r in records])
    bins = []
    ece = 0.
    for index in range(5):
        group = [r for r in records if min(4, int(r[name]*5)) == index]
        if not group:
            continue
        p = sum(r[name] for r in group)/len(group)
        y = sum(r["y"] for r in group)/len(group)
        ece += len(group)*abs(p-y)
        bins.append({"range": f"{index*20}-{(index+1)*20}%", "n": len(group),
                     "predicted": round(p, 5), "observed": round(y, 5),
                     "observed_approx_95_wilson": calibration.wilson(sum(r["y"] for r in group), len(group))})
    return {"n": len(records), "brier": errors["mean"], "log_loss": losses["mean"],
            "brier_approx_95_range": errors["approx_95_ci"],
            "log_loss_approx_95_range": losses["approx_95_ci"],
            "ece": round(ece/len(records), 6) if records else None, "bins": bins,
            "weeks": losses["blocks"]}


def experiment(hist, as_of=None):
    hist, audit = calibration.prepare_history(hist, as_of)
    output = {"generated_at": (as_of or datetime.now(timezone.utc)).isoformat(),
              "status": "research_only_no_model_promoted",
              "model_selection": "validation log-loss only; calibration period unused for ablation selection; final period exploratory",
              "variants": VARIANTS, "markets": {}, "input_audit": audit,
              "production_model_changed": False}
    cache = {}
    for market in MARKETS:
        base_market = "goals" if market == "h2h" else market
        h, a, _, _ = runner.MARKETS[base_market]
        available = [r for r in hist if r.get(h) is not None and r.get(a) is not None]
        boundaries = calibration.date_splits(available)
        records = []
        availability = {}
        for league in runner.LEAGUES:
            rows = [r for r in available if r["league"] == league]
            availability[league] = len(rows)
            for i, m in enumerate(rows):
                phase = calibration.split_for(m["date"], boundaries)
                if phase not in ("validation", "holdout"):
                    continue
                predictions = {}
                for name, params in VARIANTS.items():
                    k = (base_market, runner.key(m), name)
                    if k not in cache:
                        prediction = runner.pred(rows[:i], m, base_market, **params)
                        cache[k] = {"h2h": prediction.get("h2h"), "over": prediction.get("over")} if prediction else None
                    prediction = cache[k]
                    predictions[name] = main_probs(prediction, market) if prediction else None
                if any(p is None for p in predictions.values()):
                    continue
                records.append({"date": m["date"], "league": league, "split": phase,
                                "y": actual(m, market), **predictions})
        validation = [r for r in records if r["split"] == "validation"]
        test = [r for r in records if r["split"] == "holdout"]
        # Selection uses full precision; rounded display metrics never choose a model.
        chosen = min(VARIANTS, key=lambda name: (sum(logloss(r[name], r["y"]) for r in validation), name)) if len(validation) >= calibration.MIN_SELECTION else None
        def gains(group):
            points = [(r["date"], logloss(r["current_v1"], r["y"])-logloss(r[chosen], r["y"])) for r in group] if chosen else []
            value = calibration.weekly_interval(points)
            return {"n": value["n"], "mean_logloss_gain": value["mean"],
                    "approx_95_ci": value["approx_95_ci"], "weeks": value["blocks"]}
        gain = gains(test)
        league_gains = {league: gains([r for r in test if r["league"] == league]) for league in runner.LEAGUES}
        output["markets"][market] = {
            "historical_examples": availability, "selected_on_validation": chosen,
            "protocol": calibration.protocol(available, audit, boundaries),
            "common_support_counts": dict(Counter(r["split"] for r in records)),
            "validation": {name: summarize(validation, name, market) for name in VARIANTS},
            "holdout": {name: summarize(test, name, market) for name in VARIANTS},
            "holdout_logloss_gain_vs_current": gain["mean_logloss_gain"],
            "holdout_approx_95_gain_interval": gain["approx_95_ci"],
            "holdout_gain_by_league": league_gains,
            "holdout_by_league": {league: {name: summarize([r for r in test if r["league"] == league], name, market) for name in VARIANTS} for league in runner.LEAGUES},
            "approval": "NOT_APPROVED_no_prospective_validation",
            "interval_method": "paired_ISO_week_cluster_percentile_bootstrap",
            "note": "Common calendar boundaries across leagues. Historically inspected data are exploratory; small statistical markets may have no eligible selection sample. No betting ROI.",
        }
    return output


def selftest():
    assert abs(brier(.7, 1)-.09) < 1e-9
    assert brier({"home": 1., "draw": 0., "away": 0.}, "home") == 0
    assert logloss(.7, 1) > 0
    hist = []
    from datetime import date, timedelta
    for i in range(160):
        hist.append({"league": "Ligue 1", "date": (date(2026, 1, 1)+timedelta(days=i)).isoformat(),
                     "home": "A", "away": "B", "gh": 2., "ga": 1., "yh": 2., "ya": 2.,
                     "ch": 5., "ca": 4., "fh": 14., "fa": 9.})
    x = experiment(hist)
    assert set(x["markets"]) == set(MARKETS)
    assert x["markets"]["h2h"]["approval"].startswith("NOT_APPROVED")
    assert "holdout_approx_95_gain_interval" in x["markets"]["h2h"]
    print("Model lab tests passed")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    hist, _, _ = runner.load_all()
    if len(hist) < 100:
        raise SystemExit("Insufficient real history: preserve last model lab report")
    result = experiment(hist)
    (OUT/"model_lab.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")
    print("Evaluated:", {m: (r["selected_on_validation"], r["holdout"].get("current_v1", {}).get("n", 0)) for m, r in result["markets"].items()})


if __name__ == "__main__":
    selftest() if "--self-test" in sys.argv else run()
