#!/usr/bin/env python3
"""Save only owned generated outputs, refusing to overwrite a newer main branch.

All production workflows share one non-cancelling concurrency group. This check
also protects against a person pushing main while calculations are running.
There is deliberately no reset, force push, merge or stale-output retry.
"""
import argparse
import os
from pathlib import Path
import subprocess

OUTPUTS = {
    "refresh": (
        "docs/latest.json", "docs/forecast_log.json", "docs/odds_budget.json",
        "docs/odds_status.json", "docs/odds_watchlist.json",
        "docs/odds_observations.json", "docs/odds_diagnostics.json",
        "docs/market_audit.json", "docs/model_lab.json", "docs/calibration_report.json",
        "docs/elo_challenger.json", "docs/ro_feed_status.json",
        "docs/ro_feed_history.json", "docs/settlement_report.json", "docs/operations_report.json",
    ),
    "lab": ("docs/model_lab.json", "docs/calibration_report.json"),
    "elo": ("docs/elo_challenger.json",),
}
OPTIONAL_OUTPUTS = frozenset({"docs/ro_feed_status.json","docs/ro_feed_history.json","docs/settlement_report.json","docs/operations_report.json"})


def git(*args, capture=True):
    return subprocess.run(["git", *args], check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def publish(kind, expected_sha, output_file=None):
    if not expected_sha or git("rev-parse", "HEAD").strip() != expected_sha:
        raise RuntimeError("Working commit changed; refusing to publish stale generated outputs")
    if git("diff", "--cached", "--name-only").strip():
        raise RuntimeError("Unexpected staged changes; refusing to include them")
    git("fetch", "origin", "main", capture=False)
    if git("rev-parse", "FETCH_HEAD").strip() != expected_sha:
        raise RuntimeError("main advanced during calculation; rerun on current main instead of overwriting data")
    # Older checkouts and isolated test fixtures may predate optional monitors.
    # A tracked monitor deletion still fails the dirty-file guard below.
    paths = tuple(path for path in OUTPUTS[kind] if path not in OPTIONAL_OUTPUTS or Path(path).is_file())
    missing = [path for path in paths if not Path(path).is_file()]
    if missing:
        raise RuntimeError("Missing generated outputs: " + ", ".join(missing))
    # Other tracked modifications indicate a dirty or compromised calculation.
    changed = set(git("diff", "--name-only").splitlines())
    if changed - set(paths):
        raise RuntimeError("Unexpected tracked modifications outside the output allowlist")
    git("add", "--", *paths)
    if git("diff", "--cached", "--name-only").strip():
        git("-c", "user.name=valueradar-bot", "-c",
            "user.email=valueradar-bot@users.noreply.github.com", "commit", "-m",
            f"Refresh {kind} outputs [skip ci]", capture=False)
        # The normal fast-forward push rejects a race after the head check above.
        git("push", "origin", "HEAD:refs/heads/main", capture=False)
    saved_sha = git("rev-parse", "HEAD").strip()
    if output_file:
        with open(output_file, "a", encoding="utf-8") as stream:
            stream.write(f"saved_sha={saved_sha}\n")
    print("Saved generated output commit:", saved_sha)
    return saved_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=OUTPUTS)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        publish(args.kind, args.expected_sha, os.environ.get("GITHUB_OUTPUT"))
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
