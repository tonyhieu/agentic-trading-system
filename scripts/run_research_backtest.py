#!/usr/bin/env python3
"""
Research-loop paired backtest runner.
 
Runs an execution algorithm against the configured baseline on every date
in `research/config.yaml -> data_window.train`, then aggregates per-date
`metrics.json` files into a single `backtest-results.json` per the schema
in `.claude/skills/snapshot/SKILL.md` section 3.
 
This script is the canonical entry point for the local train-window phase
of the research loop. It replaces the inline loop pattern that agents
previously regenerated in their context every iteration (see the original
SKILL.md backtest section 7).
 
Design notes:
  - SUBPROCESS ISOLATION: each backtest runs in a fresh `python` process,
    bypassing the Nautilus single-process native-mem abort documented in
    research/suggested_improvements.md P0 #4 and log.md OBSERVATIONS #2.
    A single invocation can now safely chain algo + baseline across many
    dates.
 
Known limitations (not addressed here):
  - Baseline runs re-execute every invocation (no caching keyed on
    date + strategy_kwargs hash). Optimization for a follow-up if it
    starts hurting iteration speed.
  - program_database entries don't carry a strategy_kwargs hash, so
    silent config changes (e.g. sigma=0.5 -> 5) aren't auto-detected.
    Better solved at the database-write layer than here.
  - Nautilus stderr still ~15 MB per run. Better solved by adjusting
    Nautilus log level in backtest_engine/, not in this script.

Usage:
    python scripts/run_research_backtest.py --algo my-new-algo
    python scripts/run_research_backtest.py --algo my-new-algo --dry-run
    python scripts/run_research_backtest.py --baseline-only
    python scripts/run_research_backtest.py --algo my-new-algo \\
        --dates 20260308,20260309 --symbol MESM6

Exit codes:
    0  all runs succeeded, results written
    1  one or more runs failed (or no comparable date pairs)
    2  CLI / config error before any backtest started
"""
 

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
try:
    import resource  # Unix-only; not available on native Windows.
except ImportError:  # pragma: no cover - Windows-only branch
    resource = None  # type: ignore[assignment]
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

# Resolve repo root regardless of cwd, so the script works from any directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backtest_engine.backtest_low_level import (  # noqa: E402
    EXECUTION_DIRS,
    STARTING_BALANCE_USD,
    run_backtest,
)

DEFAULT_CONFIG = REPO_ROOT / "research" / "config.yaml"
DEFAULT_SYMBOL = "MESM6"

# Per-backtest timeout for subprocess isolation. A 1-day backtest should
# complete in well under 60s; this is a sanity ceiling, not a normal-case
# limit. If you regularly bump this, something else is wrong.
#
# Lowered from 600s to 180s as part of issue #61. The original 600s
# existed primarily to absorb the memory-pressure tail when a Nautilus
# engine pushed past available RAM and the OS started thrashing — a
# wedged subprocess could stall for many minutes before either crashing
# or finishing. With the RLIMIT_AS memory cap also added under #61, the
# memory-pressure failure mode now raises MemoryError in seconds, so
# the tail no longer exists and 180s gives ample headroom over the
# ~27s observed for the simple baseline on the busiest cached day.
SUBPROCESS_TIMEOUT_SEC = 1200

# Per-backtest virtual-memory ceiling for the --internal-single-run child.
# Nautilus holds all order/fill/position objects in engine.trader caches
# until reports are generated at end; a busy day on a non-skip algo can
# push RSS past 10 GB (~9.5 GB measured for the simple baseline on
# 20260312). On a 16 GB / 0 swap host that's right at the OOM edge, and
# the allocator stalls under pressure make the subprocess timeout look
# like a hang. With this cap, the child raises MemoryError quickly
# instead of thrashing the OS — turns the failure mode from "wedge for
# minutes" into "fail in seconds." Override with RESEARCH_MEM_CAP_GB=0
# to disable. Enforced via RLIMIT_AS — works on Linux (the agent-loop
# host); macOS treats it as advisory and the setrlimit call may return
# EINVAL, in which case we log a warning and continue uncapped.
MEMORY_CAP_GB_DEFAULT = 16

# Magic prefix on the child's stdout line carrying the result payload.
# Anything goes after this prefix as long as it's a single line of JSON.
METRICS_MARKER = "__METRICS_JSON__"


