"""Focused EDA: at the EXACT gating boundary of the base algo, does tail
have a different drift than just-above-threshold?

Also: pool both train dates and recompute side-asymmetry to check whether
the side asymmetry is day-specific or aggregate-positive.
"""
from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path
import bisect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest_engine.data_loader import load_dbn_partition
from nautilus_trader.model.data import TradeTick, QuoteTick
from nautilus_trader.model.enums import AggressorSide


DATES = ["20260308", "20260309", "20260315", "20260318"]
WINDOW_NS = 10 * 1_000_000_000
HORIZON_NS = 30 * 1_000_000_000
THRESH = 2.0


def signed(side: AggressorSide, size: float) -> float:
    if side == AggressorSide.BUYER:
        return size
    if side == AggressorSide.SELLER:
        return -size
    return 0.0


def load_one(date: str):
    _inst, ticks = load_dbn_partition(date, "MESM6")
    trades = [t for t in ticks if isinstance(t, TradeTick)]
    quotes = []
    for t in ticks:
        if isinstance(t, QuoteTick):
            bid = float(str(t.bid_price))
            ask = float(str(t.ask_price))
            quotes.append((t.ts_event, (bid + ask) * 0.5))
    return trades, quotes


def compute_drifts_at_thresholds(trades, quotes, date):
    qs_ts = [q[0] for q in quotes]
    qs_mid = [q[1] for q in quotes]

    def mid_at(ts):
        i = bisect.bisect_right(qs_ts, ts) - 1
        if i < 0:
            return None
        return qs_mid[i]

    deque_v: deque[tuple[int, float]] = deque()
    net_v = 0.0

    # Per evaluation point (each trade), record net_v at that time and drift
    records = []  # (net_v, drift)
    for t in trades:
        ts = t.ts_event
        size = float(str(t.size))
        sv = signed(t.aggressor_side, size)
        deque_v.append((ts, sv))
        net_v += sv
        cutoff = ts - WINDOW_NS
        while deque_v and deque_v[0][0] < cutoff:
            _, old_sv = deque_v.popleft()
            net_v -= old_sv

        m_now = mid_at(ts)
        m_fut = mid_at(ts + HORIZON_NS)
        if m_now is None or m_fut is None:
            continue
        records.append((net_v, m_fut - m_now))

    if not records:
        return None

    # Buckets relative to base-algo gate
    sell_dom = [r for r in records if r[0] <= -THRESH]  # gates BUY
    buy_dom = [r for r in records if r[0] >= THRESH]    # gates SELL
    neutral = [r for r in records if -THRESH < r[0] < THRESH]

    # For BUY-skip: if drift < 0 (price went down), skip was correct (BUY would have lost)
    # The metric "mean adverse drift for BUY" = -mean(drift) in sell_dom periods
    # → positive means skip was good on average
    if sell_dom:
        buy_skip_value = -sum(r[1] for r in sell_dom) / len(sell_dom)
    else:
        buy_skip_value = float("nan")
    # For SELL-skip: if drift > 0 (price went up), skip was correct (SELL would have lost)
    # mean(drift) in buy_dom
    if buy_dom:
        sell_skip_value = sum(r[1] for r in buy_dom) / len(buy_dom)
    else:
        sell_skip_value = float("nan")

    # Magnitude-conditional: split sell_dom into "moderate" (-3 < net_v <= -2) vs "extreme" (net_v <= -10)
    sell_dom_mod = [r for r in records if -3 <= r[0] <= -THRESH]
    sell_dom_ext = [r for r in records if r[0] <= -10]
    buy_dom_mod = [r for r in records if THRESH <= r[0] <= 3]
    buy_dom_ext = [r for r in records if r[0] >= 10]

    return {
        "date": date,
        "n_records": len(records),
        "n_sell_dom": len(sell_dom),
        "n_buy_dom": len(buy_dom),
        "n_neutral": len(neutral),
        "buy_skip_value_mean": buy_skip_value,
        "sell_skip_value_mean": sell_skip_value,
        "moderate_sell_dom_n": len(sell_dom_mod),
        "moderate_sell_dom_buy_skip_value": (
            -sum(r[1] for r in sell_dom_mod) / max(len(sell_dom_mod), 1)
        ),
        "extreme_sell_dom_n": len(sell_dom_ext),
        "extreme_sell_dom_buy_skip_value": (
            -sum(r[1] for r in sell_dom_ext) / max(len(sell_dom_ext), 1)
        ),
        "moderate_buy_dom_n": len(buy_dom_mod),
        "moderate_buy_dom_sell_skip_value": (
            sum(r[1] for r in buy_dom_mod) / max(len(buy_dom_mod), 1)
        ),
        "extreme_buy_dom_n": len(buy_dom_ext),
        "extreme_buy_dom_sell_skip_value": (
            sum(r[1] for r in buy_dom_ext) / max(len(buy_dom_ext), 1)
        ),
    }


