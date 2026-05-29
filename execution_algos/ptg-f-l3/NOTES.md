# Algorithm Notes: ptg-f-l3

Per-iteration experiment — base_algo `position-tier-gate`, context mode
`full-trace`, loop 3. Starting point: `position-tier-gate` base algo.

## Hypothesis

**Context available (full-trace, loop 3)**: loops 1-2 full_reasoning + NOTES.md.

**Key findings from prior loops**:
- Loop 1 (cap=2): identical to simple. The cap lever is binary: cap=1 = serialized
  entry = best; cap>=2 = no-op = simple baseline.
- Loop 2 (loss-streak gate): identical to base. Any filter at oracle-signal time is
  a no-op because: concurrent opens are blocked by cap=1 anyway; between-oracle opens
  see net_qty=0 and are allowed regardless. The streak gate fires only on between-oracle
  opens but those are always allowed.

**New mechanism for loop 3**: Layer an **aggressor-flow gate** on top of cap=1.
Subscribe to trade ticks and maintain a rolling window of signed aggressor flow.
At each open order: skip if the current flow direction is ADVERSE to the order direction.
This acts between oracle signals (during the flat-position window) and can filter opens
where the current market microstructure is directionally adverse.

The aggressor-flow arm (afg) found that a 30s window with threshold=1 gives +32.59%
vs the afg base. Here, the position gate already filters concurrent entries; the flow
gate would additionally filter entries where the market flow disagrees with the oracle signal.

**Why this might work**: The oracle generates signals every 1 second. Between oracle fires,
the position is flat (thanks to cap=1). The next oracle open arrives in that flat window.
If the current aggressor flow in the 30s preceding the open is ADVERSE (e.g., sellers
dominating for a BUY signal), the flow gate would skip the open. This layering could
reduce adverse-selection entries while still using the position cap to prevent concurrent stacking.

**Risk**: The afg's +32.59% was measured vs the afg BASE, which had baseline trade_count
~107k. The ptg base has only 90k trades (already filtered). Applying the flow gate on top
of the already-filtered 90k trades may reduce trade_count further without proportional P&L
benefit — the remaining trades may already be the "good" ones that the flow gate would pass anyway.

**Builds on**: `position-tier-gate` base algo (cap=1 preserved). Adds: aggressor-flow gate
(window=30s, threshold=1.0). This is a combination of the two mechanisms found best in their
respective arms.

---

## Implementation Decisions

- **`position_cap` = 1**: preserved (binary cliff finding from loop 1).
- **`window_seconds` = 30.0**: best window from the afg arm (loop 7: +32.59% vs afg base).
- **`flow_threshold` = 1.0**: best threshold from the afg arm (integer equivalence class).
- **`_position_flat` anti-cascade**: preserved from afg (submit unconditionally after any skip
  to prevent infinite skipping; but note that for ptg, the position gate already handles
  re-entry post-close).
- **Reduce-only orders**: always submitted (intraday_flat compliance).
- **Look-ahead check**: `on_trade_tick` receives ticks with ts_event <= order.ts_init (replay
  is strictly chronological). The prune uses `order.ts_init - window_ns`, so only past ticks
  are in the deque at decision time.

---

## Backtest Observations

**Full 12-date train window:**

| Metric | ptg-f-l3 (flow+cap) | base (cap=1) |
|---|---|---|
| realized_pnl | $3,525.75 | $4,262.50 |
| vs_base_pnl_pct | **-17.28%** | — |
| sharpe_ratio | 17.401 | 17.619 |
| trade_count | 78,238 | 90,433 |

**What drove underperformance**: The flow gate removes 12,195 trades (-13.5%)
but P&L drops -17.28%. The trades filtered by the flow gate are NOT predominantly
the bad ones — they are a mix of good and bad entries. The position-tier-gate
mechanism at cap=1 already selected the highest-quality subset of oracle entries;
applying an additional flow filter to this already-filtered set removes value
without proportional filtering of adverse trades.

**Hypothesis verdict**: FALSIFIED. Combining flow gate + position gate degrades vs
position gate alone. The position-tier-gate mechanism already selects better trades
than the flow gate provides additional discrimination for.

**Suggested next attempt**: The key insight is that the ptg base at cap=1 is
near-optimal for this mechanism. The position gate's value comes from its ORACLE-AWARE
timing (it sees exactly which oracle signals conflict with current exposure). Additional
microstructure filters (flow, spread) degrade this because they remove some of the
good oracle-aligned entries. Future loops should explore mechanisms that improve the
QUALITY of individual entries rather than filtering which entries to take.