def _apply_memory_cap() -> None:
    """Set RLIMIT_AS for the current process to bound peak memory.

    No-op when RESEARCH_MEM_CAP_GB=0 or when the platform refuses the
    setrlimit call (e.g. unprivileged WSL). Failures are non-fatal — we
    log a warning to stderr and continue; the original failure mode
    (OS-level memory pressure) is no worse than not having the cap.
    """
    try:
        cap_gb = float(os.environ.get("RESEARCH_MEM_CAP_GB", MEMORY_CAP_GB_DEFAULT))
    except ValueError:
        print(
            f"WARN: RESEARCH_MEM_CAP_GB={os.environ.get('RESEARCH_MEM_CAP_GB')!r} "
            f"is not a number; ignoring",
            file=sys.stderr,
        )
        return
    if cap_gb <= 0:
        return
    if resource is None:
        # Windows: no RLIMIT_AS available. Skip silently — original failure
        # mode (OS-level memory pressure) is no worse than not having the cap.
        return
    cap_bytes = int(cap_gb * 1024 * 1024 * 1024)
    try:
        resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, cap_bytes))
    except (ValueError, OSError) as exc:
        print(
            f"WARN: could not apply RLIMIT_AS={cap_gb} GB ({exc}); continuing without cap",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI + config
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run an execution algorithm + baseline over the configured train window.",
    )
    p.add_argument(
        "--algo",
        help="Factory name of the execution algorithm to test (registered in "
             "execution_algos/__init__.py). Required unless --baseline-only.",
    )
    p.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help=f"Path to config.yaml (default: {DEFAULT_CONFIG.relative_to(REPO_ROOT)}).",
    )
    p.add_argument(
        "--symbol", default=DEFAULT_SYMBOL,
        help=f"Instrument raw_symbol (default: {DEFAULT_SYMBOL}).",
    )
    p.add_argument(
        "--dates",
        help="Comma-separated YYYYMMDD list overriding config.yaml train dates. "
             "Debugging-only; production runs should read from config.",
    )
    p.add_argument(
        "--baseline-only", action="store_true",
        help="Run only the baseline (refreshes its result dirs). Skip the algo.",
    )
    p.add_argument(
        "--use-cached-baseline", action="store_true",
        help="Skip the baseline subprocess; read existing "
             "<baseline>/results/<date>/metrics.json from disk instead. "
             "Missing cache entries surface as failures, same UX as today "
             "when a baseline subprocess fails on a date with no DBN data. "
             "Run --baseline-only first to populate or refresh the cache.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the (date, algo) backtest plan and exit without running.",
    )
    p.add_argument(
        "--smoke", action="store_true",
        help="Bypass Nautilus entirely; generate deterministic synthetic "
             "metrics for the algo and baseline (seeded by algo_name+date). "
             "Outputs go to execution_algos/<algo>/results-smoke/, not "
             "results/. Use to test pipeline infrastructure (factory "
             "registration, aggregation, paths, commit/hook/snapshot) in "
             "seconds rather than the ~30 min a real run takes. Mutually "
             "exclusive with --use-cached-baseline and --baseline-only.",
    )
    # Hidden: spawned recursively by run_one() to get subprocess isolation.
    # Not for users; running it manually has no extra behavior worth exposing.
    p.add_argument(
        "--internal-single-run", action="store_true",
        help=argparse.SUPPRESS,
    )
    return p.parse_args()


