#!/usr/bin/env python3
"""
Out-of-sample (OOS) evaluation runner — SAFE, non-destructive.
Runs algo + baseline over the TEST window and writes oos-results/<algo>.json.
Does NOT touch execution_algos/<algo>/results/backtest-results.json.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_research_backtest import (
    run_one, aggregate, safe_pct_delta, load_config, DEFAULT_CONFIG, DEFAULT_SYMBOL,
)

PERF_KEYS = (
    "realized_pnl", "unrealized_pnl", "sharpe_ratio", "sharpe_n_days",
    "max_drawdown_pct", "win_rate", "trade_count", "mean_slippage",
    "max_abs_slippage", "total_commissions", "total_return_pct",
    "is_weighted_bps", "is_total_price",
)

def test_dates_from_config(cfg):
    import pandas as pd
    start, end = cfg["data_window"]["test"]
    days = pd.date_range(start, end, freq="D")
    days = days[days.dayofweek != 5]
    return days.strftime("%Y%m%d").tolist()

def build_performance_block(algo_agg, base_agg):
    perf = {k: algo_agg[k] for k in PERF_KEYS}
    algo_total = algo_agg["realized_pnl"] + algo_agg["unrealized_pnl"]
    base_total = base_agg["realized_pnl"] + base_agg["unrealized_pnl"]
    perf["vs_baseline_pnl_pct"] = safe_pct_delta(algo_total, base_total)
    perf["vs_baseline_slippage_pct"] = safe_pct_delta(algo_agg["mean_slippage"], base_agg["mean_slippage"])
    if algo_agg["is_weighted_bps"] is not None and base_agg["is_weighted_bps"] is not None:
        perf["vs_baseline_is_bps"] = safe_pct_delta(algo_agg["is_weighted_bps"], base_agg["is_weighted_bps"])
    else:
        perf["vs_baseline_is_bps"] = None
    return perf

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--algo", required=True)
    p.add_argument("--baseline", default="simple")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    p.add_argument("--dates")
    p.add_argument("--out-dir", type=Path, default=REPO_ROOT / "oos-results")
    return p.parse_args()

def main():
    args = parse_args()
    cfg = load_config(args.config)
    dates = [d.strip() for d in args.dates.split(",") if d.strip()] if args.dates else test_dates_from_config(cfg)
    print(f"OOS eval: algo={args.algo} baseline={args.baseline} symbol={args.symbol}")
    print(f"Test dates ({len(dates)}): {', '.join(dates)}")
    print(f"Output: {args.out_dir / (args.algo + '.json')}")
    print("NOTE: this does NOT modify any backtest-results.json.\n")
    algo_metrics, base_metrics, failures = {}, {}, []
    for date in dates:
        print(f">>> {args.algo} @ {date} ...", flush=True)
        try:
            m = run_one(algo_name=args.algo, date=date, symbol=args.symbol, config_path=args.config)
            algo_metrics[date] = m
            print(f"    OK   trades={m['trade_count']} pnl={m['realized_pnl']:.2f}")
        except Exception as exc:
            print(f"    FAIL {exc}", file=sys.stderr); failures.append((args.algo, date, str(exc)))
        print(f">>> {args.baseline} @ {date} ...", flush=True)
        try:
            m = run_one(algo_name=args.baseline, date=date, symbol=args.symbol, config_path=args.config)
            base_metrics[date] = m
            print(f"    OK   trades={m['trade_count']} pnl={m['realized_pnl']:.2f}")
        except Exception as exc:
            print(f"    FAIL {exc}", file=sys.stderr); failures.append((args.baseline, date, str(exc)))
    if failures:
        print(f"\n{len(failures)} run(s) failed:", file=sys.stderr)
        for a, d, e in failures: print(f"  - {a} @ {d}: {e}", file=sys.stderr)
    comparable = sorted(set(algo_metrics) & set(base_metrics))
    dropped = sorted(set(dates) - set(comparable))
    if dropped:
        print(f"\n⚠ Dropping {len(dropped)} date(s): {', '.join(dropped)}", file=sys.stderr)
    if not comparable:
        print("\nERROR: no comparable dates — nothing written.", file=sys.stderr); return 2
    algo_agg = aggregate([algo_metrics[d] for d in comparable])
    base_agg = aggregate([base_metrics[d] for d in comparable])
    perf_oos = build_performance_block(algo_agg, base_agg)
    payload = {
        "algo_name": args.algo, "evaluation_type": "oos_local",
        "backtest_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline": args.baseline, "sharpe_metric_version": "v2",
        "strategy_used": cfg["strategy"]["name"], "symbol": args.symbol,
        "performance_oos": perf_oos,
        "period": {"test_dates": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in comparable]},
        "run_dirs": [algo_metrics[d]["_run_dir"] for d in comparable],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.algo}.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote: {out_path}")
    print(f"  realized_pnl        : {perf_oos['realized_pnl']:.2f}")
    print(f"  sharpe_ratio        : {perf_oos['sharpe_ratio']:.4f}")
    print(f"  win_rate            : {perf_oos['win_rate']:.4f}")
    print(f"  trade_count         : {perf_oos['trade_count']}")
    print(f"  vs_baseline_pnl_pct : {perf_oos['vs_baseline_pnl_pct']:.2f}")
    print(f"  dates used          : {len(comparable)} of {len(dates)}")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
