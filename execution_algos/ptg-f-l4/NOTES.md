# Algorithm Notes: ptg-f-l4

Per-iteration experiment — base_algo `position-tier-gate`, context mode
`full-trace`, loop 4.

## Hypothesis

**Context from loops 1-3**:
- Loop 1 (cap=2): = simple (binary cliff, cap=1 must be preserved)
- Loop 2 (streak gate): = no-op (redundant with cap=1)
- Loop 3 (flow gate 30s + cap=1): -17.28% vs base (flow gate degrades already-good entries)

**Loop 4 hypothesis**: The 30s flow window used in loop 3 may be too long for
actionable microstructure signal when layered on the position gate. A shorter
window (5s) captures only the most recent momentum — which may have a tighter
correlation with imminent adverse fills. If 5s flow is a better predictor of
near-term adverse selection than 30s flow, it might filter fewer good trades.

**Mechanism**: cap=1 + flow gate with window=5s, threshold=1.0.

**Expectation**: trade_count between 78,238 (l3) and 90,433 (base). If a shorter
window is less selective (fewer skips), P&L degradation may be smaller.

**Builds on**: ptg-f-l3 finding (30s flow gate hurts). Testing 5s variant.

---

## Implementation Decisions

- position_cap=1 (preserved)
- window_seconds=5.0 (shorter than l3's 30s)
- flow_threshold=1.0 (same as l3)

---

## Backtest Observations

**Full 12-date train window:**
ptg-f-l4 (5s flow gate + cap=1): pnl=$3,266.50, -23.37% vs base, trades=78,436.
Worse than loop 3 (30s flow gate, -17.28%). Shorter window is more aggressive.
**Hypothesis verdict**: FALSIFIED. Short-window flow gate hurts more than long-window.
**Suggested next**: Directional-aware position cap (loop 5).
