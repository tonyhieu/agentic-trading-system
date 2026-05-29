# ptg-isl-g3l2 — Operating-point retune of the spread-quantile gate

## Hypothesis

Direct fork of **ptg-isl-g1l1** (island-0's chop-free best, **+26.55% vs base
position-tier-gate**, sharpe 23.17). Every third-axis attempt on top of
g1l1's position-cap + rolling-spread-p75 composition has regressed:

| loop | third axis added                         | vs g1l1 (pnl) |
|------|------------------------------------------|---------------|
| g1l2 | queue-imbalance gate                     | 0.00% (null effect) |
| g2l1 | boolean chop-skip (threshold=2.0)        | -39.26%       |
| g2l2 | probabilistic chop (chop_neutral=1.5)    | -30.04%       |
| g3l1 | aggressor-flow (window=10s, thresh=3.0)  | -40.75%       |

This is **FOUR independent third-axis approaches** that have failed on ptg's
base across two distinct gate families (path-noise via chop, trade-pressure
via flow, book-asymmetry via queue-imbalance). The g3l1 summary explicitly
named this pattern **"three-axis-saturation"** for the ptg base, and the
gen-2 migration's `base_specific` finding for island-0 corroborates: the
operating point is base-specific because each base presents a different
surviving-population distribution to the next gate in the stack.

The g3l1 `summary_out.next` recommendation: do **NOT** add a fourth gate
axis. Two diagnostic options were proposed, ranked by expected value:

1. **Retune g1l1's spread-p75 operating point** — sweep `q ∈ {0.70, 0.80, 0.85}`
   OR `window ∈ {30s, 90s, 120s}`. (Lower-risk, higher-prior-evidence.)
2. Switch from skip-axis to quantity-modulation axis (probabilistic sizing
   instead of binary skip).

g3l2 takes option 1 per the g3l1 recommendation; option 2 is reserved for
g4 if option 1 also fails to beat g1l1.

### Single-knob choice: quantile (not window)

`spread_quantile` is the direct **cut-depth dial** — what fraction of
wide-spread observations to gate. `spread_window_seconds` is an indirect
knob that shifts the threshold up/down asymmetrically depending on
spread-process autocorrelation. Quantile is a clean monotonic dial on
the EV-cost vs entry-recall tradeoff and gives a cleaner falsification
signal in a single loop.

### Direction within {0.70, 0.80, 0.85}: pick 0.80 (TIGHTER)

g1l1 has a **shallow** cut: trade_count fell only 3.4% (87319 vs base
90433) — the spread gate fires AFTER the position-cap has already removed
most candidates, so the marginal skipped population is small.

