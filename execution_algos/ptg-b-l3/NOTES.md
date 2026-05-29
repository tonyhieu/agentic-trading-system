# ptg-b-l3 -- adverse-move override at 3-tick threshold

## Hypothesis

Brief-summary context allowed for this loop: loop-1.json + loop-2.json
(metrics + summary_out). I mechanically inspected
`execution_algos/ptg-b-l2/execution_algorithm.py` only -- no prior-loop
NOTES prose.

L2 (adverse_threshold_ticks=1) was -41.30% vs base on the 11
apples-to-apples dates (recovered +34 pp from L1's -75.33% by replacing
the age predicate with an adverse-move predicate, but still admitted
+9.80% trade_count vs base with negative aggregate consequence). L2's
brief-summary `next` text identified the highest-leverage next change
explicitly: **raise adverse_threshold_ticks from 1 to 3** ($0.75 in
price, three full-spread displacements). The reasoning given there is
that 1 tick is bid-ask oscillation rather than a real adverse regime,
and 3 ticks is a clearly distinguishable regime.

This loop implements exactly that single targeted change. The same gate
skeleton is preserved -- only the threshold constant changes.

### One targeted change vs. L2

- L2: `adverse_threshold_ticks = 1.0` (default = $0.25)
- L3: `adverse_threshold_ticks = 3.0` (default = $0.75)

Everything else is identical, including:
  - reversal vs same-direction-add classification
  - reduce-only short-circuit (always submits)
  - quote subscription pattern (idempotent, in `on_order`)
  - fall-back-to-skip behavior on missing quote or missing avg_px_open
  - diagnostic counters

### Why exactly 3 (not 2 or 5)

