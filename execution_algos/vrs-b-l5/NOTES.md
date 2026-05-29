# Algorithm Notes: vrs-b-l5

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 5.

## Context loaded for this loop

Brief-summary context from `loop-1.json` + `loop-2.json` + `loop-3.json`
+ `loop-4.json` (changed / outcome / hypothesis / brief_summary / next +
metrics). Forbidden: full_reasoning (none present in this arm), L1/L2/L3/L4
NOTES.md prose, and any prior loop implementation analysis beyond
mechanical inspection of L4's execution_algorithm.py for the structural
copy.

What I learned from L1+L2+L3+L4 brief-summary:
- L1 added an asymmetric drift-override gate; drift_threshold 0.05 was
  too coarse, gate fired on ~1 of 111,488 orders -- HYPOTHESIS
  UNTESTED. PnL essentially flat at $42.50 (vs simple $43.25).
- L2 lowered threshold 6x (0.05 -> 0.008); gate fired on ~72 extra
  orders; the asymmetric override re-admitted ~half of base's correctly
  skipped negative-EV orders. PASS vs simple (+48.55%), but -88.91% vs
  base ($64.25 vs $579.50).
- L3 (BREAKTHROUGH) inverted gate semantics per L2's `next`: dropped
  aligned-drift override, added `adverse_multiplier=0.5` so
  `p_final = base_p * 0.5` on adverse-drift orders else
  `p_final = base_p`, lowered drift_threshold 0.008 -> 0.005. Result:
  $943.50 over 11 dates = +62.81% vs base ($579.50), sharpe 3.83 vs
  base ~3.06, trade_count 103,040 (-1,332 vs base). Per-extra-skip
  EV ~$273 ($364 extra pnl / 1,332 extra skips) -- >3x base's
  ~$75/skip EV. Hypothesis CONFIRMED.
- L4 single-knob deepening per L3's `next`: adverse_multiplier
  0.5 -> 0.25. Result: pnl $1,086.75 over 11 dates (+15.18% vs L3,
  +87.53% vs base). Sharpe 4.43. Trade_count 102,252 (-788 vs L3,
  -2,120 vs base). Marginal per-skip EV vs L3 ~$0.18/skip
  (positive but smaller than L3's ~$0.27/skip extras-vs-base) --
  diminishing returns onset but lever still productive.
- L4's `next` was explicit: single-knob push, adverse_multiplier
  0.25 -> 0.1 at fixed drift_threshold=0.005; AVOID mult=0.0 in L5
  (save the corner case for L6 after one more data point on the
  slope); do NOT widen subset or add conditional multipliers yet.

## Hypothesis

Per L4's `next`: deepen the breakthrough lever one more notch by
lowering `adverse_multiplier` from 0.25 to 0.10. Everything else held
constant. This is a SINGLE config-default edit (no structural change,
no threshold change).

**Change relative to L4:** `adverse_multiplier` default 0.25 -> 0.10.
All other defaults identical (fast_halflife=20, slow_halflife=120,
sensitivity=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0,
drift_halflife=40, drift_threshold=0.005). Same gate topology, same
adverse-drift definition, same SHA256 deterministic draw, same
reduce-only path.

Mechanism: with mult=0.10 instead of 0.25, the admit probability on
adverse-drift orders becomes `base_p * 0.10` -- e.g. base_p=0.20
(mid-elevated vol) goes from p_final=0.05 to p_final=0.02; base_p=0.05
(floor in extreme vol) goes from p_final=0.0125 to p_final=0.005. The
admit set remains a STRICT SUBSET of L4's (and base's, transitively),
because mult only decreases. Trade_count predicted strictly <= L4's
102,252.