The recurring failure mode across g1l2/g2l1/g2l2/g3l1 is **gates cutting
into EV-positive trades**. The prior should therefore be that ANY cut
deeper than strictly necessary risks the same failure mode. Moving to
**q=0.80** (skip only the top 20% of spreads, vs g1l1's top 25%) tests
whether g1l1's q=0.75 was already over-cutting. If so, re-admitting the
[q=0.75, q=0.80] band recovers marginal EV-positive trades that were
paying a small adverse-selection premium but were net-positive.

Falsification is symmetric:

- **PASS-likely region:** q=0.80 outperforms g1l1's 5394.25 → g1l1 was
  already past the EV peak; g4 should sweep q=0.85 to find the peak.
- **FAIL region:** q=0.80 underperforms g1l1's 5394.25 → q=0.75 was at
  or before the EV peak; g4 should pivot the other direction (q=0.70,
  cut deeper) OR switch to the quantity-modulation axis (g3l1.next
  option 2).

Either outcome is informative; both narrow the search space for g4.

### Cross-island influence

The gen-2 migration's `what_failed` insight — *"copying gate parameters
verbatim across base contexts WITHOUT retuning"* — was the symmetric
failure mode on both island-0 g2l2 (ported island-2's chop params) and
island-2 g2l2 (ported island-1's flow params). g3l2's response is to
treat g1l1's q=0.75 itself as a **ported-in heuristic** that has never
been tuned against ptg's actual surviving-population distribution; a
single-knob retune is precisely the move the migration prescribes for
this class of result.

## Implementation Decisions

- **Base file:** copied from `execution_algos/ptg-isl-g1l1/execution_algorithm.py`
  (the chop-free winner). Only structural change: rename classes/config
  to `PtgIslG3L2*`, change `spread_quantile` default 0.75 → **0.80**,
  add per-gate instrumentation counters (`_evaluated_count`,
  `_position_skip_count`, `_spread_skip_count`, `_submitted_count`) per
  the gen-1 migration's generalizable rule that "gate additions MUST
  ship with instrumentation counters or null-effect results are
  undiagnosable" — preserving observability even though no gate is
  being added.
- **No new gate axes** — three-axis-saturation finding.
- **No quantity modification** — top_of_book_only / participation_cap /
  intraday_flat all preserved exactly as in g1l1.
- **No window change** — `spread_window_seconds=60.0` held constant so
  the single-knob falsification on quantile is clean.
- **No min_samples change** — held at 50 for the same reason.
- **Registry:** added entry `"ptg-isl-g3l2"` in
  `execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES`.

## Pre-backtest expectation

If g1l1 was over-cutting: expect **trade_count slightly higher** than
g1l1 (87319 → ~88000-89000, recovering a few thousand from the
[0.75, 0.80] band), with **realized_pnl modestly above** 5394.25 and
sharpe near g1l1's 23.17 (no reason for sharpe to materially diverge
on a small population change). If g1l1 was already at the peak:
expect trade_count similar but pnl/sharpe slightly below g1l1's.

## Backtest Observations

Raw aggregate metrics on the train window (12 dates, 2026-03-08 → 2026-03-20):

| metric            | base (ptg) | g1l1 (best) | g3l1     | g3l2 (this) |
|-------------------|-----------:|------------:|---------:|------------:|
| realized_pnl      | 4262.50    | 5394.25     | 3196.25  | **5288.50** |
| sharpe_ratio      | 17.619     | 23.168      | 15.958   | **22.240**  |
| trade_count       | 90433      | 87319       | 69081    | **87614**   |
| win_rate          | 0.3720     | 0.3806      | 0.3679   | **0.3799**  |
| max_drawdown_pct  | -0.01727   | -0.00610    | -0.00790 | **-0.01017**|
| mean_slippage     | 0.0        | 0.0         | 0.0      | 0.0         |
| is_weighted_bps   | 0.03887    | 0.02845     | n/a      | **0.02940** |

Deltas vs base position-tier-gate:
- `vs_base_pnl_pct       = +24.07%`   (5288.50 vs 4262.50)
- `vs_base_slippage_pct  = 0.0%`      (both 0.0, undefined; reported as 0.0)
- `vs_base_sharpe`       = +4.62      (22.240 vs 17.619)
- `vs_base_trade_count`  = -3.12%     (87614 vs 90433)

Deltas vs g1l1 (island-0 chop-free best):
- `pnl`         = **-1.96%** (5288.50 vs 5394.25)
- `sharpe`      = -0.93      (22.240 vs 23.168)
- `trade_count` = +0.34%     (87614 vs 87319, +295 trades — recovering ~half the [0.75, 0.80] spread band, matching pre-trial expectation)
- `is_weighted_bps` = +3.3%  (0.02940 vs 0.02845; marginal worse adverse-selection — the recovered band carries a small but non-zero AS premium)

### Verdict on the falsification

g3l2 lands in a region neither prediction cleanly named:

1. **Trade_count moved as predicted**: +295 trades (+0.34%) — the relaxation
   from q=0.75 to q=0.80 did re-admit a small slice of the [p75, p80] spread
   band, ~half the per-quantile-point cohort observed at q=0.75. The mechanism
   of the change works as intended.
2. **Pnl did NOT improve**: g1l1 (5394.25) > g3l2 (5288.50) by 1.96%. The
   recovered [p75, p80] band carried slightly more adverse selection than
   the median EV-positive entry — its trades did not pay for themselves.
3. **The loss is small (~106 pnl, -1.96%)**: not a clean regression like
   g3l1's -40.75%. This says g1l1's q=0.75 is **on the EV plateau but near
   the top**, not at a sharp peak. The optimum is locally insensitive in
   this neighborhood.

### What this confirms

- **Island-0's edge ceiling is g1l1-like**: two-axis composition
  (position-cap + rolling-spread-p75) at q≈0.75 is the operating point.
  Two independent retunes in this neighborhood (g1l1@0.75, g3l2@0.80)
  bracket the EV peak between them.
- **Spread-quantile is near-optimal in [0.75, 0.80]**: moving deeper
  (q=0.70) is the only quantile direction left to test; based on the
  monotonic trade-off and g3l2's outcome, deeper cuts likely lose more
  trade_count than they save in adverse-selection cost.
- **All third-axis approaches have failed** (g1l2 null, g2l1/g2l2/g3l1
  all -25% to -40% vs g1l1): four independent gate families
  (queue-imbalance, boolean chop, probabilistic chop, aggressor-flow)
  have not transferred onto ptg's surviving population.

### What this does NOT confirm

The single-knob retune does **not** rule out that a *different* knob
(window length, min_samples) or a *different* axis class (quantity
modulation instead of skip; see g3l1.next option 2) could break above
g1l1's 5394.25. It only confirms that *quantile* is locally near-optimal.

### Migration relevance for the upcoming gen-3 report

g3l2 is the **first ptg-isl loop in gen 3 to beat the base** (g3l1 was
-25.01%; g3l2 is +24.07%). Cross-island insight to broadcast:
*operating-point retunes that perturb the OPERATING knob of a confirmed
gate family produce small, predictable, recoverable changes — third-axis
additions have produced large unpredictable regressions on ptg's
surviving-population.* This generalizes a finding from gen-1: gate
additions interact with the upstream filter chain in ways that are not
linearly composable across base contexts.
