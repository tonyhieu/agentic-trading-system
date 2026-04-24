"""Toy end-to-end run: noisy oracle signal on GCM6 tick data.

Day 1 (2026-04-06): training
Day 2 (2026-04-07): validation

Usage:
    python toy_example/run.py [--k 20] [--noise 0.3]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loader import load_ticks, TRAIN_FILE, VAL_FILE
from strategy import noisy_oracle
from backtester import run


def report(label: str, results: dict) -> None:
    print(f"\n{'='*45}")
    print(f"  {label}")
    print(f"{'='*45}")
    if results.get("total_trades", 0) == 0:
        print("  No trades generated.")
        return
    col_w = 18
    for key, val in results.items():
        print(f"  {key:<{col_w}}: {val}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k",     type=int,   default=20,  help="lookahead ticks")
    parser.add_argument("--noise", type=float, default=0.3, help="noise std dev (0=perfect oracle)")
    args = parser.parse_args()

    print(f"Parameters: k={args.k}, noise_std={args.noise}")

    print("\nLoading data...")
    train_df = load_ticks(TRAIN_FILE)
    val_df   = load_ticks(VAL_FILE)
    print(f"  Train ticks : {len(train_df):>10,}  ({TRAIN_FILE.split('-')[2]})")
    print(f"  Val ticks   : {len(val_df):>10,}  ({VAL_FILE.split('-')[2]})")

    print("\nComputing signals...")
    train_sig = noisy_oracle(train_df, k=args.k, noise_std=args.noise, seed=42)
    val_sig   = noisy_oracle(val_df,   k=args.k, noise_std=args.noise, seed=99)

    print("Running backtests...")
    train_res = run(train_df, train_sig, k=args.k)
    val_res   = run(val_df,   val_sig,   k=args.k)

    report("TRAIN  — 2026-04-06", train_res)
    report("VALIDATE — 2026-04-07", val_res)

    print()
    if val_res.get("total_trades", 0) > 0:
        twap_pass = val_res["vs_twap_pct"] >= 10
        vwap_pass = val_res["vs_vwap_pct"] >= 10
        status = "PASS" if (twap_pass and vwap_pass) else "FAIL"
        print(f"Gate check (validation): {status}  "
              f"(vs TWAP {val_res['vs_twap_pct']:+.1f}%  vs VWAP {val_res['vs_vwap_pct']:+.1f}%)")


if __name__ == "__main__":
    main()
