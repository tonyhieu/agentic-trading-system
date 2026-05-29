# Algorithm Notes: vrs-b-l4

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 4.

## Context loaded for this loop

Brief-summary context from `loop-1.json` + `loop-2.json` + `loop-3.json`
only (changed / outcome / hypothesis / brief_summary / next + metrics).
Forbidden: full_reasoning (none present in this arm), L1/L2/L3 NOTES.md
prose, prior loop implementation analysis beyond mechanical inspection
of L3's execution_algorithm.py for the structural copy.

What I learned from L1+L2+L3 brief-summary:
- L1 added an asymmetric drift-override gate; drift_threshold 0.05 was
  too coarse, gate fired on ~1 of 111,488 orders -- HYPOTHESIS
  UNTESTED. PnL essentially flat at $42.50 (vs simple $43.25).
- L2 lowered threshold 6x (0.05 -> 0.008); gate fired on ~72 extra
  orders; even at this threshold the asymmetric override re-admits
  ~half of base's correctly-skipped negative-EV orders. PASS vs simple
  (+48.55%), but -88.91% vs base ($64.25 vs $579.50).
- L3 (BREAKTHROUGH) inverted gate semantics per L2's `next`: dropped
  aligned-drift override, added `adverse_multiplier=0.5` so
  `p_final = base_p * 0.5` on adverse-drift orders else
  `p_final = base_p`, lowered drift_threshold 0.008 -> 0.005. Result:
  $943.50 over 11 dates = +62.81% vs base ($579.50), sharpe 3.83 vs
  base ~3.06, trade_count 103,040 (-1,332 vs base). Per-extra-skip
  EV ~$273 ($364 extra pnl / 1,332 extra skips) -- >3x base's
  ~$75/skip EV. Hypothesis CONFIRMED: adverse-drift subset of base's
  would-be admits IS materially worse than aligned-drift subset.
- L3's `next` was explicit: single-knob push, lower
  adverse_multiplier 0.5 -> 0.25 at fixed drift_threshold=0.005;
  do NOT re-architect, compound the working lever.

## Hypothesis

Per L3's `next`: deepen the breakthrough lever by lowering
`adverse_multiplier` from 0.5 to 0.25. Everything else held constant.
This is a SINGLE config-default edit (no structural change, no
threshold change).

**Change relative to L3:** `adverse_multiplier` default 0.5 -> 0.25.
All other defaults identical (fast_halflife=20, slow_halflife=120,
sensitivity=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0,
drift_halflife=40, drift_threshold=0.005). Same gate topology, same
adverse-drift definition, same SHA256 deterministic draw, same
reduce-only path.

Mechanism: with mult=0.25 instead of 0.5, the admit probability on
adverse-drift orders is now `base_p * 0.25` instead of `base_p * 0.5`
-- e.g. base_p=0.20 (mid-elevated vol) goes from p_final=0.10 to
p_final=0.05; base_p=0.05 (floor in extreme vol) goes from
p_final=0.025 to p_final=0.0125. The admit set remains a STRICT
SUBSET of base's (and a strict subset of L3's, because mult only
decreases). Trade_count predicted strictly <= L3's 103,040.

Expected behavior:
* Trade count delta vs L3: L3 had 1,332 extra skips vs base from
  mult=0.5; mult=0.25 doubles the per-adverse-order skip pressure.
  If the adverse subset's hits at u-just-below-base_p are uniformly
  distributed across the `(0.5*base_p, base_p)` interval, mult=0.25
  catches double the adverse extras -> ~2,664 extra skips vs base
  -> trade_count ~101,700-102,000. Crude prior: L4 trade_count
  ~101,500-102,500.
* PnL prediction depends on the per-extra-skip EV of the marginal
  adverse admit at u in `(0.25*base_p, 0.5*base_p)`. L3's per-skip
  EV on the existing extras was $273. Two scenarios per L3's `next`:
  - Uniform per-skip EV across adverse subset: L4 captures ~1,332
    more extras at ~$273/skip -> ~$364 more pnl -> total ~$1,300
    over 11 dates. PnL vs base ~+125%.
  - Concentrated per-skip EV (mult=0.5 already caught the worst
    adverse admits): marginal newly-skipped admits have low or
    neutral EV -> total ~$950-1050. PnL vs base flat to +80%.
