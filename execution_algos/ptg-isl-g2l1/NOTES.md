# Algorithm Notes: ptg-isl-g2l1

## Hypothesis

**Builds on**: `ptg-isl-g1l2` (island-0, generation 1, loop 2) — which stacked
queue-imbalance gating on top of g1l1's position-cap + rolling-spread-p75
combo. Result on the 12-date train window: bit-for-bit identical to g1l1
(pnl +26.55% vs base, sharpe 23.17). The added imbalance gate produced
**zero incremental effect** — a null-effect result that g1l2 itself
flagged as undiagnosable without instrumentation.

**Mechanism (this loop, g2l1)**: Drop the null-effect queue-imbalance gate.
Keep position-cap + rolling-spread-p75. ADD a price-path **choppiness gate**
on top — a genuinely orthogonal axis (price-path inefficiency vs book-width)
that produced +34% PnL on island-2's vol-regime-sizer base in g1l1.

Concretely, at OPEN time:

  Let `path_length(W)  = sum_{i=t-W+1..t} |mid_i - mid_{i-1}|`
      `displacement(W) = |mid_t - mid_{t-W}|`
      `chop_ratio(W)   = path_length(W) / max(displacement(W), eps)`

  SKIP the OPEN if `chop_ratio > chop_skip_threshold` (default 2.0).

  A pure trend → chop_ratio == 1.0 → pass. A whipsaw of equal-magnitude
  sign-flips → displacement → 0 → chop_ratio → ∞ → skip.

Also ADD lightweight **instrumentation counters** for every gate
(evaluated, skipped_position, skipped_spread, skipped_chop, submitted)
and emit them on each skip-log line — gen-1 lost a loop (g1l2) to
inability to distinguish "gate never fires" from "gate fires but is
EV-neutral."

**Cross-island influence (cited explicitly)**: The gen-1 migration report
flagged composing island-0's spread-quantile gate with island-2's
choppiness ratio as the single highest-leverage cross-island direction
("highest-leverage generation-2 direction across all islands"). That is
exactly what this loop implements, ported to the position-tier-gate base.
Island-2's choppiness gate used a *probabilistic* sizer (because the
vol-regime-sizer base is probabilistic); island-0 uses *boolean skip*
semantics throughout, so we adapt it to a deterministic threshold gate
rather than copying the exponential-decay submission probability.

**Why this composition should compose additively (not redundantly)**:
- Spread-p75 gates on **top-of-book width** (a snapshot variable). It
  catches liquidity-vacuum moments.
- Chop-ratio gates on **trajectory of the mid** over a 30-tick window
  (a path variable). It catches whipsaw regimes.
- These two correlate weakly: a whipsaw can occur on a tight book
  (frequent small sign-flipping ticks) and a vacuum can occur during a
  clean trend (one wide print). The migration explicitly named these as
  "near-orthogonal axes (book-state vs price-path)."

**Expected effect**:
- Trade-count drop: bigger than g1l1's -3.4%, likely 2-8% of the
  surviving-after-spread-gate population removed.
- PnL: a positive lift over g1l1 IF chop-gate fires on a net-negative
  EV slice; near-zero if the slice is EV-neutral; instrumentation will
  tell us which.
- Sharpe / drawdown: tighter, since the filtered slice should contain
  whipsaw-period trades that are high-variance losers.

**Honesty up-front**: mean_slippage is 0.0 by simulator construction
(top-of-book fills), so `vs_base_slippage_pct` will be 0.0 again. The
real comparison axes here are pnl, sharpe, drawdown, and the new
instrumentation log lines.

## Implementation Decisions

- **Choppiness window**: 30 quote ticks — matches island-2 g1l1's choice,
  which the migration confirmed worked. Reusing the proven window
  rather than re-tuning.
- **chop_skip_threshold = 2.0**: at this threshold, a window with at
  least one full reversal (path doubles displacement) is skipped. This
  is firmer than island-2's `chop_neutral=1.5` (which only *starts*
  decaying probability at 1.5 and never fully zeros it). Boolean-skip
  semantics require a single threshold — 2.0 sits at "clearly whipsaw,
  not just modest noise."
- **min_ticks=40 / window_ticks=30**: cold-start guard mirrors island-2.
  Until 40 quote ticks are observed, the chop gate is a no-op (pass).
- **Gate ordering**: position-cap → spread → chop. Each is cheap; we
  preserve the gen-1 ordering and append chop last so g1l1/g1l2
  outcomes are nested if chop never fires (helpful for the null-result
  comparison this loop is designed to break).
- **Instrumentation**: integer counters maintained on the algo
  instance. Each skip path increments its counter and emits an
  `info`-level log line with the running totals every Nth skip
  (every 500 by default to avoid log blowup); a final summary line is
  emitted in `on_stop` (subclass hook if available; otherwise the
  per-skip-log line accumulator provides observability post-hoc via
  grep). Counters are stored on the instance so per-date metrics
  files could be enriched in a future loop if needed.
