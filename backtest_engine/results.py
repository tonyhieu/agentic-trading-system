"""Capture, compute, and persist a single backtest run as a comparable artifact.

A run lands at `{strategy_dir}/results/{timestamp}-{shortsha}/` containing:
- metadata.json: run config (strategy, params, exec algo, params, date, symbol, git sha, ts)
- metrics.json:  summary stats for cross-run comparison
- account.csv, orders.csv, fills.csv, positions.csv: raw Nautilus reports
"""
from __future__ import annotations

import ast
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

# Annualization basis for Sharpe: 1-min returns, 24h futures session, 252 trading days.
MINUTES_PER_TRADING_YEAR = 252 * 24 * 60


@dataclass
class Reports:
    account: pd.DataFrame
    orders: pd.DataFrame
    fills: pd.DataFrame
    positions: pd.DataFrame


def _git_short_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "nogit"


def _coerce(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "value"):  # nautilus identifiers
        return str(v)
    if isinstance(v, dict):
        return {k: _coerce(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_coerce(x) for x in v]
    return v


def _final_equity(account: pd.DataFrame) -> float | None:
    if account.empty:
        return None
    for col in ("balance_total", "total", "equity"):
        if col in account.columns:
            return float(account[col].iloc[-1])
    return None


def _max_drawdown_pct(account: pd.DataFrame) -> float | None:
    for col in ("balance_total", "total", "equity"):
        if col in account.columns and len(account) > 1:
            series = account[col].astype(float)
            peak = series.cummax()
            dd = (series - peak) / peak
            return float(dd.min() * 100.0)
    return None


def _parse_money(value: Any) -> float:
    """Nautilus reports money as strings like '11.25 USD'. Extract the leading number."""
    if pd.isna(value):
        return float("nan")
    s = str(value).strip().split()
    try:
        return float(s[0])
    except (ValueError, IndexError):
        return float("nan")


def _sum_money_list(value: Any) -> float:
    """Sum a commissions-like field. Nautilus stores commissions as a list[Money] per order;
    that becomes a stringified list once round-tripped through CSV."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (list, tuple)):
        return float(sum(_parse_money(v) for v in value if v is not None))
    s = str(value).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return float(sum(_parse_money(v) for v in parsed))
        except (ValueError, SyntaxError):
            pass
    return _parse_money(value)


def _sharpe_ratio(account: pd.DataFrame) -> float | None:
    """Annualized Sharpe from the equity curve, resampled to 1-minute bars.

    Note: Nautilus emits account rows only on account-changing events, so the
    forward-filled curve understates both mean and stdev of returns. The absolute
    value is imprecise, but the number is consistent across runs that use the
    same machinery, which is what this metric is for.
    """
    col = next((c for c in ("balance_total", "total", "equity") if c in account.columns), None)
    if col is None or len(account) < 2 or not isinstance(account.index, pd.DatetimeIndex):
        return None

    resampled = account[col].astype(float).resample("1min").last().ffill().dropna()
    if len(resampled) < 2:
        return None

    returns = resampled.pct_change().dropna()
    stdev = float(returns.std(ddof=1))
    if returns.empty or stdev == 0 or math.isnan(stdev):
        return None

    return float(returns.mean() / stdev * math.sqrt(MINUTES_PER_TRADING_YEAR))


def _execution_costs(orders: pd.DataFrame) -> dict[str, float | None]:
    """Per-order slippage (fill vs limit) and commissions, both reported by Nautilus.

    For arrival-price IS, see `backtest_engine.arrival_price`.
    """
    total_comm = mean_slip = max_slip = None

    if not orders.empty and "commissions" in orders.columns:
        total_comm = float(sum(_sum_money_list(v) for v in orders["commissions"]))

    if not orders.empty and "slippage" in orders.columns:
        slip = pd.to_numeric(orders["slippage"], errors="coerce").dropna()
        if not slip.empty:
            mean_slip = float(slip.mean())
            max_slip = float(slip.abs().max())

    return {
        "total_commissions": total_comm,
        "mean_slippage": mean_slip,
        "max_abs_slippage": max_slip,
    }


def compute_metrics(reports: Reports, starting_balance: float) -> dict[str, Any]:
    pos = reports.positions
    pnl_col = next((c for c in ("realized_pnl", "realized_return_pnl") if c in pos.columns), None)
    # `entry` is the side that opened the position (BUY=long, SELL=short).
    # `side` after close is FLAT, so always prefer `entry` for direction.
    side_col = "entry" if "entry" in pos.columns else ("side" if "side" in pos.columns else None)

    pnl_series = pos[pnl_col].map(_parse_money) if pnl_col else None
    realized_pnl = float(pnl_series.sum()) if pnl_series is not None else None
    winners = int((pnl_series > 0).sum()) if pnl_series is not None else None
    losers = int((pnl_series < 0).sum()) if pnl_series is not None else None
    trades = int(len(pos))
    win_rate = (winners / trades) if (winners is not None and trades) else None

    long_count = short_count = None
    if side_col:
        sides = pos[side_col].astype(str).str.upper()
        long_count = int(sides.isin(["BUY", "LONG"]).sum())
        short_count = int(sides.isin(["SELL", "SHORT"]).sum())

    final_equity = _final_equity(reports.account)
    total_return_pct = (
        ((final_equity - starting_balance) / starting_balance) * 100.0
        if final_equity is not None and starting_balance else None
    )

    return {
        "starting_balance": starting_balance,
        "final_equity": final_equity,
        "total_return_pct": total_return_pct,
        "realized_pnl": realized_pnl,
        "max_drawdown_pct": _max_drawdown_pct(reports.account),
        "sharpe_ratio": _sharpe_ratio(reports.account),
        "trade_count": trades,
        "winners": winners,
        "losers": losers,
        "win_rate": win_rate,
        "long_count": long_count,
        "short_count": short_count,
        "order_count": int(len(reports.orders)),
        "fill_count": int(len(reports.fills)),
        **_execution_costs(reports.orders),
    }


def persist(
    strategy_dir: Path,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    reports: Reports,
) -> Path:
    """Write a run to `{strategy_dir}/results/{timestamp}-{shortsha}/` and return that path."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    sha = _git_short_sha()
    run_dir = strategy_dir / "results" / f"{ts}-{sha}"
    run_dir.mkdir(parents=True, exist_ok=True)

    full_meta = {
        "timestamp_utc": ts,
        "git_sha_short": sha,
        **_coerce(metadata),
    }
    (run_dir / "metadata.json").write_text(json.dumps(full_meta, indent=2, default=str))

    safe_metrics = {
        k: (None if isinstance(v, float) and math.isnan(v) else v)
        for k, v in metrics.items()
    }
    (run_dir / "metrics.json").write_text(json.dumps(safe_metrics, indent=2, default=str))

    reports.account.to_csv(run_dir / "account.csv", index=True)
    reports.orders.to_csv(run_dir / "orders.csv", index=False)
    reports.fills.to_csv(run_dir / "fills.csv", index=False)
    reports.positions.to_csv(run_dir / "positions.csv", index=False)

    return run_dir