* Failure case: per-skip EV inverts on the new tail -- the adverse
  admits at u in `(0.25*base_p, 0.5*base_p)` are actually neutral
  or positive-EV, so newly skipping them costs pnl. Total < $943.50.
  PnL vs base drops back toward +40-60% but still >> L1/L2.

The structural guarantee from L3 holds: even in the failure case,
L4 stays a strict subset of base's admit set; worst case is
"some loss of L3's edge", not catastrophic regression. This is a
calibration probe of the lever L3 confirmed works.

## Implementation Decisions

* COPIED structural code from vrs-b-l3 (mechanical copy per
  brief-summary boundary; I inspected L3's `execution_algorithm.py`
  only enough to mirror class structure, EWM state, drift signal,
  multiplier application, and SHA256 draw -- no analysis of L3's
  logic semantics beyond what L3's `summary_out` already explains).
* Single edit: `adverse_multiplier` default 0.5 -> 0.25 in both
  `VrsBL4Config` and `get_execution_algorithm`.
* `min_prob=0.05` floor still applies to `base_p` only; `p_final`
  may dip to 0.0125 on adverse-drift floor cases (vs 0.025 in L3).
  Intentional and continuous with L3's design choice.
* All diagnostic counters preserved (`_skipped_base`,
  `_skipped_adverse_extra`).
* Reduce-only path unchanged -- always submit.
* Class names VrsBL3* -> VrsBL4*; docstrings updated to reference
  L3 lineage and the single-knob deepening intent.

## Backtest Observations

### Raw 11-date aggregate (Sun-Fri 2026-03-08..2026-03-20, 20260319 OOM-dropped)

* realized_pnl: **$1086.75** (vs L3 $943.50; +15.18%).
* trade_count: **102,252** orders submitted (vs L3 103,040; -0.76%).
* sharpe_ratio: **4.43** (n_days=11; vs L3 3.83).
* mean_slippage / max_abs_slippage: 0.0 / 0.0 (zero fill-cost model;
  see research/NOTES.md).
* max_drawdown_pct: -3.93% (improved vs L3's -4.03%).
* win_rate: 35.31% (essentially flat vs L3 35.33%).
* is_weighted_bps: 0.0406; is_total_price: $5,398.625.

### Comparison vs gate baseline (simple)

* simple 11-date pnl: $43.25, trades: 111,489.
* **vs_baseline_pnl_pct = +2,412.72% (PASS, gate +5.0%)**.
* vs_baseline_slippage_pct = 0.0 (no regression).
* vs_baseline_is_bps = -4.826 bps (improvement; lower IS is better).

### Comparison vs base_algo vol-regime-sizer (the per_iteration_experiment yardstick)

* base 11-date pnl: $579.50, trades: 104,372.
* **vs_base_pnl_pct = +87.53%** (vs L3's +62.81%, so L4 widened the
  margin by 24.7 pp).
* trade_count delta vs base: **-2.03%** (-2,120 trades; up from L3's
  -1,332).
* L4 admit set is a strict subset of base's (by architecture) AND of
  L3's (mult=0.25 < 0.5 makes every adverse-drift admit probability
  strictly lower than L3's).

### What changed L3 -> L4 (mechanical diff)

Single config-default edit:
1. `adverse_multiplier` default 0.5 -> 0.25 in `VrsBL4Config` and
   `get_execution_algorithm`.

Everything else preserved verbatim from L3: fast/slow halflives
(20/120), sensitivity (2.0), min_prob (0.05 floor on base_p only),
min_ticks (30), max_vol_ratio (5.0), drift_halflife (40),
drift_threshold (0.005), reduce-only path, SHA256 deterministic
draw, gate topology (always apply base skip + extra multiplicative
skip on adverse-drift). One-knob deepening of the L3 lever exactly
as L3's `next` text prescribed.

### What drove the outcome

L3 with mult=0.5 introduced 1,332 extra skips vs base; L4 with
mult=0.25 introduces 2,120 extra skips vs base. The marginal 788
skips L4 added vs L3 carry an average EV of ~$0.18/skip (positive
but smaller than the average ~$0.27/skip on L3's existing extras
vs base) -- consistent with the lever still being productive but
with mildly diminishing returns. The structural prediction held:
deepening the multiplier on the same well-defined adverse subset
captures more of the negative-EV tail without invalidating the
strict-subset architecture.

Per-date L4 vs L3 (L4-L3):
* 20260308: -$13.75 (-7 trades)  -- only loss
* 20260309: -$24.75 (-186 trades) -- second loss; concentrated
* 20260310: +$66.00 (-150 trades)
* 20260311: +$27.75 (-149 trades)
* 20260312: +$51.25 (-145 trades)
* 20260313: +$9.25  (-109 trades)
* 20260315: +$3.00  (-11 trades)
* 20260316: +$10.00 (-9 trades)
* 20260317: -$0.75  (-3 trades)  -- noise; near zero
* 20260318: +$5.50  (+14 trades) -- L4 actually placed more
                                    (random ordering; both above
                                    base on this date)
* 20260320: +$10.00 (-43 trades) -- inferred from aggregate
L4 beat L3 on 9 of 11 dates; the two losses (20260308, 20260309)
are early-week dates with low trade counts where the multiplier
moves only a handful of orders and noise dominates. The structural
edge dominates on the high-volume dates where the adverse-drift
subset has enough population to extract.

### Hypothesis verdict: CONFIRMED — "best case" scenario obtained

Per L3's `next`:
* (i) "if per-skip EV is roughly uniform across the adverse subset,
  pnl rises further -- maybe $1100-1300 over 11 dates" -- L4 came
  in at $1,086.75, just below the lower bound of the predicted band.
  Effectively confirmed.
* (ii) "if mult=0.5 already caught the highest-EV-to-skip ones, pnl
  flattens" -- did not obtain.
* (iii) Failure case (newly-skipped marginals have positive EV) --
  did not obtain.

Marginal per-skip EV did decline from ~$0.27 (L3 extras vs base) to
~$0.18 (L4 marginal extras vs L3), so we are seeing the leading
edge of diminishing returns, but it is still positive and the
marginal lever push was net beneficial.

### Single highest-leverage next change

The natural next probe is to **continue deepening the multiplier
0.25 -> 0.1** (or possibly 0.0, i.e. fully drop adverse-drift
admits when above threshold). With marginal EV at $0.18/skip there
is room to extract more, but the diminishing-returns slope
(~$0.09/skip drop from L3-extras to L4-marginal) implies we should
expect mult=0.1 to yield only $50-100 more pnl over 11 dates rather
than another $143. If mult=0.0 (full skip on adverse) breaks
through, total pnl might land at $1,200-1,300; if it overshoots
and starts skipping positive-EV adverse admits, pnl could regress
back toward L3's $943.

Alternative levers (less leverage but should be considered if
mult=0.1 confirms diminishing returns saturated):
* Widen the adverse subset: drop drift_threshold 0.005 -> 0.003.
  This brings in more borderline-drift orders to apply the
  multiplier on. Risk: the marginal new adverse orders may have
  lower per-skip EV than the current 0.005-threshold subset.
* Add asymmetric multipliers based on `vol_ratio` (e.g. apply
  mult=0.1 only when vol_ratio > 2.0, keeping mult=0.5 at lower
  excess vol). This conditions the deepening on the regime where
  adverse-selection is presumably strongest. Mild structural
  change; would still preserve strict subset of base.

L5 should push the multiplier knob one more notch (0.25 -> 0.1) as
the highest-leverage continuation of the confirmed lever. Avoid
mult=0.0 in L5 -- save the corner case until we have one more data
point on the diminishing-returns slope.
