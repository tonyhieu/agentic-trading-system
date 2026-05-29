"""EDA for sip-afg-l2 Step 3 — confront each candidate with train-window data.

Loads two non-adjacent train dates (20260308, 20260315), filters to MESM6
TradeTicks, and produces one concrete number/result per candidate.
"""
from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest_engine.data_loader import load_dbn_partition
from nautilus_trader.model.data import TradeTick, QuoteTick
from nautilus_trader.model.enums import AggressorSide


DATES = ["20260308", "20260315"]
WINDOW_NS = 10 * 1_000_000_000   # 10s window matching base algo
HORIZON_NS = 30 * 1_000_000_000  # oracle horizon = 30s (per config.yaml)
PRICE_DIV = 1_000_000_000  # nautilus internal int → price


def signed(side: AggressorSide, size: float) -> float:
    if side == AggressorSide.BUYER:
        return size
    if side == AggressorSide.SELLER:
        return -size
    return 0.0


def signed_count(side: AggressorSide) -> int:
    if side == AggressorSide.BUYER:
        return 1
    if side == AggressorSide.SELLER:
        return -1
    return 0


def load_trades(date: str) -> list[TradeTick]:
    _inst, ticks = load_dbn_partition(date, "MESM6")
    return [t for t in ticks if isinstance(t, TradeTick)]


def load_quote_midprices(date: str) -> list[tuple[int, float]]:
    """Return sorted list of (ts_event_ns, midprice) tuples from quote ticks."""
    _inst, ticks = load_dbn_partition(date, "MESM6")
    out: list[tuple[int, float]] = []
    for t in ticks:
        if isinstance(t, QuoteTick):
            bid = float(str(t.bid_price))
            ask = float(str(t.ask_price))
            mid = (bid + ask) * 0.5
            out.append((t.ts_event, mid))
    return out


# --------------------------------------------------------------------------
# Candidate A — does volume-flow vs count-flow differ?
# Walk a 10s window across the day; at every "evaluation point" (every trade
# tick) compute net_signed_volume vs net_signed_count and compare gate decisions.
# --------------------------------------------------------------------------

def candidate_a_volume_vs_count(trades: list[TradeTick], date: str) -> dict:
    """Compare gate decisions under volume-flow vs count-flow.

    Gate definitions:
      - Volume gate: |net_signed_volume_in_window| >= VOL_THRESH (2.0)
      - Count  gate: |net_signed_count_in_window|  >= COUNT_THRESH

    We want to know: does net_signed_count agree with net_signed_volume on
    when to gate, or do they disagree often? Disagreement is the necessary
    condition for candidate A to do anything different from the base.

    Strategy: scan all trades (acting as decision-evaluation points). Record
    per evaluation point the signs and magnitudes. We pick COUNT_THRESH = 2
    (parity with VOL_THRESH=2 contracts → "2 net trades net adverse").
    """
    VOL_THRESH = 2.0
    COUNT_THRESH = 2

    deque_v: deque[tuple[int, float]] = deque()
    deque_c: deque[tuple[int, int]] = deque()
    net_v = 0.0
    net_c = 0

    eval_points = 0
    vol_fires = 0
    cnt_fires = 0
    both_fire = 0
    disagreements_signed = 0  # same magnitude exceeded, opposite signs
    only_vol = 0
    only_cnt = 0

    # Track running corr-like quantity
    sum_v = sum_c = sum_v2 = sum_c2 = sum_vc = 0.0

    for t in trades:
        ts = t.ts_event
        size = float(str(t.size))
        side = t.aggressor_side
        sv = signed(side, size)
        sc = signed_count(side)
        deque_v.append((ts, sv))
        deque_c.append((ts, sc))
        net_v += sv
        net_c += sc

        # Prune
        cutoff = ts - WINDOW_NS
        while deque_v and deque_v[0][0] < cutoff:
            _, old_sv = deque_v.popleft()
            net_v -= old_sv
        while deque_c and deque_c[0][0] < cutoff:
            _, old_sc = deque_c.popleft()
            net_c -= old_sc

        eval_points += 1
        v_fire = abs(net_v) >= VOL_THRESH
        c_fire = abs(net_c) >= COUNT_THRESH
        if v_fire:
            vol_fires += 1
        if c_fire:
            cnt_fires += 1
        if v_fire and c_fire:
            both_fire += 1
            if (net_v < 0) != (net_c < 0):
                disagreements_signed += 1
        elif v_fire and not c_fire:
            only_vol += 1
        elif c_fire and not v_fire:
            only_cnt += 1

        sum_v += net_v
        sum_c += net_c
        sum_v2 += net_v * net_v
        sum_c2 += net_c * net_c
        sum_vc += net_v * net_c

    if eval_points >= 2:
        n = eval_points
        mean_v = sum_v / n
        mean_c = sum_c / n
        var_v = sum_v2 / n - mean_v * mean_v
        var_c = sum_c2 / n - mean_c * mean_c
        cov_vc = sum_vc / n - mean_v * mean_c
        if var_v > 0 and var_c > 0:
            corr = cov_vc / (var_v ** 0.5 * var_c ** 0.5)
        else:
            corr = float("nan")
    else:
        corr = float("nan")

    return {
        "date": date,
        "eval_points": eval_points,
        "vol_fires": vol_fires,
        "cnt_fires": cnt_fires,
        "both_fire": both_fire,
        "disagreements_signed": disagreements_signed,
        "only_vol": only_vol,
        "only_cnt": only_cnt,
        "corr_net_v_net_c": corr,
        "agreement_rate_when_either_fires": (
            both_fire / (both_fire + only_vol + only_cnt)
            if (both_fire + only_vol + only_cnt) > 0
            else float("nan")
        ),
    }


