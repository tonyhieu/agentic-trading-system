"""Per-skip counterfactual P&L attribution.

When an execution algorithm declines to submit an OPEN order, it can call
``SkipRecorder.record(...)`` with the parent-order metadata and the
top-of-book quote captured at the skip site. After ``engine.run()`` the
backtest pipeline calls :func:`attach_skip_attribution`, which:

  * Simulates the counterfactual entry fill at top-of-book (ask for BUY,
    bid for SELL) at the skip's ``ts_event``.
  * Looks up the mid ``horizon_seconds`` after the skip and uses that as
    the would-be exit price. The horizon defaults to the oracle
    strategy's signal lifetime so the counterfactual mirrors a single
    strategy decision cycle.
  * Computes per-skip would-be P&L in price units and bps, tags each by
    direction (BUY/SELL) and magnitude bucket
    (negative / near_zero / positive), and aggregates a per-date summary.

The resulting ``skipped_attribution.json`` lets the researcher
distinguish "we precisely skipped losers" (negative-bucket dominates)
from "we just removed volume" (flat distribution across buckets).
Reference: GitHub issue #66.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtest_engine.arrival_price import _build_quote_index, _lookup

# Default counterfactual exit horizon, in seconds. Matches the oracle
# strategy's default `horizon_seconds`, so a "would-be PnL" reflects one
# full signal lifetime rather than a microstructure tick. Override via
# `attach_skip_attribution(..., horizon_seconds=...)`.
DEFAULT_HORIZON_SECONDS: float = 30.0

# |would-be P&L| / arrival_mid below this threshold (in bps) is bucketed
# as "near_zero". 1 bps on a $4500 MES future ≈ $0.45 per contract — well
# inside one tick of price noise, so anything tighter is signal-free.
NEAR_ZERO_BPS: float = 1.0


@dataclass
class SkipEvent:
    """A single skip decision captured at the algorithm's skip site.

    All prices are in the instrument's quote currency. ``ts_event`` is
    nanoseconds since the Unix epoch (Nautilus convention).
    """

    ts_event: int
    instrument_id: str
    parent_order_id: str
    side: str
    quantity: float
    bid: float
    ask: float
    trigger: str | None = None


@dataclass
class SkipRecorder:
    """Append-only buffer of :class:`SkipEvent`. One per backtest run.

    Construct it in the backtest harness, pass it into the execution
    algorithm factory via ``skip_recorder=...``, and call
    :func:`attach_skip_attribution` after ``engine.run()`` returns.
    """

    events: list[SkipEvent] = field(default_factory=list)

    def record(
        self,
        *,
        ts_event: int,
        instrument_id: Any,
        parent_order_id: Any,
        side: str,
        quantity: float,
        bid: float,
        ask: float,
        trigger: str | None = None,
    ) -> None:
        self.events.append(
            SkipEvent(
                ts_event=int(ts_event),
                instrument_id=str(instrument_id),
                parent_order_id=str(parent_order_id),
                side=str(side).upper(),
                quantity=float(quantity),
                bid=float(bid),
                ask=float(ask),
                trigger=str(trigger) if trigger is not None else None,
            )
        )

    def to_frame(self) -> pd.DataFrame:
        cols = [
            "ts_event", "instrument_id", "parent_order_id",
            "side", "quantity", "bid", "ask", "trigger",
        ]
        if not self.events:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([{c: getattr(e, c) for c in cols} for e in self.events])


_EMPTY_SUMMARY: dict[str, Any] = {
    "skipped_count": 0,
    "attributed_count": 0,
    "would_be_pnl_distribution": {"negative": 0, "near_zero": 0, "positive": 0},
    "would_be_pnl_total": 0.0,
    "precision": None,
    "recall": None,
    "horizon_seconds": None,
}


def _bucket_label(pnl_bps: float) -> str:
    if math.isnan(pnl_bps):
        return "unattributed"
    if pnl_bps > NEAR_ZERO_BPS:
        return "positive"
    if pnl_bps < -NEAR_ZERO_BPS:
        return "negative"
    return "near_zero"


def attach_skip_attribution(
    recorder: SkipRecorder,
    ticks: list,
    *,
    horizon_seconds: float = DEFAULT_HORIZON_SECONDS,
    multiplier: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compute counterfactual P&L for every skip event.

    For each skip we look up two mids from the quote stream:
      * ``entry_mid`` — mid at the skip ``ts_event`` (sanity check).
      * ``exit_mid``  — mid at ``ts_event + horizon_seconds`` (the
        counterfactual exit). When the horizon walks off the end of the
        day's tick stream, the skip is reported with NaN P&L and is
        excluded from the precision tally.

    Sign convention: ``would_be_pnl > 0`` means the skipped trade would
    have made money — i.e. the skip filter rejected a *winner*. Lots of
    negative-bucket skips means the filter precisely targets losers;
    a flat distribution means the filter just removes volume.
    """
    skips = recorder.to_frame()
    if skips.empty:
        return skips, {**_EMPTY_SUMMARY, "horizon_seconds": float(horizon_seconds)}

    quote_index = _build_quote_index(ticks)
    skips = skips.sort_values("ts_event").reset_index(drop=True)

    skip_ts = skips["ts_event"].to_numpy(dtype=np.int64)
    sides = skips["side"].to_numpy()
    qty = skips["quantity"].to_numpy(dtype=np.float64)
    direction = np.where(sides == "BUY", 1.0, np.where(sides == "SELL", -1.0, 0.0))

    # Counterfactual entry: top-of-book on the same tick (ask for BUY,
    # bid for SELL). This is what the skipped order would have filled at
    # under the `top_of_book_only` execution constraint.
    entry_fill = np.where(
        sides == "BUY",
        skips["ask"].to_numpy(dtype=np.float64),
        skips["bid"].to_numpy(dtype=np.float64),
    )

    if quote_index is None:
        entry_mid = np.full(len(skips), np.nan)
        exit_mid = np.full(len(skips), np.nan)
    else:
        qts, qmid = quote_index
        entry_mid = _lookup(skip_ts, qts, qmid)
        horizon_ns = int(horizon_seconds * 1_000_000_000)
        exit_target = skip_ts + horizon_ns
        exit_mid = _lookup(exit_target, qts, qmid)
        # _lookup returns the rightmost mid <= target. If the target
        # walks past the last tick of the day, every skip past that
        # point gets the same final mid, which is a degenerate
        # extrapolation rather than a real counterfactual. Mask those.
        last_ts = int(qts[-1])
        exit_mid = np.where(exit_target > last_ts, np.nan, exit_mid)

    would_be_pnl = (exit_mid - entry_fill) * direction * qty * float(multiplier)
    with np.errstate(divide="ignore", invalid="ignore"):
        pnl_bps = np.where(
            entry_mid > 0,
            (exit_mid - entry_fill) * direction / entry_mid * 10_000.0,
            np.nan,
        )

    skips["entry_mid"] = entry_mid
    skips["entry_fill"] = entry_fill
    skips["exit_mid"] = exit_mid
    skips["would_be_pnl"] = would_be_pnl
    skips["would_be_pnl_bps"] = pnl_bps
    skips["bucket"] = [_bucket_label(x) for x in pnl_bps]

    attributed = skips["bucket"] != "unattributed"
    buckets = {
        "negative":  int(((skips["bucket"] == "negative") & attributed).sum()),
        "near_zero": int(((skips["bucket"] == "near_zero") & attributed).sum()),
        "positive":  int(((skips["bucket"] == "positive") & attributed).sum()),
    }
    attributed_count = int(attributed.sum())
    precision = (buckets["negative"] / attributed_count) if attributed_count > 0 else None
    pnl_total = float(np.nansum(would_be_pnl))

    summary = {
        "skipped_count": int(len(skips)),
        "attributed_count": attributed_count,
        "would_be_pnl_distribution": buckets,
        "would_be_pnl_total": pnl_total,
        # Fraction of attributed skips that the filter correctly rejected
        # (would have been losers). `recall` requires a comparable
        # denominator over the actual losers in the un-skipped trades and
        # is left None for now — adding it requires pairing skip events
        # with the trade-level realized P&L distribution, which is a
        # separate piece of infrastructure (see issue #66 schema).
        "precision": float(precision) if precision is not None else None,
        "recall": None,
        "horizon_seconds": float(horizon_seconds),
    }
    return skips, summary