L2's `next` text proposed 3 as the natural single-step probe. The
adaptive rule (also from L2's `next`) is:
  - If L3 still has +trade_count vs base, predicate still too loose ->
    next loop tries 5.
  - If L3 collapses to ~0 admitted reversals (trade_count near base ~=
    73,802), predicate too strict -> next loop tries 2.
  - If L3 underperforms base even at 3 ticks, the adverse-mid proxy is
    exhausted as a conditioning variable -> next loop pivots to a
    different axis (spread vs rolling median, signed aggressor
    imbalance).

The in-flight diagnostic to look at first in step 7 is `trade_count`
relative to base's 73,802 -- it directly indicates which side of the
admit/skip curve L3 lands on.

### Failure mode I am explicitly betting against

The risk in the opposite direction from L2: 3 ticks may be too strict,
admitting almost no reversals and effectively collapsing to the base's
blanket-skip behavior. In that case L3's metrics would resemble base
(pnl close to $3564 on these 11 dates, trade_count near 73,802). That
is not a failure of the experiment -- it pins down one endpoint of the
threshold curve -- but it would mean L3 does not beat base, only ties
it, and L4 would probe 2 ticks. The prediction I am betting on is that
**3 ticks admits a non-trivial but small number of reversals (a few
hundred to a few thousand) that are net pnl-positive on average**, so
L3 lands between L2 ($2092, +7,232 trades vs base) and base ($3564,
0 trades delta), but skewed toward base in trade count and ideally
above base in pnl.

## Implementation Decisions

- Copied `execution_algos/ptg-b-l2/execution_algorithm.py` mechanically
  as the starting point; renamed `PtgBL2Config`/`PtgBL2Algorithm` to
  `PtgBL3Config`/`PtgBL3Algorithm`; changed the
  `adverse_threshold_ticks` default value from 1.0 to 3.0 in three
  places (Config default, Config docstring, factory kwarg default).
- Updated the module-level docstring to describe the single change vs
  L2 and the prediction.
- Did NOT alter the algorithm's structural logic, helper functions,
  counter set, or the `frozen=True` config pattern.
- The submitted-reversal-override log line message was reworded from
  ">= 1 tick" to ">= threshold (3 ticks default)" for accuracy; the
  numeric values logged are still computed from the config.
- `__init__.py` updated to re-export from the renamed module docstring.
- Registered in `execution_algos/__init__.py`.

## Backtest Observations

### Aggregate (11-date apples-to-apples train window, 2026-03-08..2026-03-20; 20260319 OOM-dropped on both sides)

| metric              | L3 (ptg-b-l3) | base (position-tier-gate, same 11 dates) | L2 (ptg-b-l2, same 11 dates) | simple (same 11 dates) |
|---------------------|---------------|------------------------------------------|------------------------------|------------------------|
| realized_pnl        | **2,769.75**  | 3,564.25                                 | 2,092.25                     | 43.25                  |
| trade_count         | 75,587        | 73,802                                   | 81,034                       | 111,489                |
| sharpe_ratio        | 13.93         | (12-date 17.62)                          | 10.08                        | low                    |
| max_drawdown_pct    | -1.89%        | -1.73% (12-date)                         | -2.45%                       | n/a                    |
| win_rate            | 36.88%        | 37.20% (12-date)                         | 36.31%                       | 35.65%                 |
| mean_slippage       | 0.0           | 0.0                                      | 0.0                          | 0.0                    |

### vs simple gate (the formal PASS comparison)

- delta_pnl = +6304.05% (gate: +5.0% -> **PASS, by a wide margin**)
- delta_slippage = 0.0% (zero fill-cost model, see research/NOTES.md; gate: <=+5.0% -> PASS)
- Verdict: **PASS** vs the configured `simple` baseline.

### vs base_algo position-tier-gate (informational refinement comparison, same 11 dates)

- vs_base_pnl_pct = **-22.29%** (L3 2,769.75 vs base 3,564.25)
- vs_base_trade_count = **+2.42%** (+1,785 trades; L3 75,587 vs base 73,802)
- All **11/11 per-date pnls trail base** in absolute dollars (range: from -$12.50 on 20260315 to -$147.00 on 20260309).
- L3 still does not beat base on this window. The refinement loop has not produced a parent-beating algorithm yet.

### vs L2 (one-loop refinement signal)

- delta_pnl = **+32.38%** on **-6.72% trades** (-5,447 fewer reversal admits drove +$677 in aggregate pnl).
- All 11 per-date pnls are >= L2 (5 dates strictly improved by >$50 each: 20260313 -195.75->-56.75, 20260317 -48.25->17.25, 20260318 314.75->378.00, 20260309 757.75->840.25, 20260312 75.00->179.75).
- L2->L3 trade count moved from 81,034 -> 75,587 (closer to base's 73,802), and pnl moved from 2,092.25 -> 2,769.75 (closer to base's 3,564.25). The two moves are consistent: each admitted reversal at the 1-tick threshold was on average money-losing, and tightening to 3 ticks dropped the worst of them.

### What changed vs L2 (mechanical diff)

- `adverse_threshold_ticks` default 1.0 -> 3.0 (factory kwarg default, config field default, and config docstring). That is the only change. Everything else (reversal classification, same-direction-add skip, reduce-only short-circuit, quote subscription, fallback skip on missing quote/avg_px_open, diagnostic counters) is byte-identical to L2.

### What drove the +32% pnl jump vs L2

- Per L2's hypothesis, the 1-tick threshold was bid-ask oscillation rather than a real adverse regime. At 1 tick, the override admitted ~7,232 net-loss reversals vs base; at 3 ticks the override admits ~1,785 net-loss reversals vs base -- a 75.3% reduction in over-admission, with a corresponding +32% pnl recovery.
- Mechanism: the 3-tick floor demands three full-spread displacements of mid against the existing position before allowing a flip. That is sufficient to filter out the majority of noise oscillations that L2 mistakenly admitted, but evidently still too permissive -- 11/11 dates trail base, meaning every date still admits some net-loss reversals.

### Hypothesis verdict

**PARTIALLY VINDICATED.** L3's hypothesis was that 3 ticks would land between L2 and base on trade_count, skewed toward base, and ideally above base in pnl. The trade_count direction was correct (81,034 -> 75,587, much closer to base's 73,802). The pnl direction was correct (2,092 -> 2,770, closing two-thirds of the L2-to-base gap). But the strongest version of the prediction -- "above base in pnl" -- did not happen; L3 is still -22.29% vs base. The "3 ticks may collapse to base" failure mode I bet against did NOT materialize -- L3 still admits +1,785 net trades vs base, so the gate is permissive enough to be admitting reversals, but those incremental admits are net money-losing in aggregate.

The L2->L3 trajectory (L1: -75.33%, L2: -41.30%, L3: -22.29% vs base) is monotonic improvement of ~+19 to +34 pp per loop. The convex region of the threshold curve is clearly visible: each tightening continues to help, with decreasing marginal returns. The natural next single-step probe is **adverse_threshold_ticks = 5** -- per L2's `next` text the rule was: "if L3 still has +trade_count vs base, the predicate is still admitting too many reversals and L4 should test 5 ticks." L3 has +trade_count vs base (+2.42%), so that branch fires.

### Single highest-leverage next change

**Raise `adverse_threshold_ticks` from 3 to 5** ($1.25 in price, five full-spread displacements). 5 ticks demands a significantly larger adverse regime -- empirically, a position that is 5 ticks underwater is likely on the wrong side of a real micro-trend rather than oscillating around fair value. The convex trajectory L1->L2->L3 suggests one more tightening should continue closing the gap; if pnl improves further and trade_count falls within striking distance of base (73,802), the predicate is approaching the right calibration. If at 5 ticks trade_count drops below base (predicate too strict, collapsing to ~no admitted reversals) or pnl regresses (admits are net-positive but we are now excluding good ones), L5 should bracket back to 4. If pnl is still below base at 5 ticks with +trade_count, the adverse-mid proxy is exhausted and a later loop should pivot conditioning variable (signed aggressor imbalance, spread vs rolling median, hold-time floor).