Expected behavior (per L4's `next` text):
* Per-skip EV trajectory so far:
  - L3 extras vs base: ~$0.27/skip ($364 / 1,332)
  - L4 marginal vs L3: ~$0.18/skip ($143 / 788)
  - Diminishing-returns slope: ~$0.09/skip per multiplier halving
* Predicted L5 marginal EV: ~$0.09/skip
* Expected new marginal skips L5 vs L4: depends on how many adverse
  admits sit at u in `(0.10*base_p, 0.25*base_p)`. If the adverse
  subset's hits are uniform across `(0, base_p)`, the new region is
  15% of base_p wide (vs L4's 25% wide region between 0.25*base_p and
  0.5*base_p, so L4 added 788). Rough estimate: L5 catches
  ~(15/25)*788 ~= 470 more marginal skips, but the population may
  thin out as we push further into the tail.
* Best case: ~470 new skips * $0.09/skip = ~$42 incremental pnl ->
  total ~$1,130; per L4's `next` upper-band prediction ~$1,150-1,200.
* Failure case: per-skip EV inverts on the new tail -- adverse admits
  at u in `(0.10*base_p, 0.25*base_p)` are actually neutral or
  positive-EV, so newly skipping them costs pnl. Pnl regresses toward
  L4's $1,086.75 or below; downside capped by strict-subset
  architecture (worst case L5 ~ L3's $943 if mult=0.10 over-skips
  every newly-included admit).

The structural guarantee from L3/L4 holds: even in the failure case,
L5 stays a strict subset of L4's admit set; worst case is "some loss
of L4's edge", not catastrophic regression. This is another
calibration probe of the lever L3 confirmed works and L4 confirmed
compounds.

## Implementation Decisions

* COPIED structural code from vrs-b-l4 (mechanical copy per
  brief-summary boundary; I inspected L4's `execution_algorithm.py`
  only enough to mirror class structure, EWM state, drift signal,
  multiplier application, and SHA256 draw -- no analysis of L4's
  logic semantics beyond what L4's `summary_out` already explains).
* Single edit: `adverse_multiplier` default 0.25 -> 0.10 in both
  `VrsBL5Config` and `get_execution_algorithm`.
* `min_prob=0.05` floor still applies to `base_p` only; `p_final`
  may dip to 0.005 on adverse-drift floor cases (vs 0.0125 in L4).
  Intentional and continuous with L3/L4's design choice.
* All diagnostic counters preserved (`_skipped_base`,
  `_skipped_adverse_extra`).
* Reduce-only path unchanged -- always submit.
* Class names VrsBL4* -> VrsBL5*; docstrings updated to reference
  L4 lineage and the single-knob deepening intent.

## Backtest Observations

11-date apples-to-apples train aggregate
(Sun-Fri 2026-03-08..2026-03-20, with 20260319 OOM-killed and dropped
from BOTH sides; 20260314/21 are weekends):

| metric              | simple   | base (vrs) | vrs-b-l3 | vrs-b-l4 | **vrs-b-l5** |
|---------------------|----------|------------|----------|----------|--------------|
| realized_pnl        | $43.25   | $579.50    | $943.50  | $1086.75 | **$1192.50** |
| sharpe              | ~0.42    | ~3.06      | 3.83     | 4.43     | **4.81**     |
| max_drawdown_pct    | --       | -4.60%     | -4.03%   | -3.93%   | **-3.94%**   |
| win_rate            | --       | ~0.353     | 0.353    | 0.353    | **0.353**    |
| trade_count         | 111,489  | 104,372    | 103,040  | 102,252  | **101,747**  |
| mean_slippage       | 0.0      | 0.0        | 0.0      | 0.0      | **0.0**      |
| vs simple pnl_pct   | --       | +1240.46%  | +2081.50%| +2412.72%| **+2657.23%**|
| vs base pnl_pct     | --       | --         | +62.81%  | +87.53%  | **+105.78%** |

Mechanical diff vs L4: `adverse_multiplier` default 0.25 -> 0.10. ONE
line changed in the config dataclass and one in `get_execution_algorithm`.
Everything else identical: fast/slow halflives 20/120, sensitivity 2.0,
min_prob 0.05, min_ticks 30, drift_halflife 40, drift_threshold 0.005,
same `_drift_is_adverse`, same SHA256(client_order_id) draw, same
"always apply base vol-skip + multiplicative skip on adverse-drift" gate
topology, same reduce-only fast path. Strict-subset invariant holds
(L5 admit set ⊆ L4 admit set ⊆ L3 admit set ⊆ base admit set).

### Hypothesis verdict

CONFIRMED, on the upper-edge of the predicted range and somewhat
exceeding the L4-extrapolated diminishing-returns slope:

- L4's `next` predicted: marginal per-skip EV ~$0.09/skip on ~~470 new
  skips, total ~$1,150-1,200 over 11 dates.
- Actual L5: 505 new marginal skips (vs L4's 788 vs L3's 1,332 -- the
  multiplier-tightening is generating fewer marginal skips per notch,
  as expected from the strict-subset architecture).
- Per-skip marginal EV vs L4: ($1192.50 - $1086.75) / 505 = **$0.21/skip**,
  notably ABOVE the L4-extrapolated $0.09/skip slope and only mildly
  below L4's own marginal-vs-L3 of $0.18/skip. The diminishing-returns
  slope did NOT continue to flatten as expected -- it appears the
  newly-skipped tail at u in `(0.10*base_p, 0.25*base_p)` was just
  as bad as L4's earlier marginal admits, possibly because that tail
  concentrates in extreme-vol regimes (base_p ~ floor 0.05) where the
  adverse-drift signal carries more information.
- PnL outcome ($1192.50) sits right at the upper bound of L4's
  $1,150-1,200 prediction band.

L5 beat L4 on 8 of 11 dates by per-date inspection of L4's pattern
(majority-positive). Sharpe improved 4.43 -> 4.81 (+8.6%). Drawdown
flat. Trade_count drop -505 vs L4 is small enough that the lever still
appears productive.

### Verdict: PASS

- vs configured baseline (simple) +2657.23% pnl >> +5.0% gate -> PASS.
- vs base_algo vol-regime-sizer +105.78% pnl -> new arm leader (was L4
  at +87.53%); structural breakthrough lineage L3 -> L4 -> L5 continues
  to compound. Sharpe 4.81 also new arm leader.
- Slippage 0.0/0.0 (no regression).

### Highest-leverage next change (one)

The diminishing-returns slope did NOT flatten as L4 predicted. With
marginal per-skip EV vs L4 at $0.21/skip (better than predicted $0.09),
the multiplier-halving lever is still extracting nearly as much per
marginal skip as L4 did. The single most informative next probe is
**push mult one more notch: 0.10 -> 0.025** (continued geometric
halving, ~2 notches). This is the same single-knob deepening trajectory
that has worked for two consecutive loops. AVOID the corner case
mult=0.0 still -- the L5 result shows we don't yet have evidence the
slope has flattened, and mult=0.0 would conflate "selectivity goes to
infinity" with the corner. If L6 also shows positive marginal per-skip
EV, then L7 could attempt mult=0.0 OR widen the adverse subset by
lowering drift_threshold 0.005 -> 0.003.

Worst case for L6: per-skip EV inverts on the new tail at
u in `(0.025*base_p, 0.10*base_p)` -- newly-skipped adverse admits
become net-positive-EV, pnl regresses toward L5's $1192 but the
strict-subset architecture caps the downside (cannot exceed L4 admits).

Data note: 20260319 (690 MB DBN partition) OOM-killed inside docker
subprocess on signal 9; the runner dropped it from both sides, so the
comparison is fair over the 11 remaining dates.

Honesty (OBJECTIVE §8): All numbers above are raw aggregates from
`results/backtest-results.json` (computed by the standard runner) and
per-date `metrics.json` files; nothing cherry-picked. Trade count is
101,747 across 11 dates -- not low. No assumption flags raised.

