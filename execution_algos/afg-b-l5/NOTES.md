# afg-b-l5 — aggressor-flow-gate with FURTHER TIGHTENED absolute threshold (flow=0.5)

Brief-summary arm, loop 5. Prior context = ONLY the `summary_out`
(changed / outcome / hypothesis / brief_summary / next) blocks from
loop-1.json (afg-b-l1), loop-2.json (afg-b-l2), loop-3.json (afg-b-l3),
and loop-4.json (afg-b-l4), plus the headline metrics for each. Per
the brief-summary mode boundary I did NOT read any prior NOTES.md
prose or any full_reasoning text -- only the brief summaries and the
L1/L2/L3/L4 source files (mechanical chassis-shape inspection only,
to know parameter and class structure).

## Hypothesis

L1 + L2 + L3 + L4 brief_summary establish:

  1. L1 (pure-ratio gate, |r| >= 0.35): WORSE than base (-53.25% pnl,
     +13,481 extra admits). Ratio-only reformulation cannot work.
  2. L2 (CONJUNCTION base AND ratio): WORSE than base (-52.14% pnl,
     +14,245 extra admits). Conjoining ADMITS the union, not the
     intersection.
  3. L3 (DISJUNCTION base OR ratio-with-busy-floor): EXACTLY equal to
     base (0.00% pnl diff). Ratio leg structurally dominated by
     absolute leg with chosen parameters.
  4. L4 (RATIO LEG REMOVED + abs threshold 2.0 -> 1.0): GENUINELY
     BEATS base (+12.16% pnl: $1088 vs $970, -1,671 trades, sharpe
     5.36 vs 4.58). Validates L1 monotone arithmetic in inverse
     direction: ~$70.6 per 1k extra skips beyond base.

L4's "next" explicitly prescribes: test threshold 0.5 to probe whether
the monotone-yield rule continues DOWN to a tighter threshold, or
whether we have crossed the optimum. Brief-summary trajectory along
the absolute-threshold axis:

  * threshold = 2.0 (base)  -> pnl $970,  87,760 trades, sharpe 4.58
  * threshold = 1.0 (L4)    -> pnl $1088, 86,089 trades, sharpe 5.36

Marginal yield from base -> L4: +$118 pnl / -1,671 trades =
~$70.6 per 1k extra skips. Sharpe rose, max_dd ~unchanged.

L5 single-parameter monotone change: flow_threshold 1.0 -> 0.5.
Expected admitted-set: strict subset of L4's (orders with |net_flow|
in [0.5, 1.0) now skipped; previously admitted by L4). The window
length (10s), anti-cascade flat-flag, and reduce-only-always-submit
semantics are preserved exactly from L4.

Expected direction (per brief-summary evidence):

  * trade_count: drops further below L4 (some incremental skips in
    [0.5, 1.0) net-flow regime).
  * pnl: rises further IF the monotone-yield rule continues to hold
    (i.e., the marginal orders in this regime are still weakly
    anti-informative on average). Falls or stalls IF we have crossed
    the optimum -- the absolute-threshold sweep would then have a
    pnl-maximum bracketed in (0.5, 2.0).
  * Sharpe: should rise if pnl rises (per L4 pattern); may decline if
    fewer-but-noisier trades increase variance per trade.
  * Selection effect: tighter threshold means more orders skip;
    cumulative skip-rate grows; the cascade-reset (_position_flat after
    any skip) fires more often.

Anti-rationale check: I considered alternatives to threshold sweep:

  * Window length change (e.g., 10s -> 5s or 20s): plausible but
    confounds the threshold sweep. L4's "next" explicitly says save
    window for L6+ after the threshold optimum is bracketed.
  * Per-side asymmetric thresholds: not yet motivated by brief-summary
    evidence (the brief summaries do not separate BUY-skip vs
    SELL-skip yields).
  * Reintroduce ratio: L1+L2+L3 exhausted that axis.
  * Lower threshold to 0 (no gate at all on signed net flow, only
    direction-side conditional): would degenerate to a no-skip algo
    (any non-zero adverse net flow skips), but only on dates with any
    aggressor activity in the window. Probably too aggressive for a
    single sweep step; 0.5 is the conservative bisection between L4's
    1.0 and the degenerate 0.0.

