#!/usr/bin/env python3
"""One-off runner for streak-spread-tight that reuses cached baseline results.

Run from repo root:
    python execution_algos/streak-spread-tight/run_backtest.py

Reads existing simple baseline metrics from disk (no re-run) and runs
streak-spread-tight via subprocess isolation for each train date in config.yaml.
Writes backtest-results.json and metadata.json to results/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_research_backtest import (  # noqa: E402
    run_one,
    aggregate,
    write_backtest_results,
    write_metadata,
    print_summary,
    train_dates_from_config,
    load_config,
    algo_results_dir,
)
from backtest_engine.backtest_low_level import EXECUTION_DIRS  # noqa: E402

ALGO_NAME = "streak-spread-tight"
DEFAULT_CONFIG = REPO_ROOT / "research" / "config.yaml"
DEFAULT_SYMBOL = "MESM6"


def load_baseline_metrics(baseline_name: str, dates: list[str]) -> dict[str, dict]:
    """Load existing baseline metrics from disk without re-running."""
    dir_name = EXECUTION_DIRS.get(baseline_name, baseline_name)
    base_results_root = REPO_ROOT / "execution_algos" / dir_name / "results"
    metrics_by_date: dict[str, dict] = {}
    for date in dates:
        run_dir = base_results_root / date
        metrics_file = run_dir / "metrics.json"
        if metrics_file.exists():
            m = json.loads(metrics_file.read_text())
            m["_run_dir"] = str(run_dir.relative_to(REPO_ROOT))
            m["_date"] = date
            metrics_by_date[date] = m
        else:
            print(f"  SKIP baseline {baseline_name} @ {date}: no metrics.json at {metrics_file}",
                  file=sys.stderr)
    return metrics_by_date


def main() -> int:
    cfg = load_config(DEFAULT_CONFIG)
    baseline = cfg["pass_gate"]["baseline"]
    dates = train_dates_from_config(cfg)
    symbol = DEFAULT_SYMBOL

    print(f"streak-spread-tight backtest runner (cached baseline mode)")
    print(f"  strategy: {cfg['strategy']['name']}")
    print(f"  baseline: {baseline} (cached from disk)")
    print(f"  dates   : {', '.join(dates)}")
    print()

    # Load existing baseline metrics
    print(f"Loading cached baseline metrics...")
    base_metrics = load_baseline_metrics(baseline, dates)
    print(f"  Found {len(base_metrics)}/{len(dates)} baseline date results on disk.")
    print()

    # Run algo for each train date
    algo_metrics: dict[str, dict] = {}
    failures: list[tuple[str, str]] = []

    for date in dates:
        print(f">>> run_backtest({ALGO_NAME}, {date}) ...", flush=True)
        try:
            m = run_one(
                algo_name=ALGO_NAME,
                date=date,
                symbol=symbol,
                config_path=DEFAULT_CONFIG,
            )
            algo_metrics[date] = m
            print(f"    OK   trades={m['trade_count']} pnl={m['realized_pnl']:.2f} "
                  f"sharpe={m['sharpe_ratio']:.2f} wr={m['win_rate']:.3f}")
        except Exception as exc:
            print(f"    FAIL {exc}", file=sys.stderr)
            failures.append((date, str(exc)))

    # Compute on comparable dates (both sides have data)
    comparable = sorted(set(algo_metrics) & set(base_metrics))
    dropped = sorted(set(dates) - set(comparable))
    if dropped:
        print(f"\nDropping {len(dropped)} date(s) (one side missing): {', '.join(dropped)}",
              file=sys.stderr)

    if not comparable:
        print("\nERROR: no comparable dates.", file=sys.stderr)
        return 1

    print(f"\nAggregating {len(comparable)} date(s): {', '.join(comparable)}")

    algo_agg = aggregate([algo_metrics[d] for d in comparable])
    base_agg = aggregate([base_metrics[d] for d in comparable])

    out_path = write_backtest_results(
        algo_name=ALGO_NAME,
        baseline_name=baseline,
        cfg=cfg,
        symbol=symbol,
        algo_agg=algo_agg,
        base_agg=base_agg,
        train_dates=comparable,
        run_dirs=[algo_metrics[d]["_run_dir"] for d in comparable],
    )
    print(f"Wrote: {out_path.relative_to(REPO_ROOT)}")

    meta_path = write_metadata(
        algo_name=ALGO_NAME,
        cfg=cfg,
        symbol=symbol,
        per_date_metrics=[algo_metrics[d] for d in comparable],
    )
    print(f"Wrote: {meta_path.relative_to(REPO_ROOT)}")

    print_summary(
        algo_name=ALGO_NAME,
        baseline_name=baseline,
        algo_agg=algo_agg,
        base_agg=base_agg,
        cfg=cfg,
    )

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
