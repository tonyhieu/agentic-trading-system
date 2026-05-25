"""EDA for afg-pc-r3: characterize |net_flow| distribution at gate-firing moments.

Uses Nautilus's DatabentoDataLoader to read the partitioned DBN, then walks
trade ticks chronologically maintaining a 10s rolling signed-aggressor-flow
deque (identical to base AFG). Samples |net_flow| every 1s and reports the
empirical distribution among samples where the gate would have fired
(|net_flow| >= 2.0). Informs strong_threshold for the magnitude-conditional
chained gate.
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from nautilus_trader.adapters.databento import DatabentoDataLoader
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

DATES = ["20260308", "20260316"]
WINDOW_NS = 10 * 1_000_000_000
THRESHOLD = 2.0
SAMPLE_INTERVAL_NS = 1_000_000_000


def main() -> None:
    out: dict = {}
    loader = DatabentoDataLoader()

    for date in DATES:
        dbn_path = Path(
            f"data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date={date}/data.dbn.zst"
        )
        if not dbn_path.exists():
            print(f"MISSING: {dbn_path}", file=sys.stderr)
            continue
        print(f"\n=== {date} ===", file=sys.stderr)

        data = loader.from_dbn_file(
            path=str(dbn_path),
            include_trades=True,
        )
        # Filter to TradeTick objects only
        trades = [d for d in data if type(d).__name__ == "TradeTick"]
        print(f"  trade ticks: {len(trades)}", file=sys.stderr)
        if not trades:
            continue

        # Build chronological (ts_event, signed_vol) arrays
        ts_event = np.array([int(t.ts_event) for t in trades], dtype=np.int64)
        sizes = np.array([float(str(t.size)) for t in trades], dtype=np.float64)
        agg = np.array([int(t.aggressor_side) for t in trades], dtype=np.int8)
        # AggressorSide enum: BUYER=1, SELLER=2, NO_AGGRESSOR=0
        signed = np.where(agg == 1, sizes, np.where(agg == 2, -sizes, 0.0))

        # Sort defensively (DBN is usually sorted but be safe)
        order = np.argsort(ts_event, kind="stable")
        ts_event = ts_event[order]
        signed = signed[order]

        # Sample net_flow every 1s.
        start_ns = int(ts_event[0]) + WINDOW_NS
        end_ns = int(ts_event[-1])
        sample_times = np.arange(start_ns, end_ns, SAMPLE_INTERVAL_NS)

        net_flows = []
        for t in sample_times:
            lo = np.searchsorted(ts_event, t - WINDOW_NS, side="left")
            hi = np.searchsorted(ts_event, t, side="right")
            if hi <= lo:
                continue
            net_flows.append(float(signed[lo:hi].sum()))
        net_flows = np.array(net_flows)

        abs_nf = np.abs(net_flows)
        fired = abs_nf[abs_nf >= THRESHOLD]
        total = len(net_flows)
        n_fired = len(fired)

        stats = {
            "n_samples": int(total),
            "n_fired_at_2.0": int(n_fired),
            "fire_rate_pct": float(n_fired / max(total, 1) * 100),
            "fired_pctiles": {
                p: float(np.percentile(fired, int(p[1:]))) if n_fired else None
                for p in ["p50", "p70", "p80", "p90", "p95", "p99"]
            },
            "fired_max": float(fired.max()) if n_fired else None,
            "fired_share_above": {
                str(thr): float((fired >= thr).sum() / max(n_fired, 1) * 100)
                for thr in [3, 4, 5, 6, 7, 8, 10, 12, 15, 20]
            },
        }
        out[date] = stats
        print(json.dumps({date: stats}, indent=2), file=sys.stderr)

    out_path = Path(
        "experiments/proposer_criticizer_experiment/aggressor-flow-gate/run-3/eda_results.json"
    )
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