## Implementation Decisions

  * Single structural change vs L4: NONE -- the algorithm shape stays
    identical to L4 (ratio leg already removed in L4, absolute-only
    gate, anti-cascade flat-flag, reduce-only-always-submit, 10s
    window).
  * Single parameter change vs L4: `flow_threshold` 1.0 -> 0.5
    (further tighten the absolute threshold). Inclusive comparison
    preserved (skip iff |net_flow| >= 0.5).
  * Window kept at 10s -- isolate the threshold change.
  * Direction-side logic: BUY adverse when net <= -0.5; SELL adverse
    when net >= 0.5. Per-side signed test mirrors base + L1 + L2 + L3
    + L4 exactly.
  * Anti-cascade semantics (`_position_flat = True` after any skip,
    forcing the next OPEN through unconditionally) preserved exactly.
    Reduce-only orders always submit (intraday_flat).
  * Quantity invariant strictly preserved -- orders are skipped or
    submitted unmodified.
  * Class names: `AfgBL5Config` / `AfgBL5Algorithm`; factory
    `get_execution_algorithm` with new defaults.

  Boundary check: the threshold 0.5 means any order where the 10s
  window has even a SINGLE-contract net imbalance in the adverse
  direction will skip (since trade sizes are typically integer
  contracts). This is a meaningful tightening -- many windows will
  have at least 1 contract of net flow in some direction. Trade
  count drop could be larger than L4's 1.9%.

## Backtest Observations

### Headline numbers (11-date matched train window; 20260319 OOM-dropped from both sides)

  * realized_pnl:        1088.0      (L4: 1088.0; base on matched dates: 970.0)
  * sharpe_ratio:        5.360       (L4: 5.360;  base on matched dates: 4.581)
  * trade_count:         86089       (L4: 86089;  base on matched dates: 87760)
  * mean_slippage:       0.0         (zero fill-cost model)
  * max_drawdown_pct:   -0.03235     (~unchanged vs L4)
  * win_rate:            0.35399     (~unchanged vs L4)
  * vs simple baseline:  +2415.61% pnl, slippage 0.0
  * vs base_algo (11-date matched): +12.16% pnl ($1088 vs $970; -1,671 trades / -1.90%)
  * vs L4 (prior loop):  +0.00% pnl, 0 trades difference -- BIT-FOR-BIT IDENTICAL

### Gate verdict

  * vs simple gate (pass if vs_baseline_pnl_pct >= +5.0% and slippage
    regression <= +5.0%): PASS by very wide margin (+2415.61% >> +5.0%;
    slippage delta = 0.0%).
  * Refinement targets vs L4 (per config refinement.targets:
    min_sharpe_delta=0.5, min_pnl_delta_pct=2.0, max_slippage_delta_pct=-1.0,
    min_winrate_delta_pp=2.0, min_mdd_delta_pp=-1.0): ALL FAIL by tying
    exactly with L4 (sharpe delta 0.000; pnl delta 0.00%; slip delta 0.000%;
    win-rate delta 0.000pp; mdd delta 0.000pp). No refinement-target
    threshold cleared.

### Honest diagnosis: the change is a mechanical no-op

L5's single parameter change vs L4 was `flow_threshold` 1.0 -> 0.5.
The two backtest-results.json files are bit-for-bit identical on every
metric (pnl, sharpe, trade_count, max_dd, win_rate, slippage, IS bps).

Root cause: `net_flow` in this algorithm is the signed sum of trade
sizes in a 10s window, and on this oracle / instrument trade sizes are
INTEGER contract counts. Consequently `net_flow` only takes INTEGER
values (..., -2, -1, 0, 1, 2, ...). The skip condition is:

    BUY:  skip iff net <= -flow_threshold
    SELL: skip iff net >=  flow_threshold

For BUY orders, `net <= -1.0` and `net <= -0.5` admit exactly the same
set of integer values (... -2, -1). For SELL, `net >= 1.0` and
`net >= 0.5` likewise admit the same integer set (1, 2, ...). The set
{net : 0 < |net| < 1} -- which L5 was trying to additionally skip on
top of L4 -- IS EMPTY because integers cannot live strictly between
0 and 1.

Therefore L5's "tightening" from 1.0 to 0.5 made zero difference: the
admitted-order set is identical to L4's. L5 is L4 in disguise.

