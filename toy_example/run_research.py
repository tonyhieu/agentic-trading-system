"""Run a backtest using the full backtest_engine with local toy_example data.

Sets up symlinks so the two pre-cached .dbn.zst files in toy_example/data/
appear at the path backtest_engine/data_loader.py expects, then runs a
NautilusTrader backtest without touching S3.

Usage:
    python toy_example/run_research.py [--strategy ema_cross] [--date 20260406]

Results are appended to toy_example/research/program_database.json.
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TOY_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOY_DIR.parent
DATA_DIR = TOY_DIR / "data"
DATA_CACHE = TOY_DIR / "data-cache"
PROGRAM_DB = TOY_DIR / "research" / "program_database.json"

# Maps YYYYMMDD date -> local filename in toy_example/data/
LOCAL_FILES = {
    "20260406": "glbx-mdp3-20260406.mbp-1.dbn.zst",
    "20260407": "glbx-mdp3-20260407.mbp-1.dbn.zst",
}


def setup_local_cache() -> None:
    """Create symlinks so data_loader.py finds the files without S3."""
    for date, filename in LOCAL_FILES.items():
        dest = (
            DATA_CACHE
            / "glbx-mdp3-market-data"
            / "v1.0.0"
            / "partitions"
            / f"date={date}"
            / "data.dbn.zst"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.symlink_to(DATA_DIR / filename)
            print(f"Linked {filename} -> {dest.relative_to(REPO_ROOT)}")


def _sanitize(metrics: dict) -> dict:
    """Replace NaN/Inf floats with None so the dict is JSON-safe."""
    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    return {k: _clean(v) for k, v in metrics.items()}


def append_to_db(entry: dict) -> None:
    PROGRAM_DB.parent.mkdir(parents=True, exist_ok=True)
    if PROGRAM_DB.exists():
        db = json.loads(PROGRAM_DB.read_text())
    else:
        db = []
    db.append(entry)
    PROGRAM_DB.write_text(json.dumps(db, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run toy_example backtest locally")
    parser.add_argument("--strategy", default="ema_cross", help="Strategy name")
    parser.add_argument(
        "--date", default="20260406",
        choices=list(LOCAL_FILES),
        help="YYYYMMDD date to backtest",
    )
    args = parser.parse_args()

    setup_local_cache()

    # Point data_loader at the local cache — skips S3 when symlinks exist
    os.environ["DATA_CACHE_DIR"] = str(DATA_CACHE)

    sys.path.insert(0, str(REPO_ROOT))

    from backtest_engine.backtest_low_level import run_backtest
    from backtest_engine.benchmarks import compute_execution_benchmarks
    from backtest_engine.results import Reports, compute_metrics
    from nautilus_trader.model import Venue

    from toy_example.loader import load_ticks

    print(f"\nRunning backtest: strategy={args.strategy}  date={args.date}  symbol=GCM6")
    engine = run_backtest(
        strategy_name=args.strategy,
        execution_algorithm_name="simple",
        date=args.date,
        symbol="GCM6",
    )

    glbx = Venue("GLBX")
    reports = Reports(
        account=engine.trader.generate_account_report(glbx),
        orders=engine.trader.generate_orders_report(),
        fills=engine.trader.generate_order_fills_report(),
        positions=engine.trader.generate_positions_report(),
    )
    metrics = compute_metrics(reports, starting_balance=1_000_000.0)

    ticks_df = load_ticks(LOCAL_FILES[args.date])
    metrics.update(compute_execution_benchmarks(reports.positions, ticks_df))
    metrics = _sanitize(metrics)

    print("\nMetrics:")
    for k, v in metrics.items():
        print(f"  {k:<25}: {v}")

    entry = {
        "strategy": args.strategy,
        "date": args.date,
        "symbol": "GCM6",
        "metrics": metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    append_to_db(entry)
    print(f"\nLogged to {PROGRAM_DB.relative_to(REPO_ROOT)}")

    engine.dispose()


if __name__ == "__main__":
    main()