- **No quantity modification**: SKIP means do not submit. Quantity
  invariant preserved across all three gates.
- **No look-ahead**: chop is computed exclusively from
  `_mids` populated in `on_quote_tick`, strictly in chronological
  replay order; `on_order` reads cached state only.
- **Reduce-only orders bypass all gates** (intraday_flat compliance,
  consistent with all prior ptg lineage algos).

## Backtest Observations

**Raw aggregate (12 train dates, MESM6):**
- realized_pnl: **3276.25** (base position-tier-gate: 4262.5; prior g1l2: 5394.25)
- mean_slippage: 0.0 (top-of-book simulator fills — same for base and lineage)
- sharpe_ratio: 17.859 (base: 17.619; g1l2: 23.168)
- max_drawdown_pct: -0.4725% (base: -1.7275%; g1l2: -0.6100%)
- win_rate: 0.3713 (base: 0.3720; g1l2: 0.3806)
- trade_count: **72060** (base: 90433; g1l2: 87319) — ~20.3% of trades filtered
- is_weighted_bps: 0.0340 (base: 0.0389; g1l2: 0.0285)

**Deltas vs base position-tier-gate (island-0 base_algo):**
- vs_base_pnl_pct: **-23.14%** (regression; computed (3276.25 - 4262.5) / |4262.5| * 100)
- vs_base_slippage_pct: 0.0 (both sides zero — delta undefined; reported as 0.0)

**Deltas vs prior lineage g1l2:**
- pnl: -39.26% (3276.25 vs 5394.25 — large regression within island-0 lineage)
- trade_count: -17.5% (72060 vs 87319 — chop gate cut 15.3k trades on top of g1l2 selection)
- sharpe: -22.9% (17.86 vs 23.17)

**Hypothesis verdict: FALSIFIED.** The composition hypothesis — that adding
choppiness gating on top of position-cap + spread-p75 would *add* PnL because
chop-ratio and spread-width are near-orthogonal axes — does not hold on this
base. The chop gate filtered 15.3k trades but removed *positive-EV* trades on
net, not whipsaw losers. The sharpe drop (23.17 → 17.86) and pnl drop (5394 →
3276) imply the filtered slice had a higher mean PnL than the survivor slice
— exactly the opposite of the expected behaviour.

Mechanistically the most likely explanations are:
1. **Threshold too aggressive for this base.** `chop_skip_threshold=2.0` was
   ported from island-2 where chop was a *probabilistic decay* (chop_neutral
   1.5 with exponential reduction, never zero), not a hard boolean skip. On
   position-tier-gate's already-throttled selection, a boolean skip at 2.0
   cuts deeper than the soft penalty did on vol-regime-sizer.
2. **Path-noise correlates positively with this strategy's edge.** Island-2's
   base (volatility-aware sizing) likely had its edge concentrated in clean
   trends; ptg's edge appears to *include* whipsaw periods. The migration
   report assumed the chop filter would transfer; this run is evidence it
   does not transfer additively to all bases.
3. **Composition with spread-p75 is not orthogonal in practice.** The spread
   gate already trimmed the tail; the surviving population's chop signal may
   be poorly calibrated (cold-start `min_ticks=40` may also be insufficient
   after spread-filtered gaps).

**Drawdown improvement is real but small** (-0.473% vs base -1.727%) — the
gate is doing *something* to risk, just at too high a PnL cost. This is a
hint that a softer/decay form of chop (rather than boolean skip) might
recover the worst losers without throwing away the edge.

**Highest-leverage next direction**: replace boolean chop-skip with a
*probabilistic* form (decay submission probability above chop_neutral=1.5
toward zero at chop_steep=3.0), mirroring island-2's actual semantics
rather than its threshold. If even probabilistic chop hurts ptg, declare
chop non-transferable to this base and pivot to a different orthogonal
axis (e.g., trade-side imbalance or recent-flow signed volume).

**Instrumentation counters** (`evaluated`, `skipped_position`,
`skipped_spread`, `skipped_chop`, `submitted`) are wired and emit every 500
skips; per-date breakdowns are recoverable from logs if needed for a
follow-up loop's diagnosis. Counters are not yet exported into
metrics.json — a future loop could surface them there.

**ASSUMPTION / DATA ISSUE — memory cap**: The 20260319 backtest run
initially failed under the default `RESEARCH_MEM_CAP_GB=16` cap and had to
be retried with `RESEARCH_MEM_CAP_GB=32`. All other 11 dates completed at
the default cap. This date appears to consume materially more memory in
this base; document for the operator — future ptg-lineage runs should
budget 32 GB for the train window to avoid retries. Not a code bug, but
worth noting that the train window's resource profile is not uniform.