### Hypothesis verdict: CONTRADICTED

L5's hypothesis predicted "trade_count strictly < L4's 86,089 (tighter
absolute threshold skips more orders -- any order with |net_flow| in
[0.5, 1.0) is newly skipped)." This was WRONG because no orders ever
have |net_flow| in (0, 1) on this oracle -- the integer resolution of
trade sizes makes that interval empty. The pre-loop hypothesis text
even flagged the possibility implicitly ("trade sizes are typically
integer contracts") but failed to recognize that this made the chosen
parameter step inert.

The lesson encoded here for future loops: on this oracle, the
flow_threshold lever has INTEGER RESOLUTION. Decimal-fraction tweaks
below 1.0 (e.g., 0.5, 0.25, 0.1, 0.01) are ALL no-ops and ALL
equivalent to threshold=1.0. The only meaningful threshold values are
1, 2, 3, ... (or 0, which would degenerate the gate). The next
informative test along the absolute-threshold axis must move by at
least one INTEGER step from the effective state (L4=L5 at flow=1).

### What "PASS" means here

Versus the configured pass_gate baseline (`simple`), L5 PASSES by an
enormous margin (the cached simple-baseline 11-date pnl is $43.25;
+2415.61% pnl improvement; slippage tied at 0.0). So by the formal
gate criterion, L5 is a PASS. But it is a TIED PASS with L4, not an
improvement. From the refinement perspective (improvement vs the
PRIOR loop), L5 is a FAIL on every refinement target -- it adds zero
information beyond L4.

This is exactly the kind of result the honesty rules in OBJECTIVE.md
exist to surface: report the raw numbers, flag the no-op, do not
fold a no-op into the brief_summary "next" stream as if it were
meaningful new data.

### Highest-leverage next direction

The threshold sweep below 1.0 is dead -- all decimal-fraction values
collapse to threshold=1.0 by integer resolution. The remaining
informative absolute-threshold tests are:

  * threshold = 2.0 -- equals base; already known to give $970 pnl /
    87,760 trades. No new info.
  * threshold = 3.0 -- LOOSEN beyond base (admit more orders, including
    those with |net_flow| in [2, 3) that base would skip). Should
    INCREASE trade_count and (by the L1 inverse-monotone rule, if it
    extrapolates to the loose side) DECREASE pnl.
  * threshold = 4.0, 5.0, ... -- further loosen; should be further from
    base.

To extend the threshold sweep in the productive (tighter) direction
we already explored to L4's optimum candidate of 1.0, the next
meaningful integer step DOWN is threshold = 0 -- but threshold = 0
degenerates: with strict-inequality `>=` interpretation the gate
fires on |net_flow| >= 0 i.e. ALWAYS (or, more precisely, whenever
the deque is non-empty), skipping nearly all entries. That is a
different algorithm entirely and probably catastrophic.

So the most informative L6 single-parameter monotone change is the
OTHER direction: flow_threshold 1.0 -> 3.0 (one integer step BEYOND
base). This tests whether the absolute-threshold sweep's pnl is
genuinely maximized near 1.0, or whether it has further upside on
the loose side that we have not yet visited. If pnl_L6 < pnl_L4, the
local maximum is bracketed in [1, 3] with peak <= 1; this is
consistent with the L1 monotone-skip rule and the data trajectory
base(2.0)=$970 -> L4(1.0)=$1088. If pnl_L6 > pnl_L4 (loosening
HELPED), the absolute-threshold curve is non-monotone with a
secondary maximum at some threshold > 2, and the L1 rule does not
extrapolate to the loose side -- a much more surprising and
informative result.

Alternative L6 direction worth keeping in reserve: change window
length (e.g., 10s -> 5s or 20s) at fixed threshold=1.0 -- this is
the orthogonal axis L4's "next" had wanted to defer until the
threshold optimum was bracketed. With L5 a no-op, the threshold
optimum is now bracketed in [1, 2] (since the data is
base(2.0)=$970, L4(1.0)=$1088, no other values informatively
sampled). Reasonable to take the orthogonal axis as L6 if we
believe further integer-threshold sweep tests will be wasteful.

I recommend L6 = flow_threshold 1.0 -> 3.0 (the integer-step-up
sweep), per the "meaningful change must move at least 1 integer
step" rule established by this no-op finding.