def main():
    print("=" * 70)
    print("Focused EDA — base-algo gate boundary + magnitude conditional")
    print("=" * 70)
    pooled_buy_skip = []
    pooled_sell_skip = []
    pooled_mod_buy_skip = []
    pooled_ext_buy_skip = []
    pooled_mod_sell_skip = []
    pooled_ext_sell_skip = []
    for date in DATES:
        trades, quotes = load_one(date)
        print(f"\n--- {date} ({len(trades)} trades, {len(quotes)} quotes) ---")
        r = compute_drifts_at_thresholds(trades, quotes, date)
        for k, v in r.items():
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")

        # Re-walk to extract raw drift lists for pooling
        qs_ts = [q[0] for q in quotes]
        qs_mid = [q[1] for q in quotes]
        def mid_at(ts):
            i = bisect.bisect_right(qs_ts, ts) - 1
            if i < 0:
                return None
            return qs_mid[i]
        deque_v: deque[tuple[int, float]] = deque()
        net_v = 0.0
        for t in trades:
            ts = t.ts_event
            size = float(str(t.size))
            sv = signed(t.aggressor_side, size)
            deque_v.append((ts, sv))
            net_v += sv
            cutoff = ts - WINDOW_NS
            while deque_v and deque_v[0][0] < cutoff:
                _, old_sv = deque_v.popleft()
                net_v -= old_sv
            m_now = mid_at(ts)
            m_fut = mid_at(ts + HORIZON_NS)
            if m_now is None or m_fut is None:
                continue
            d = m_fut - m_now
            if net_v <= -THRESH:
                pooled_buy_skip.append(-d)
            if net_v >= THRESH:
                pooled_sell_skip.append(d)
            if -3 <= net_v <= -THRESH:
                pooled_mod_buy_skip.append(-d)
            if net_v <= -10:
                pooled_ext_buy_skip.append(-d)
            if THRESH <= net_v <= 3:
                pooled_mod_sell_skip.append(d)
            if net_v >= 10:
                pooled_ext_sell_skip.append(d)

    print("\n" + "=" * 70)
    print("POOLED across 4 dates")
    print("=" * 70)
    def stats(name, xs):
        if not xs:
            print(f"  {name}: (none)")
            return
        n = len(xs)
        mean = sum(xs) / n
        # SE of mean
        var = sum((x - mean) ** 2 for x in xs) / max(n - 1, 1)
        se = (var / n) ** 0.5
        print(f"  {name}: n={n:>6}, mean_skip_value={mean:+.4f} (se={se:.4f}, t={mean/se if se>0 else 0:+.2f})")

    print("\nAll gating events:")
    stats("buy_skip_value  (net_v <= -2)", pooled_buy_skip)
    stats("sell_skip_value (net_v >= +2)", pooled_sell_skip)
    print("\nMagnitude-conditional split:")
    stats("buy_skip moderate (-3 <= net_v <= -2)", pooled_mod_buy_skip)
    stats("buy_skip extreme  (net_v <= -10)     ", pooled_ext_buy_skip)
    stats("sell_skip moderate (2 <= net_v <= 3)", pooled_mod_sell_skip)
    stats("sell_skip extreme  (net_v >= 10)    ", pooled_ext_sell_skip)


if __name__ == "__main__":
    main()