# --------------------------------------------------------------------------
# Candidate B — does drift conditional on |net_flow| concentrate in the tail?
# Walk window, at each trade time record net_v and the realized 30s-ahead
# midprice drift. Bin by |net_v| quantile and compare mean/median absolute drift.
# --------------------------------------------------------------------------

def candidate_b_tail_premium(trades: list[TradeTick], quotes: list[tuple[int, float]], date: str) -> dict:
    """For each trade timestamp, record (net_v, signed_drift_30s).

    signed_drift = mid(t+30s) - mid(t), signed in the direction opposite to
    net_v so positive drift means "adverse for someone entering with net_v
    flow against the move". Equivalently: if net_v > 0 (buyer-dominated),
    then a future BUY entry could face adverse drift = mid(t+30s) - mid(t).
    But the gate fires to skip SELL when net_v >= +THRESH. So the predictive
    target of |net_v| is the magnitude of the future price move; we bin
    |net_v| and report mean / 90th-percentile |drift|.
    """
    if not quotes:
        return {"date": date, "skipped": "no quotes"}

    # Need quick lookup: mid at time t (use last quote at or before t)
    qs_ts = [q[0] for q in quotes]
    qs_mid = [q[1] for q in quotes]
    nq = len(qs_ts)

    import bisect

    def mid_at(ts: int) -> float | None:
        i = bisect.bisect_right(qs_ts, ts) - 1
        if i < 0:
            return None
        return qs_mid[i]

    deque_v: deque[tuple[int, float]] = deque()
    net_v = 0.0
    records: list[tuple[float, float]] = []  # (|net_v|, |drift|)
    signed_records: list[tuple[float, float]] = []  # (net_v, signed_drift_in_flow_direction)

    for t in trades:
        ts = t.ts_event
        size = float(str(t.size))
        side = t.aggressor_side
        sv = signed(side, size)
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
        drift = m_fut - m_now
        records.append((abs(net_v), abs(drift)))
        # signed_drift_in_flow_direction: positive means price moved further in flow direction
        # (continuation), negative means reversion. Sign of net_v determines what's "forward".
        if net_v > 0:
            signed_records.append((net_v, drift))
        elif net_v < 0:
            signed_records.append((net_v, -drift))
        else:
            signed_records.append((net_v, 0.0))

    # Bin |net_v| into deciles and compute mean |drift| per decile
    if not records:
        return {"date": date, "skipped": "no records"}

    records.sort(key=lambda x: x[0])
    n = len(records)
    deciles = []
    for d in range(10):
        lo = int(d * n / 10)
        hi = int((d + 1) * n / 10)
        if hi > lo:
            chunk = records[lo:hi]
            abs_v = sum(c[0] for c in chunk) / len(chunk)
            abs_drift = sum(c[1] for c in chunk) / len(chunk)
            deciles.append({"decile": d, "n": len(chunk), "mean_abs_net_v": abs_v, "mean_abs_drift": abs_drift})

    # Specifically compare: mean |drift| above |net_v|=p90 vs below p90
    abs_vs = sorted([r[0] for r in records])
    p90 = abs_vs[int(0.9 * n)] if n > 0 else 0
    tail = [r for r in records if r[0] >= p90]
    body = [r for r in records if r[0] < p90]
    mean_drift_tail = sum(r[1] for r in tail) / max(len(tail), 1)
    mean_drift_body = sum(r[1] for r in body) / max(len(body), 1)

    # Signed flow continuation: for net_v > 0 records, mean drift_in_flow_dir
    pos = [r[1] for r in signed_records if r[0] > 0]
    neg = [r[1] for r in signed_records if r[0] < 0]
    return {
        "date": date,
        "n_records": n,
        "p90_abs_net_v": p90,
        "mean_abs_drift_tail_pct_p90+": mean_drift_tail,
        "mean_abs_drift_body_below_p90": mean_drift_body,
        "tail_premium_ratio": (mean_drift_tail / mean_drift_body) if mean_drift_body > 0 else float("nan"),
        "deciles": deciles,
        "n_pos_flow": len(pos),
        "mean_continuation_pos_flow": (sum(pos) / len(pos)) if pos else float("nan"),
        "n_neg_flow": len(neg),
        "mean_continuation_neg_flow": (sum(neg) / len(neg)) if neg else float("nan"),
    }