def load_config(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def train_dates_from_config(cfg: dict) -> list[str]:
    """Calendar-day YYYYMMDD list, both endpoints inclusive, weekends-aware.

    GLBX FX futures trade Sunday evening through Friday US time, so:
      - Saturday partitions don't exist → drop (dropping here saves a
        wasted S3 sync attempt + a guaranteed failure entry in the
        runner's per-date loop, which used to cost ~600s per Saturday
        on cascade-fail).
      - Sunday partitions DO exist (the evening session) → keep.
    Other non-trading dates (US holidays) are not filtered here; they
    still surface downstream as a run_backtest() failure, which we
    catch and skip.
    """
    start, end = cfg["data_window"]["train"]
    days = pd.date_range(start, end, freq="D")
    # pandas dayofweek: Mon=0..Sun=6. Drop Saturday only.
    days = days[days.dayofweek != 5]
    return days.strftime("%Y%m%d").tolist()


# ---------------------------------------------------------------------------
# Run-dir lookup
# ---------------------------------------------------------------------------

def algo_results_dir(algo_name: str, subdir: str = "results") -> Path:
    """Path to <algo>/<subdir>/ on disk.

    EXECUTION_DIRS handles the legacy 'simple' -> 'simple_execution_strategy'
    mapping; new algos use their factory name as the directory name.

    `subdir` is "results" for normal runs and "results-smoke" for smoke runs
    (so synthetic artifacts never collide with canonical ones).
    """
    dir_name = EXECUTION_DIRS.get(algo_name, algo_name)
    return REPO_ROOT / "execution_algos" / dir_name / subdir


def load_cached_baseline_metrics(baseline_name: str, date: str) -> dict:
    """Read pre-computed baseline metrics for one date from disk.

    Returns the same dict shape as `run_one()` (includes `_run_dir` and
    `_date`). Raises FileNotFoundError if the metrics.json is absent — the
    caller treats that like a subprocess failure and drops the date from
    the comparable set.
    """
    run_dir = algo_results_dir(baseline_name) / date
    metrics_file = run_dir / "metrics.json"
    if not metrics_file.exists():
        raise FileNotFoundError(
            f"--use-cached-baseline: no metrics.json at "
            f"{metrics_file.relative_to(REPO_ROOT)} "
            f"(run `--baseline-only` to populate)"
        )
    metrics = json.loads(metrics_file.read_text())
    metrics["_run_dir"] = str(run_dir.relative_to(REPO_ROOT))
    metrics["_date"] = date
    return metrics


def newest_run_dir_excluding(results_dir: Path, exclude: set[Path]) -> Path | None:
    if not results_dir.exists():
        return None
    candidates = [
        p for p in results_dir.iterdir()
        if p.is_dir() and p not in exclude
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


# ---------------------------------------------------------------------------
# Per-run execution
# ---------------------------------------------------------------------------

def _run_one_in_process(*, algo_name: str, date: str, cfg: dict, symbol: str) -> dict:
    """Run ONE backtest in the current process. Used by the child subprocess.

    Parents should call `run_one()` instead, which wraps this in a subprocess
    to dodge Nautilus's single-process native-mem abort.

    Raises RuntimeError if no new run dir appeared (engine never persisted)
    or if trade_count == 0 (silent exec_id misroute — see log.md
    OBSERVATIONS #1 in the spread-filter iteration).
    """
    results_dir = algo_results_dir(algo_name)
    existing = {p for p in results_dir.iterdir() if p.is_dir()} if results_dir.exists() else set()

    engine = run_backtest(
        strategy_name=cfg["strategy"]["name"],
        # Defensive copy: run_backtest pops keys from strategy_kwargs.
        strategy_kwargs=dict(cfg["strategy"]["kwargs"]),
        execution_algorithm_name=algo_name,
        date=date,
        symbol=symbol,
    )
    engine.dispose()

    new_dir = newest_run_dir_excluding(results_dir, existing)
    if new_dir is None:
        raise RuntimeError(
            f"No new run dir under {results_dir.relative_to(REPO_ROOT)} after "
            f"run_backtest({algo_name}, {date}). Did persist() write?"
        )
    metrics = json.loads((new_dir / "metrics.json").read_text())
    if metrics.get("trade_count", 0) == 0:
        raise RuntimeError(
            f"trade_count == 0 for ({algo_name}, {date}). "
            f"Likely exec_id misroute (check {algo_name}'s factory passes "
            f"exec_id='MY_GENERIC_ALGO'). See log.md OBSERVATIONS #1."
        )
    metrics["_run_dir"] = str(new_dir.relative_to(REPO_ROOT))
    metrics["_date"] = date
    return metrics


def run_one(*, algo_name: str, date: str, symbol: str, config_path: Path) -> dict:
    """Run one backtest in a FRESH subprocess, return its metrics.

    Why subprocess: Nautilus engines hold native memory that engine.dispose()
    doesn't fully release; running 2 backtests in the same Python process
    crashes the second one (SIGABRT). A fresh process per backtest is the
    standard workaround. See research/suggested_improvements.md P0 #4.

    Child output protocol: the child prints `__METRICS_JSON__{...}` as its
    last stdout line. Anything before that is Nautilus log noise we discard.
    On any failure (non-zero exit, timeout, missing marker), raise
    RuntimeError with a stderr/stdout tail to give the agent a fighting
    chance to debug.
    """
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--internal-single-run",
        "--algo", algo_name,
        "--dates", date,
        "--symbol", symbol,
        "--config", str(config_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SEC,
            # Inherit env so DATA_CACHE_DIR, S3_BUCKET_NAME, etc. propagate.
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"subprocess timed out after {SUBPROCESS_TIMEOUT_SEC}s "
            f"({algo_name}, {date})"
        )

    if proc.returncode != 0:
        # Negative returncode on POSIX = killed by signal; -6 = SIGABRT
        # (the Nautilus native-mem abort we're isolating from each other).
        sig_hint = ""
        if proc.returncode < 0:
            sig_hint = f" (killed by signal {-proc.returncode})"
        tail = "\n".join(proc.stderr.splitlines()[-15:]) or "(empty stderr)"
        raise RuntimeError(
            f"subprocess exited {proc.returncode}{sig_hint} for "
            f"({algo_name}, {date}). stderr tail:\n{tail}"
        )

    # Walk stdout in reverse so we tolerate trailing blank lines / log noise.
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith(METRICS_MARKER):
            return json.loads(line[len(METRICS_MARKER):])

    tail = "\n".join(proc.stdout.splitlines()[-10:]) or "(empty stdout)"
    raise RuntimeError(
        f"subprocess exited 0 but emitted no {METRICS_MARKER} line for "
        f"({algo_name}, {date}). stdout tail:\n{tail}"
    )


# ---------------------------------------------------------------------------
# Smoke mode (synthetic metrics — Nautilus bypass for infra testing)
# ---------------------------------------------------------------------------

SMOKE_SUBDIR = "results-smoke"


def smoke_metrics_for(*, algo_name: str, date: str) -> dict:
    """Deterministic synthetic per-date metrics, seeded by (algo_name, date).

    Schema matches compute_metrics() in backtest_engine/results.py so the
    aggregator path is exercised identically to a real run. Reruns of the
    same (algo_name, date) produce identical numbers — the seed is hashed
    from the pair, not time-based.
    """
    seed = int.from_bytes(
        hashlib.sha256(f"{algo_name}::{date}".encode()).digest()[:8],
        "big",
    )
    rng = random.Random(seed)

    starting = 1_000_000.0
    realized = rng.uniform(50.0, 350.0)
    trade_count = rng.randint(100, 500)
    win_rate = rng.uniform(0.40, 0.55)
    winners = int(round(trade_count * win_rate))
    losers = trade_count - winners
    order_count = trade_count * 2

    return {
        "starting_balance":     starting,
        "final_equity":         starting + realized,
        "total_return_pct":     realized / starting * 100,
        "realized_pnl":         realized,
        "max_drawdown_pct":     -rng.uniform(0.001, 0.005),
        "sharpe_ratio":         rng.uniform(1.0, 3.5),
        "trade_count":          trade_count,
        "winners":              winners,
        "losers":               losers,
        "win_rate":             winners / trade_count if trade_count else 0.0,
        "long_count":           trade_count // 2,
        "short_count":          trade_count - trade_count // 2,
        "order_count":          order_count,
        "fill_count":           order_count,
        "total_commissions":    0.0,
        "mean_slippage":        0.0,
        "max_abs_slippage":     0.0,
        "arrival_mid_captured": order_count,
        "arrival_mid_total":    order_count,
        "is_mean_bps":          rng.uniform(0.05, 0.25),
        "is_weighted_bps":      rng.uniform(0.05, 0.25),
        "is_max_bps":           rng.uniform(20.0, 35.0),
        "is_min_bps":           -rng.uniform(3.0, 8.0),
        "is_total_price":       float(rng.randint(30, 120)),
        "unrealized_pnl":       0.0,
    }


def smoke_run_one(*, algo_name: str, date: str) -> dict:
    """Generate synthetic metrics, write to results-smoke/<date>/metrics.json,
    and return the dict with `_run_dir` + `_date` attached.

    Mimics `_run_one_in_process()`'s return shape so the aggregator path
    is exercised unchanged. Unlike `persist()` it overwrites without
    complaint — smoke is for repeated pipeline testing, not canonical runs.
    """
    run_dir = algo_results_dir(algo_name, subdir=SMOKE_SUBDIR) / date
    run_dir.mkdir(parents=True, exist_ok=True)

    metrics = smoke_metrics_for(algo_name=algo_name, date=date)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")

    metrics["_run_dir"] = str(run_dir.relative_to(REPO_ROOT))
    metrics["_date"] = date
    return metrics


def smoke_preflight(algo_name: str, baseline_name: str) -> str | None:
    """Verify both algos are registered in the factory.

    Catches the most common bug (forgetting to register a new algo in
    `execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES`) without
    paying the Nautilus startup cost or running an actual backtest.

    Returns an error message on failure, None on success.
    """
    from execution_algos import _EXEC_ALGORITHM_FACTORIES
    for name in (algo_name, baseline_name):
        if name not in _EXEC_ALGORITHM_FACTORIES:
            available = ", ".join(sorted(_EXEC_ALGORITHM_FACTORIES))
            return (
                f"'{name}' not registered in _EXEC_ALGORITHM_FACTORIES. "
                f"Available: {available}"
            )
    return None


# ---------------------------------------------------------------------------
# Aggregation (per snapshot/SKILL.md section 3 rules)
# ---------------------------------------------------------------------------

def _sum(metrics_list: list[dict], key: str, default=0) -> float:
    return sum(m.get(key, default) for m in metrics_list)


def aggregate(per_date: list[dict]) -> dict:
    """Aggregate per-date metrics into a single block.

    Aggregation rules from snapshot/SKILL.md section 3:
      - sums: realized_pnl, unrealized_pnl, total_commissions, trade_count,
              winners, losers, order_count, fill_count, is_total_price
      - mean: sharpe_ratio (per-date mean of daily-scaled Sharpe)
      - min:  max_drawdown_pct (most negative)
      - win_rate: recomputed from summed counts
      - mean_slippage: trade-count-weighted mean
      - max_abs_slippage: max across days
      - is_weighted_bps: captured-order-count-weighted mean across dates
      - total_return_pct: recomputed from (realized + unrealized) /
                         starting_balance (no cross-day compounding)
    """
    if not per_date:
        raise ValueError("aggregate() called with empty list")

    summed_pnl     = _sum(per_date, "realized_pnl",     0.0)
    summed_trades  = _sum(per_date, "trade_count",      0)
    summed_winners = _sum(per_date, "winners",          0)

    if summed_trades > 0:
        mean_slip = sum(
            m["mean_slippage"] * m["trade_count"] for m in per_date
        ) / summed_trades
    else:
        mean_slip = sum(m["mean_slippage"] for m in per_date) / len(per_date)

    # IS: captured-order-count-weighted mean of per-date is_weighted_bps. Skip
    # dates where no orders captured an arrival mid (is_weighted_bps is None).
    is_dates = [
        m for m in per_date
        if m.get("is_weighted_bps") is not None and m.get("arrival_mid_captured", 0) > 0
    ]
    total_captured = sum(m["arrival_mid_captured"] for m in is_dates)
    if is_dates and total_captured > 0:
        is_weighted_bps = sum(
            m["is_weighted_bps"] * m["arrival_mid_captured"] for m in is_dates
        ) / total_captured
        is_total_price = sum(m.get("is_total_price") or 0.0 for m in is_dates)
    else:
        is_weighted_bps = None
        is_total_price = None

    summed_unrealized = _sum(per_date, "unrealized_pnl", 0.0)

    daily_returns = [
        (m.get("realized_pnl", 0.0) + m.get("unrealized_pnl", 0.0)) / STARTING_BALANCE_USD
        for m in per_date
    ]
    if len(daily_returns) > 1:
        # Cross-day annualized Sharpe: mean(daily_returns) / std(daily_returns) * sqrt(252)
        ret_series = pd.Series(daily_returns)
        mean_ret = ret_series.mean()
        std_ret = ret_series.std(ddof=1)
        agg_sharpe = float(mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
    else:
        # Cannot compute cross-day variance with N=1.
        agg_sharpe = 0.0

    return {
        "realized_pnl":       summed_pnl,
        "unrealized_pnl": summed_unrealized,
        "sharpe_ratio":       agg_sharpe,
        "sharpe_n_days":      len(per_date),
        "max_drawdown_pct":   min(m["max_drawdown_pct"] for m in per_date),
        "win_rate":           (summed_winners / summed_trades) if summed_trades else 0.0,
        "trade_count":        summed_trades,
        "winners":            summed_winners,
        "losers":             _sum(per_date, "losers",     0),
        "order_count":        _sum(per_date, "order_count", 0),
        "fill_count":         _sum(per_date, "fill_count",  0),
        "mean_slippage":      mean_slip,
        "max_abs_slippage":   max(m["max_abs_slippage"] for m in per_date),
        "total_commissions":  _sum(per_date, "total_commissions", 0.0),
        "total_return_pct":   ((summed_pnl + summed_unrealized) / STARTING_BALANCE_USD) * 100,
        "is_weighted_bps":    is_weighted_bps,
        "is_total_price":     is_total_price,
    }


def safe_pct_delta(mine: float, base: float) -> float:
    """Percentage delta vs base, guarded against base == 0."""
    if abs(base) < 1e-9:
        return 0.0 if abs(mine - base) < 1e-9 else float("inf")
    return (mine - base) / abs(base) * 100


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_backtest_results(
    *,
    algo_name: str,
    baseline_name: str,
    cfg: dict,
    symbol: str,
    algo_agg: dict,
    base_agg: dict,
    train_dates: list[str],
    run_dirs: list[str],
    results_subdir: str = "results",
) -> Path:
    """Write <algo>/results/backtest-results.json per snapshot/SKILL.md section 3."""
    perf_keys = (
        "realized_pnl", "unrealized_pnl",
        "sharpe_ratio", "sharpe_n_days", "max_drawdown_pct", "win_rate",
        "trade_count", "mean_slippage", "max_abs_slippage",
        "total_commissions", "total_return_pct",
        "is_weighted_bps", "is_total_price",
    )
    performance = {k: algo_agg[k] for k in perf_keys}
    algo_total = algo_agg["realized_pnl"] + algo_agg["unrealized_pnl"]
    base_total = base_agg["realized_pnl"] + base_agg["unrealized_pnl"]
    performance["vs_baseline_pnl_pct"]      = safe_pct_delta(algo_total,                base_total)
    performance["vs_baseline_slippage_pct"] = safe_pct_delta(algo_agg["mean_slippage"], base_agg["mean_slippage"])
    if algo_agg["is_weighted_bps"] is not None and base_agg["is_weighted_bps"] is not None:
        performance["vs_baseline_is_bps"] = safe_pct_delta(
            algo_agg["is_weighted_bps"], base_agg["is_weighted_bps"]
        )
    else:
        performance["vs_baseline_is_bps"] = None

    payload = {
        "algo_name":     algo_name,
        "backtest_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline":      baseline_name,
        "sharpe_metric_version": "v2",
        "strategy_used": cfg["strategy"]["name"],
        "symbol":        symbol,
        "performance":   performance,
        "performance_oos": None,  # filled by the evaluate skill post-snapshot
        "period": {
            "train_dates": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in train_dates],
            "test_dates":  [],
        },
        "run_dirs": run_dirs,
    }
    out_path = algo_results_dir(algo_name, subdir=results_subdir) / "backtest-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


def write_metadata(
    *,
    algo_name: str,
    cfg: dict,
    symbol: str,
    per_date_metrics: list[dict],
    results_subdir: str = "results",
) -> Path:
    """Write the consolidated `<algo>/results/metadata.json` reproduction file.

    Constructed directly from `cfg`, the algorithm name, and the per-run trading
    dates. No per-run metadata sidecar is read or needed — the parent has
    everything required to fully describe the reproduction.
    """
    runs = [{"date": m["_date"]} for m in per_date_metrics]

    payload = {
        "strategy_name":             cfg["strategy"]["name"],
        "strategy_kwargs":           cfg["strategy"]["kwargs"],
        "execution_algorithm_name":  algo_name,
        "execution_algorithm_kwargs": {},
        "symbol":                    symbol,
        "dataset_name":              cfg["dataset"]["name"],
        "dataset_version":           cfg["dataset"]["version"],
        "runs":                      sorted(runs, key=lambda r: r["date"] or ""),
    }

    out_path = algo_results_dir(algo_name, subdir=results_subdir) / "metadata.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


def classify_verdict(delta_pnl_pct: float, cfg: dict) -> str:
    """Map a P&L delta to PASS / CLOSE / FAIL per config.yaml -> pass_gate.

    Interpretation matches log.md OBSERVATIONS #8: CLOSE = [gate_min - close_margin, gate_min).
    This is the agent's call in the end (OBJECTIVE.md section 5 step 7); we just suggest.
    """
    gate_min   = cfg["pass_gate"]["min_pnl_improvement_pct"]
    gate_close = cfg["pass_gate"]["close_margin_pct"]
    if delta_pnl_pct >= gate_min:
        return "PASS"
    if delta_pnl_pct >= gate_min - gate_close:
        return "CLOSE"
    return "FAIL"


def print_summary(
    *,
    algo_name: str | None,
    baseline_name: str,
    algo_agg: dict | None,
    base_agg: dict,
    cfg: dict,
) -> None:
    print()
    print("=" * 66)
    print("Research-loop backtest summary")
    print("=" * 66)
    print(f"  strategy : {cfg['strategy']['name']}")
    print(f"  baseline : {baseline_name}")
    if algo_name:
        print(f"  algorithm: {algo_name}")
    print()

    if algo_agg is None:
        print("Baseline-only run — per-date aggregate:")
        for k in ("realized_pnl", "sharpe_ratio", "trade_count", "mean_slippage"):
            v = base_agg[k]
            print(f"    {k:<22} {v:>14.4f}" if isinstance(v, float) else f"    {k:<22} {v:>14}")
        print("=" * 66)
        return

    print(f"  {'metric':<24}{'algo':>14}{'baseline':>14}{'delta_%':>12}")
    print("  " + "-" * 64)
    rows = [
        ("realized_pnl",       algo_agg["realized_pnl"],       base_agg["realized_pnl"]),
        ("unrealized_pnl", algo_agg["unrealized_pnl"], base_agg["unrealized_pnl"]),
        ("sharpe_ratio",       algo_agg["sharpe_ratio"],       base_agg["sharpe_ratio"]),
        ("max_drawdown_pct",   algo_agg["max_drawdown_pct"],   base_agg["max_drawdown_pct"]),
        ("win_rate",           algo_agg["win_rate"],           base_agg["win_rate"]),
        ("trade_count",        algo_agg["trade_count"],        base_agg["trade_count"]),
        ("mean_slippage",      algo_agg["mean_slippage"],      base_agg["mean_slippage"]),
    ]
    for name, mine, base in rows:
        print(f"  {name:<24}{mine:>14.4f}{base:>14.4f}{safe_pct_delta(mine, base):>+12.2f}")
    if algo_agg.get("is_weighted_bps") is not None and base_agg.get("is_weighted_bps") is not None:
        mine, base = algo_agg["is_weighted_bps"], base_agg["is_weighted_bps"]
        print(f"  {'is_weighted_bps':<24}{mine:>14.4f}{base:>14.4f}{safe_pct_delta(mine, base):>+12.2f}")

    algo_total = algo_agg["realized_pnl"] + algo_agg["unrealized_pnl"]
    base_total = base_agg["realized_pnl"] + base_agg["unrealized_pnl"]
    delta_pnl_pct = safe_pct_delta(algo_total, base_total)
    verdict = classify_verdict(delta_pnl_pct, cfg)
    gate_min   = cfg["pass_gate"]["min_pnl_improvement_pct"]
    gate_close = cfg["pass_gate"]["close_margin_pct"]
    print()
    print(f"  Pass gate: min_pnl_improvement_pct={gate_min}, close_margin_pct={gate_close}")
    print(f"  Suggested verdict (train-only): {verdict}  (delta_pnl_pct={delta_pnl_pct:+.2f}, basis=realized+unrealized)")
    print()
    print("  Note: this is an informational suggestion. The final PASS/CLOSE/FAIL")
    print("  decision rests with the agent per OBJECTIVE.md section 5 step 7.")
    if algo_agg["trade_count"] < 30:
        print()
        print(f"  ⚠ WARNING: trade_count={algo_agg['trade_count']} < 30. "
              f"Sharpe and win_rate may be unreliable (OBJECTIVE.md section 8).")
    print("=" * 66)


# ---------------------------------------------------------------------------
# Internal subprocess entry point
# ---------------------------------------------------------------------------

def _do_internal_single_run(args: argparse.Namespace) -> int:
    """Execute exactly one backtest and print its metrics as JSON for the parent.

    The parent invokes us with `--internal-single-run --algo X --dates YYYYMMDD
    --symbol Z --config /path`. We run the backtest once, then print
    `__METRICS_JSON__{...}` as the last stdout line for the parent to parse.

    On failure we exit non-zero; parent surfaces stderr tail. Do not print
    anything else to stdout after the marker line.
    """
    _apply_memory_cap()

    if not args.algo:
        print("ERROR: --internal-single-run requires --algo", file=sys.stderr)
        return 2
    if not args.dates:
        print("ERROR: --internal-single-run requires --dates", file=sys.stderr)
        return 2

    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    if len(dates) != 1:
        print(f"ERROR: --internal-single-run expects exactly one date, got {len(dates)}",
              file=sys.stderr)
        return 2

    cfg = load_config(args.config)
    try:
        metrics = _run_one_in_process(
            algo_name=args.algo,
            date=dates[0],
            cfg=cfg,
            symbol=args.symbol,
        )
    except Exception as exc:  # noqa: BLE001 — message goes back to parent via stderr
        print(f"_run_one_in_process raised: {exc}", file=sys.stderr)
        return 1

    # Parent reads the last stdout line starting with this marker; do not
    # print anything after this point.
    print(f"{METRICS_MARKER}{json.dumps(metrics)}")
    return 0


# ---------------------------------------------------------------------------
# Smoke entry point
# ---------------------------------------------------------------------------

def run_smoke(*, args: argparse.Namespace, cfg: dict, baseline: str,
              dates: list[str]) -> int:
    """Generate synthetic metrics for algo + baseline across `dates`, run
    aggregation, write backtest-results.json + metadata.json under
    `results-smoke/`. End-to-end pipeline test without Nautilus.
    """
    err = smoke_preflight(args.algo, baseline)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print("=" * 66)
    print("⚠  SMOKE MODE — synthetic metrics, not real backtests")
    print("=" * 66)
    print(f"  algo    : {args.algo}")
    print(f"  baseline: {baseline}")
    print(f"  dates   : {len(dates)} ({dates[0]} … {dates[-1]})")
    print(f"  output  : execution_algos/<algo>/{SMOKE_SUBDIR}/")
    print()

    if args.dry_run:
        for date in dates:
            print(f"  - smoke_run_one(algo={args.algo}, date={date})")
            print(f"  - smoke_run_one(algo={baseline}, date={date})")
        print()
        print("(dry-run: no smoke runs executed)")
        return 0

    algo_metrics: dict[str, dict] = {}
    base_metrics: dict[str, dict] = {}
    for date in dates:
        algo_metrics[date] = smoke_run_one(algo_name=args.algo, date=date)
        base_metrics[date] = smoke_run_one(algo_name=baseline,   date=date)

    comparable = sorted(set(algo_metrics) & set(base_metrics))
    algo_agg = aggregate([algo_metrics[d] for d in comparable])
    base_agg = aggregate([base_metrics[d] for d in comparable])

    out_path = write_backtest_results(
        algo_name=args.algo,
        baseline_name=baseline,
        cfg=cfg,
        symbol=args.symbol,
        algo_agg=algo_agg,
        base_agg=base_agg,
        train_dates=comparable,
        run_dirs=[algo_metrics[d]["_run_dir"] for d in comparable],
        results_subdir=SMOKE_SUBDIR,
    )
    print(f"Wrote: {out_path.relative_to(REPO_ROOT)}")

    meta_path = write_metadata(
        algo_name=args.algo,
        cfg=cfg,
        symbol=args.symbol,
        per_date_metrics=[algo_metrics[d] for d in comparable],
        results_subdir=SMOKE_SUBDIR,
    )
    print(f"Wrote: {meta_path.relative_to(REPO_ROOT)}")

    print_summary(algo_name=args.algo, baseline_name=baseline,
                  algo_agg=algo_agg, base_agg=base_agg, cfg=cfg)
    print()
    print("⚠  SMOKE numbers are synthetic — do NOT commit results-smoke/ "
          "or write them to program_database.json.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    # Internal subprocess: short-circuit before user-facing checks (which
    # would reject e.g. --algo simple matching the baseline).
    if args.internal_single_run:
        return _do_internal_single_run(args)

    if not args.algo and not args.baseline_only:
        print("ERROR: --algo is required (unless --baseline-only).", file=sys.stderr)
        return 2

    cfg = load_config(args.config)
    baseline = cfg["pass_gate"]["baseline"]

    dates = (
        [d.strip() for d in args.dates.split(",") if d.strip()]
        if args.dates
        else train_dates_from_config(cfg)
    )
    if not dates:
        print("ERROR: empty date list.", file=sys.stderr)
        return 2

    if args.algo and args.algo == baseline:
        print(f"ERROR: --algo ({args.algo}) is the same as the baseline. "
              f"Use --baseline-only to refresh just the baseline.", file=sys.stderr)
        return 2

    if args.use_cached_baseline and args.baseline_only:
        print("ERROR: --use-cached-baseline and --baseline-only are mutually "
              "exclusive (one reads the cache, the other writes it).",
              file=sys.stderr)
        return 2

    if args.smoke and (args.use_cached_baseline or args.baseline_only):
        print("ERROR: --smoke is mutually exclusive with --use-cached-baseline "
              "and --baseline-only (smoke generates synthetic metrics for both "
              "algo and baseline; nothing to cache or refresh).",
              file=sys.stderr)
        return 2

    # ----- smoke mode: bypass Nautilus, generate synthetic metrics -----
    if args.smoke:
        return run_smoke(args=args, cfg=cfg, baseline=baseline, dates=dates)

    # ----- plan -----
    if args.baseline_only:
        planned = len(dates)
    elif args.use_cached_baseline:
        planned = len(dates)  # only the algo runs as a subprocess
    else:
        planned = len(dates) * 2
    print(f"Plan: {planned} backtest(s)")
    print(f"  symbol  : {args.symbol}")
    print(f"  strategy: {cfg['strategy']['name']}")
    if not args.baseline_only:
        print(f"  algo    : {args.algo}")
    baseline_mode = "cached" if args.use_cached_baseline else "subprocess"
    print(f"  baseline: {baseline} ({baseline_mode})")
    print(f"  dates   : {', '.join(dates)}")
    if args.dry_run:
        print()
        for date in dates:
            if not args.baseline_only:
                print(f"  - run_backtest(execution_algorithm={args.algo}, date={date})")
            if args.use_cached_baseline:
                cached_path = algo_results_dir(baseline) / date / "metrics.json"
                print(f"  - read cached baseline metrics: "
                      f"{cached_path.relative_to(REPO_ROOT)}")
            else:
                print(f"  - run_backtest(execution_algorithm={baseline}, date={date})")
        print()
        print("(dry-run: no backtests executed)")
        return 0

    # ----- execute date-major (so we can pair algo + baseline cleanly) -----
    algo_metrics: dict[str, dict] = {}
    base_metrics: dict[str, dict] = {}
    failures: list[tuple[str, str, str]] = []  # (algo_name, date, error)

    # Iteration wall-clock budget (issue #61). Guards against the per-date
    # cascade where a wedged algorithm + 600s subprocess timeout could burn
    # ~2 hours of wall-clock before the iteration completed. 0 / missing
    # disables. Checked at the *start* of each date — the in-flight
    # subprocess (if any) is allowed to finish so we don't lose work that
    # was about to land.
    budget_sec = float(cfg.get("loop", {}).get("iteration_timeout_seconds", 0) or 0)
    loop_start = time.monotonic()
    budget_exceeded = False

    for date in dates:
        if budget_sec > 0 and (time.monotonic() - loop_start) > budget_sec:
            remaining = [d for d in dates[dates.index(date):]]
            print(
                f"\n⚠ ITERATION BUDGET EXCEEDED ({budget_sec:.0f}s). "
                f"Skipping {len(remaining)} remaining date(s): "
                f"{', '.join(remaining)}",
                file=sys.stderr,
            )
            budget_exceeded = True
            break

        if not args.baseline_only:
            print(f"\n>>> run_backtest({args.algo}, {date}) ...", flush=True)
            try:
                m = run_one(
                    algo_name=args.algo, date=date,
                    symbol=args.symbol, config_path=args.config,
                )
                algo_metrics[date] = m
                s_ratio = m.get("sharpe_ratio_intraday", m.get("sharpe_ratio", 0.0))
                print(f"    OK   trades={m['trade_count']} pnl={m['realized_pnl']:.2f} "
                      f"sharpe={s_ratio:.2f}")
            except Exception as exc:  # noqa: BLE001 — surface any failure to the agent
                print(f"    FAIL {exc}", file=sys.stderr)
                failures.append((args.algo, date, str(exc)))

        if args.use_cached_baseline:
            print(f"\n>>> cached baseline({baseline}, {date}) ...", flush=True)
            try:
                m = load_cached_baseline_metrics(baseline, date)
                base_metrics[date] = m
                s_ratio = m.get("sharpe_ratio_intraday", m.get("sharpe_ratio", 0.0))
                print(f"    CACHE trades={m['trade_count']} pnl={m['realized_pnl']:.2f} "
                      f"sharpe={s_ratio:.2f}")
            except Exception as exc:  # noqa: BLE001
                print(f"    FAIL {exc}", file=sys.stderr)
                failures.append((baseline, date, str(exc)))
        else:
            print(f"\n>>> run_backtest({baseline}, {date}) ...", flush=True)
            try:
                m = run_one(
                    algo_name=baseline, date=date,
                    symbol=args.symbol, config_path=args.config,
                )
                base_metrics[date] = m
                s_ratio = m.get("sharpe_ratio_intraday", m.get("sharpe_ratio", 0.0))
                print(f"    OK   trades={m['trade_count']} pnl={m['realized_pnl']:.2f} "
                      f"sharpe={s_ratio:.2f}")
            except Exception as exc:  # noqa: BLE001
                print(f"    FAIL {exc}", file=sys.stderr)
                failures.append((baseline, date, str(exc)))

    # ----- report failures -----
    if failures:
        print(f"\n{len(failures)} run(s) failed:", file=sys.stderr)
        for algo, date, err in failures:
            print(f"  - {algo} @ {date}: {err}", file=sys.stderr)

    if not base_metrics:
        print("\nERROR: no successful baseline runs — cannot compute anything.", file=sys.stderr)
        return 1

    # ----- baseline-only branch -----
    if args.baseline_only:
        base_dates = sorted(base_metrics)
        base_agg = aggregate([base_metrics[d] for d in base_dates])

        # Write the same aggregate files as a normal --algo run, using the
        # baseline as its own comparator. vs_baseline_* deltas come out as 0.
        out_path = write_backtest_results(
            algo_name=baseline,
            baseline_name=baseline,
            cfg=cfg,
            symbol=args.symbol,
            algo_agg=base_agg,
            base_agg=base_agg,
            train_dates=base_dates,
            run_dirs=[base_metrics[d]["_run_dir"] for d in base_dates],
        )
        print(f"\nWrote: {out_path.relative_to(REPO_ROOT)}")

        meta_path = write_metadata(
            algo_name=baseline,
            cfg=cfg,
            symbol=args.symbol,
            per_date_metrics=[base_metrics[d] for d in base_dates],
        )
        print(f"Wrote: {meta_path.relative_to(REPO_ROOT)}")

        print_summary(algo_name=None, baseline_name=baseline,
                      algo_agg=None, base_agg=base_agg, cfg=cfg)
        return 0 if not failures and not budget_exceeded else 1

    if not algo_metrics:
        print("\nERROR: no successful algo runs — cannot aggregate.", file=sys.stderr)
        return 1

    # ----- pair date-by-date (only dates where BOTH succeeded are comparable) -----
    comparable = sorted(set(algo_metrics) & set(base_metrics))
    dropped = sorted(set(dates) - set(comparable))
    if dropped:
        print(f"\n⚠ Dropping {len(dropped)} date(s) from aggregate (one side failed): "
              f"{', '.join(dropped)}", file=sys.stderr)

    if not comparable:
        print("\nERROR: no dates where both algo and baseline succeeded.", file=sys.stderr)
        return 1

    algo_agg = aggregate([algo_metrics[d] for d in comparable])
    base_agg = aggregate([base_metrics[d] for d in comparable])

    out_path = write_backtest_results(
        algo_name=args.algo,
        baseline_name=baseline,
        cfg=cfg,
        symbol=args.symbol,
        algo_agg=algo_agg,
        base_agg=base_agg,
        train_dates=comparable,
        run_dirs=[algo_metrics[d]["_run_dir"] for d in comparable],
    )
    print(f"\nWrote: {out_path.relative_to(REPO_ROOT)}")

    meta_path = write_metadata(
        algo_name=args.algo,
        cfg=cfg,
        symbol=args.symbol,
        per_date_metrics=[algo_metrics[d] for d in comparable],
    )
    print(f"Wrote: {meta_path.relative_to(REPO_ROOT)}")

    print_summary(algo_name=args.algo, baseline_name=baseline,
                  algo_agg=algo_agg, base_agg=base_agg, cfg=cfg)

    return 0 if not failures and not budget_exceeded else 1


if __name__ == "__main__":
    sys.exit(main())
