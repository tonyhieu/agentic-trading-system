"""TWAP and VWAP execution benchmarks for the toy_example Pass Gate.

Interpretation (see toy_example/PROBLEM_DEFINITION.md §4 and the NOTES.md entry that
resolves its ambiguity):

For each closed round-trip position we reconstruct entry/exit fills as if the strategy
had used TWAP or VWAP instead of its actual (aggressive) fills. Entry/exit decision
times and position sizes are held equal to the strategy's — only fill prices change.

- TWAP fill = arithmetic mean of mid over [decision_ts, decision_ts + T_exec].
- VWAP fill = book-size-weighted mean of mid over the same window. MBP-1 has no
  trade volume, so we weight by displayed size on the side the execution would lift
  (ask_sz_00 for buys, bid_sz_00 for sells).
- T_exec defaults to 5 minutes.

Net P&L for each scenario = sum over positions of (close_px - open_px) * direction
* peak_qty, using each scenario's fill prices. This equals the spec's "Gross - IS"
decomposition algebraically.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_EXEC_WINDOW_SECONDS = 300


def _benchmark_fill(
    ticks: pd.DataFrame,
    decision_ts: pd.Timestamp,
    taking_side: str,
    window_seconds: int,
) -> tuple[float | None, float | None]:
    """Return (twap_fill, vwap_fill) for a decision at decision_ts taking taking_side.

    Returns (None, None) if no ticks cover the window.
    """
    end = decision_ts + pd.Timedelta(seconds=window_seconds)
    window = ticks[(ticks["ts_recv"] >= decision_ts) & (ticks["ts_recv"] < end)]
    if window.empty:
        return None, None

    twap = float(window["mid"].mean())

    size_col = "ask_sz_00" if taking_side == "BUY" else "bid_sz_00"
    weights = window[size_col].astype(float)
    total_weight = float(weights.sum())
    vwap = float((window["mid"] * weights).sum() / total_weight) if total_weight > 0 else twap

    return twap, vwap


def compute_execution_benchmarks(
    positions: pd.DataFrame,
    ticks: pd.DataFrame,
    exec_window_seconds: int = DEFAULT_EXEC_WINDOW_SECONDS,
) -> dict[str, float | int | None]:
    """Compute TWAP/VWAP benchmark net P&L and vs-strategy percentages.

    Returns keys: twap_net_pnl, vwap_net_pnl, vs_twap_pct, vs_vwap_pct,
    benchmark_trade_count, exec_window_seconds.

    `vs_*_pct` is (strategy_net - benchmark_net) / |benchmark_net| * 100. It is None
    when the benchmark net P&L is zero (percentage undefined) or no positions could
    be benchmarked (e.g., exit decisions fell past the end of available tick data).
    """
    base: dict[str, float | int | None] = {
        "twap_net_pnl": None,
        "vwap_net_pnl": None,
        "vs_twap_pct": None,
        "vs_vwap_pct": None,
        "benchmark_trade_count": 0,
        "exec_window_seconds": exec_window_seconds,
    }

    if positions.empty or ticks.empty:
        return base

    closed = positions[positions["side"].astype(str).str.upper() == "FLAT"].copy()
    if closed.empty:
        return base

    closed["ts_opened"] = pd.to_datetime(closed["ts_opened"], utc=True)
    closed["ts_closed"] = pd.to_datetime(closed["ts_closed"], utc=True)

    ticks = ticks[["ts_recv", "mid", "bid_sz_00", "ask_sz_00"]].copy()
    ticks["ts_recv"] = pd.to_datetime(ticks["ts_recv"], utc=True)
    ticks = ticks.sort_values("ts_recv").reset_index(drop=True)

    strategy_net = 0.0
    twap_net = 0.0
    vwap_net = 0.0
    counted = 0

    for _, pos in closed.iterrows():
        entry_side = str(pos["entry"]).upper()
        if entry_side not in ("BUY", "SELL"):
            continue
        qty = float(pos["peak_qty"]) if pd.notna(pos["peak_qty"]) else 0.0
        if qty == 0:
            continue

        direction = 1 if entry_side == "BUY" else -1
        exit_side = "SELL" if entry_side == "BUY" else "BUY"

        twap_open, vwap_open = _benchmark_fill(
            ticks, pos["ts_opened"], entry_side, exec_window_seconds
        )
        twap_close, vwap_close = _benchmark_fill(
            ticks, pos["ts_closed"], exit_side, exec_window_seconds
        )

        if None in (twap_open, vwap_open, twap_close, vwap_close):
            continue

        open_px = float(pos["avg_px_open"])
        close_px = float(pos["avg_px_close"])

        strategy_net += (close_px - open_px) * direction * qty
        twap_net += (twap_close - twap_open) * direction * qty
        vwap_net += (vwap_close - vwap_open) * direction * qty
        counted += 1

    if counted == 0:
        return base

    def _vs(strat: float, bench: float) -> float | None:
        if bench == 0:
            return None
        return (strat - bench) / abs(bench) * 100.0

    return {
        "twap_net_pnl": twap_net,
        "vwap_net_pnl": vwap_net,
        "vs_twap_pct": _vs(strategy_net, twap_net),
        "vs_vwap_pct": _vs(strategy_net, vwap_net),
        "benchmark_trade_count": counted,
        "exec_window_seconds": exec_window_seconds,
    }
