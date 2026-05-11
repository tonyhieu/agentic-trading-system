"""Implementation Shortfall against arrival mid.

Computed post-hoc from the same QuoteTicks that fed the backtest, so any
execution algo gets IS for free without instrumentation. For each order we
look up the most recent quote at or before its `ts_init` (decision time,
before the exec algo touches it) and report:

  - arrival_mid:    (bid + ask) / 2 from that quote
  - is_price:       (fill_px - arrival_mid) * dir, in instrument price units
  - is_bps:         is_price / arrival_mid * 10_000

Sign convention: positive IS = adverse for the trader. The qty-weighted
mean (`is_weighted_bps`) is the canonical objective an execution algo
should minimize.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from nautilus_trader.model.data import QuoteTick
except ImportError:  # nautilus is optional at metric-computation time
    QuoteTick = None  # type: ignore[misc,assignment]


def _build_quote_index(ticks: list) -> tuple[np.ndarray, np.ndarray] | None:
    if QuoteTick is None or not ticks:
        return None

    ts_list: list[int] = []
    mid_list: list[float] = []
    for t in ticks:
        if not isinstance(t, QuoteTick):
            continue
        ts_list.append(int(t.ts_event))
        mid_list.append((t.bid_price.as_double() + t.ask_price.as_double()) / 2.0)

    if not ts_list:
        return None

    ts = np.asarray(ts_list, dtype=np.int64)
    mid = np.asarray(mid_list, dtype=np.float64)
    if not np.all(ts[:-1] <= ts[1:]):
        order = np.argsort(ts, kind="stable")
        ts, mid = ts[order], mid[order]
    return ts, mid


def _lookup(target_ns: np.ndarray, qts: np.ndarray, qmid: np.ndarray) -> np.ndarray:
    """For each target_ns, return mid from rightmost qts <= target, else NaN."""
    idx = np.searchsorted(qts, target_ns, side="right") - 1
    safe_idx = np.clip(idx, 0, len(qmid) - 1)
    return np.where(idx >= 0, qmid[safe_idx], np.nan)


_EMPTY: dict[str, float | int | None] = {
    "arrival_mid_captured": 0,
    "arrival_mid_total": 0,
    "is_mean_bps": None,
    "is_weighted_bps": None,
    "is_max_bps": None,
    "is_min_bps": None,
    "is_total_price": None,
}


def attach_implementation_shortfall(
    orders: pd.DataFrame,
    ticks: list,
) -> tuple[pd.DataFrame, dict[str, float | int | None]]:
    """Augment orders with IS columns and return summary metrics."""
    if orders.empty:
        return orders, dict(_EMPTY)

    quote_index = _build_quote_index(ticks)
    if quote_index is None:
        return orders, dict(_EMPTY)
    qts, qmid = quote_index

    ts_init = pd.to_numeric(orders.get("ts_init"), errors="coerce").to_numpy(dtype="float64")
    fill_px = pd.to_numeric(orders.get("avg_px"), errors="coerce").to_numpy(dtype="float64")
    qty = pd.to_numeric(orders.get("filled_qty"), errors="coerce").fillna(0.0).to_numpy(dtype="float64")
    sides = orders["side"].astype(str).str.upper().to_numpy() if "side" in orders.columns else np.array([])
    direction = np.where(sides == "BUY", 1.0, np.where(sides == "SELL", -1.0, 0.0))

    arrival_mid = np.full(len(orders), np.nan, dtype="float64")
    valid_ts = ~np.isnan(ts_init)
    if valid_ts.any():
        arrival_mid[valid_ts] = _lookup(ts_init[valid_ts].astype(np.int64), qts, qmid)

    is_price = (fill_px - arrival_mid) * direction
    with np.errstate(divide="ignore", invalid="ignore"):
        is_bps = np.where(arrival_mid > 0, is_price / arrival_mid * 10_000.0, np.nan)

    out = orders.copy()
    out["arrival_mid"] = arrival_mid
    out["is_price"] = is_price
    out["is_bps"] = is_bps

    captured = int(np.sum(~np.isnan(arrival_mid)))
    total = int(len(orders))
    valid = ~np.isnan(is_bps) & (qty > 0) & (direction != 0)
    if not valid.any():
        return out, {**_EMPTY, "arrival_mid_captured": captured, "arrival_mid_total": total}

    weights = qty[valid]
    bps = is_bps[valid]
    return out, {
        "arrival_mid_captured": captured,
        "arrival_mid_total": total,
        "is_mean_bps": float(np.mean(bps)),
        "is_weighted_bps": float(np.average(bps, weights=weights)),
        "is_max_bps": float(np.max(bps)),
        "is_min_bps": float(np.min(bps)),
        "is_total_price": float(np.sum(is_price[valid] * weights)),
    }