# --------------------------------------------------------------------------
# Candidate C — is conditional drift asymmetric by side?
# Bin trade-time observations by sign(net_v); compute the mean 30s-ahead drift
# separately for net_v > 0 (buyer-dominated) and net_v < 0 (seller-dominated).
# An asymmetric guard is only useful if these two are meaningfully different.
# --------------------------------------------------------------------------

def candidate_c_side_asymmetry(trades: list[TradeTick], quotes: list[tuple[int, float]], date: str) -> dict:
    if not quotes:
        return {"date": date, "skipped": "no quotes"}

    qs_ts = [q[0] for q in quotes]
    qs_mid = [q[1] for q in quotes]
    nq = len(qs_ts)

    import bisect

    def mid_at(ts: int) -> float | None:
        i = bisect.bisect_right(qs_ts, ts) - 1
        if i < 0:
            return None
        return qs_mid[i]

    deque_v: deque[tuple[int, float]] = deque()
    net_v = 0.0

    # Use base algo's threshold (>= 2 contracts adverse)
    THRESH = 2.0

    # Group A: net_v <= -THRESH (sell-dominated, would gate BUY orders)
    # → record forward drift; if BUY entry skipped, what would the *post* drift
    #   look like? Negative drift means market continues down, BUY was right to skip.
    sell_dom_drifts: list[float] = []
    buy_dom_drifts: list[float] = []

    for t in trades:
        ts = t.ts_event
        size = float(str(t.size))
        side = t.aggressor_side
        sv = signed(side, size)
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
        drift = m_fut - m_now  # absolute, signed: positive = up
        if net_v <= -THRESH:
            # sell-dominated. A BUY order placed here would face adverse drift if drift < 0
            # adverse_for_buy = -drift  (positive number means adverse)
            sell_dom_drifts.append(-drift)
        elif net_v >= THRESH:
            # buy-dominated. A SELL order placed here would face adverse drift if drift > 0
            buy_dom_drifts.append(drift)

    def stats(xs):
        if not xs:
            return {"n": 0}
        n = len(xs)
        mean = sum(xs) / n
        xs_sorted = sorted(xs)
        median = xs_sorted[n // 2]
        return {"n": n, "mean_adverse_drift": mean, "median_adverse_drift": median}

    return {
        "date": date,
        "buy_orders_adverse_when_sell_dominated_flow": stats(sell_dom_drifts),
        "sell_orders_adverse_when_buy_dominated_flow": stats(buy_dom_drifts),
    }


def main() -> None:
    print("=" * 70)
    print("EDA for sip-afg-l2 Step 3 — confronting candidates with train data")
    print("=" * 70)
    for date in DATES:
        print(f"\n--- DATE {date} ---")
        trades = load_trades(date)
        quotes = load_quote_midprices(date)
        print(f"Loaded {len(trades)} trade ticks, {len(quotes)} quote ticks.")

        print("\n[Candidate A] volume-flow vs count-flow agreement")
        rA = candidate_a_volume_vs_count(trades, date)
        for k, v in rA.items():
            print(f"  {k}: {v}")

        print("\n[Candidate B] tail-premium of |net_v| → |drift_30s|")
        rB = candidate_b_tail_premium(trades, quotes, date)
        for k, v in rB.items():
            if k == "deciles":
                print(f"  {k}:")
                for d in v:
                    print(f"    d={d['decile']:>2}: n={d['n']:>4}  mean_abs_net_v={d['mean_abs_net_v']:6.2f}  mean_abs_drift={d['mean_abs_drift']:6.3f}")
            else:
                print(f"  {k}: {v}")

        print("\n[Candidate C] side asymmetry of adverse drift")
        rC = candidate_c_side_asymmetry(trades, quotes, date)
        for k, v in rC.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
