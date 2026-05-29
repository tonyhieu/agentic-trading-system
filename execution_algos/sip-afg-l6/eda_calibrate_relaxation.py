"""EDA for sip-afg-l6: calibrate sip-afg-l5's `relaxation_factor`.

Measurement protocol (matches NOTES.md → Calibration Target):
  1. Load TradeTick objects for two train dates via the project's
     `backtest_engine/data_loader.py` (which uses Nautilus's
     `DatabentoDataLoader`).
  2. Build a synthetic order-arrival stream at 1 Hz (oracle's
     signal_interval_seconds = 1.0). Session bounds are the first/last
     trade ts_event in the day.
  3. Replay events chronologically. At each synthetic arrival, prune
     the 10s aggressor-flow deque, compute net_flow, and decide whether
     the BASE aggressor-flow-gate would skip — using the worst-case
     side (whichever side's gate would fire on this snapshot). After a
     skip the base sets ``_position_flat = True`` and the next arrival
     is a forced submit (not evaluated).
  4. For each base-skip event, record |net_flow| at the very next
     synthetic arrival (1 s later). This is the calibration
     distribution.
  5. Current effective threshold (3.0 = 2.0 * 1.5) → current firing
     rate = Pr(|next_net_flow| >= 3.0). Target = 0.30 (pre-committed).
     Calibrated effective threshold = 70th percentile of the
     |next_net_flow| distribution. Calibrated relaxation =
     calibrated_threshold / 2.0.

No look-ahead bias: at each arrival only trades with
``tick.ts_event <= arrival_ts`` are in the deque (replay is
chronological).

Train dates only — leakage rule enforced (20260309 and 20260311 are
both in ``data_window.train`` = [2026-03-08, 2026-03-21]).
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backtest_engine.data_loader import load_dbn_partition

from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide


WINDOW_NS = 10 * 1_000_000_000          # 10s rolling window for aggressor flow
FLOW_THRESHOLD = 2.0                     # base flow_threshold (contracts)
ARRIVAL_INTERVAL_NS = 1_000_000_000      # 1.0s oracle cadence

TRAIN_DATES = ["20260309", "20260311"]   # 2 train dates per spec
SYMBOL = "MESM6"


def extract_trade_ticks(ticks) -> list[tuple[int, float]]:
    """Filter raw Nautilus data to TradeTick → (ts_event_ns, signed_vol)."""
    out: list[tuple[int, float]] = []
    for t in ticks:
        if not isinstance(t, TradeTick):
            continue
        size = float(str(t.size))
        if t.aggressor_side == AggressorSide.BUYER:
            sv = size
        elif t.aggressor_side == AggressorSide.SELLER:
            sv = -size
        else:
            sv = 0.0
        out.append((int(t.ts_event), sv))
    out.sort(key=lambda x: x[0])
    return out


def simulate_base_with_next_flow(trade_ticks: list[tuple[int, float]]):
    """Simulate the BASE aggressor-flow-gate on a 1Hz arrival stream.

    Returns:
      arrivals_abs        — |net_flow| at every arrival
      skip_decisions      — True/False per non-forced arrival (base-skip flag)
      next_after_skip_abs — |net_flow| at the arrival immediately after
                            every base skip
    """
    if not trade_ticks:
        return [], [], []

    session_start_ns = trade_ticks[0][0]
    session_end_ns = trade_ticks[-1][0]

    n_arrivals = max(0, (session_end_ns - session_start_ns) // ARRIVAL_INTERVAL_NS)
    arrival_times = [session_start_ns + i * ARRIVAL_INTERVAL_NS for i in range(int(n_arrivals))]

    flow_deque: deque[tuple[int, float]] = deque()
    net_flow = 0.0
    trade_idx = 0
    n_trades = len(trade_ticks)

    arrivals_abs: list[float] = []
    skip_decisions: list[bool] = []
    skip_indices: list[int] = []

    # Base's _position_flat (binary): True after any skip → next opening
    # order is force-submitted. Initially True (warm-up first order forced).
    position_flat = True

    for i, arrival_ts in enumerate(arrival_times):
        # Drain trades with ts_event <= arrival_ts into the deque.
        while trade_idx < n_trades and trade_ticks[trade_idx][0] <= arrival_ts:
            ts, sv = trade_ticks[trade_idx]
            flow_deque.append((ts, sv))
            net_flow += sv
            trade_idx += 1

        # Prune entries older than the window.
        cutoff = arrival_ts - WINDOW_NS
        while flow_deque and flow_deque[0][0] < cutoff:
            _, old_sv = flow_deque.popleft()
            net_flow -= old_sv

        net = net_flow
        arrivals_abs.append(abs(net))

        if position_flat:
            # Forced re-entry — base does NOT evaluate the gate here.
            position_flat = False
            continue

        # Worst-case adverse side: gate fires when |net_flow| >= threshold
        # in either direction (the side of the order is chosen to be the
        # adverse one).
        if net >= FLOW_THRESHOLD or net <= -FLOW_THRESHOLD:
            skip_decisions.append(True)
            skip_indices.append(i)
            position_flat = True
        else:
            skip_decisions.append(False)
            # position_flat stays False (submitted).

    next_after_skip_abs: list[float] = []
    for si in skip_indices:
        if si + 1 < len(arrivals_abs):
            next_after_skip_abs.append(arrivals_abs[si + 1])

    return arrivals_abs, skip_decisions, next_after_skip_abs


def main() -> None:
    all_next_after_skip: list[float] = []
    per_date: dict[str, dict] = {}

    for date in TRAIN_DATES:
        print(f"[{date}] loading partition...")
        _, ticks = load_dbn_partition(date, SYMBOL)
        trade_ticks = extract_trade_ticks(ticks)
        if not trade_ticks:
            print(f"[{date}] no trade ticks; skipping")
            continue

        arrivals_abs, skip_decisions, next_after_skip = simulate_base_with_next_flow(trade_ticks)
        n_arrivals = len(arrivals_abs)
        n_evaluated = len(skip_decisions)
        n_skips = sum(skip_decisions)
        per_date[date] = {
            "n_trade_ticks": len(trade_ticks),
            "n_synthetic_arrivals": n_arrivals,
            "n_evaluated_for_skip": n_evaluated,
            "n_base_skips": int(n_skips),
            "base_skip_rate_of_evaluated": n_skips / n_evaluated if n_evaluated else 0.0,
            "n_post_skip_next_arrivals": len(next_after_skip),
        }
        all_next_after_skip.extend(next_after_skip)
        print(f"[{date}] trades={len(trade_ticks)}, arrivals={n_arrivals}, "
              f"evaluated_skip_decisions={n_evaluated}, base_skips={n_skips}, "
              f"post_skip_next_arrivals={len(next_after_skip)}")

    if not all_next_after_skip:
        print("ERROR: no post-skip arrivals collected.")
        return

    arr = np.array(all_next_after_skip)
    current_threshold = FLOW_THRESHOLD * 1.5
    current_firing_rate = float(np.mean(arr >= current_threshold))

    target_firing_rate = 0.30
    # P(X >= q) = target → q = quantile at (1 - target).
    calibrated_threshold = float(np.percentile(arr, 100 * (1 - target_firing_rate)))
    calibrated_relaxation = calibrated_threshold / FLOW_THRESHOLD
    delta_pct = abs(calibrated_relaxation - 1.5) / 1.5 * 100

    summary = {
        "dates_analyzed": TRAIN_DATES,
        "per_date": per_date,
        "n_post_skip_samples_total": int(arr.size),
        "next_abs_net_flow_distribution": {
            "mean": float(np.mean(arr)),
            "p10": float(np.percentile(arr, 10)),
            "p25": float(np.percentile(arr, 25)),
            "p50": float(np.percentile(arr, 50)),
            "p70": float(np.percentile(arr, 70)),
            "p75": float(np.percentile(arr, 75)),
            "p80": float(np.percentile(arr, 80)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
        },
        "current_relaxation_factor": 1.5,
        "current_effective_threshold": current_threshold,
        "current_firing_rate": current_firing_rate,
        "target_firing_rate": target_firing_rate,
        "calibrated_effective_threshold": calibrated_threshold,
        "calibrated_relaxation_factor": calibrated_relaxation,
        "abs_pct_delta_vs_current": delta_pct,
        "survival_criterion_passed": bool(delta_pct >= 10.0),
    }

    out = Path(__file__).parent / "results" / "eda-calibration.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
