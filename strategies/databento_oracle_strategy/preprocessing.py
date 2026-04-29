"""Offline preprocessing: turn a sorted tick stream into pre-shifted oracle signals.

For each TradeTick at time T we emit an ``OracleSignal`` *also stamped at T* but
carrying the price observed at T + horizon (plus optional Gaussian noise). The
two-pointer sweep keeps this O(N), which matters at full-day CME tick volumes.

This runs on the same ``ticks`` list that ``backtest_engine.data_loader`` pulls
from S3 — there is no separate data path, no live-stream lookahead, and the
output is deterministic given a seed so runs are reproducible.
"""
from __future__ import annotations

import random

from nautilus_trader.model.data import TradeTick

from strategies.databento_oracle_strategy.oracle_signal import OracleSignal


def build_oracle_signals(
    ticks: list,
    horizon_seconds: float,
    sigma: float = 0.0,
    seed: int = 42,
    signal_interval_seconds: float = 0.0,
) -> list[OracleSignal]:
    """Generate one OracleSignal per qualifying TradeTick.

    Parameters
    ----------
    ticks : list
        Mixed Nautilus data (e.g. trade + quote ticks) returned by the loader.
        Non-``TradeTick`` items are ignored. Must be sorted by ``ts_event``.
    horizon_seconds : float
        How far in the future to look for the "oracle" price.
    sigma : float
        Stdev of additive Gaussian noise applied to the future price, in price
        units. Use 0 for a perfect oracle; raise it to degrade signal quality.
    seed : int
        Seed for the noise RNG so backtests are reproducible.
    signal_interval_seconds : float
        Minimum gap between successive emitted signals. ``0`` means emit one
        per tick. Useful for taming signal volume on dense streams.
    """
    if horizon_seconds <= 0:
        raise ValueError(f"horizon_seconds must be positive, got {horizon_seconds}")

    horizon_ns = int(horizon_seconds * 1_000_000_000)
    interval_ns = int(signal_interval_seconds * 1_000_000_000)
    rng = random.Random(seed)

    trades: list[TradeTick] = [t for t in ticks if isinstance(t, TradeTick)]
    if not trades:
        return []

    signals: list[OracleSignal] = []
    j = 0
    last_emit_ns = -interval_ns  # ensures the first tick passes the gap check

    for current in trades:
        if interval_ns and current.ts_event - last_emit_ns < interval_ns:
            continue

        target_ts = current.ts_event + horizon_ns
        while j < len(trades) and trades[j].ts_event < target_ts:
            j += 1
        if j >= len(trades):
            break

        future_price = float(trades[j].price)
        if sigma > 0.0:
            future_price += rng.gauss(0.0, sigma)

        signals.append(
            OracleSignal(
                instrument_id=current.instrument_id,
                current_price=float(current.price),
                future_price=future_price,
                ts_event=current.ts_event,
                ts_init=current.ts_init,
            )
        )
        last_emit_ns = current.ts_event

    return signals
