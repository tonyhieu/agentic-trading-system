# Algorithm Notes: afg-f-l6

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 6. Starting point: `afg-f-l5` (prior loop).

## Hypothesis

**Context available (full-trace, loop 6)**: full prior reasoning + NOTES.md
for `afg-f-l1`, `afg-f-l2`, `afg-f-l3`, `afg-f-l4`, and `afg-f-l5`, plus base
algo metrics. Total context_chars_in = 98,204 (~24,551 tokens).

Recap of the five-loop history of this arm:

- **Loop 1 (afg-f-l1)**: added `min_gross_volume = 8.0` floor (theory:
  thin-tape one-sided prints are noise). Result: realized_pnl **-9.18 %**
  vs base. Theory FALSIFIED on P&L — thin-tape one-sided prints carry
  genuine 30 s adverse signal. IS/P&L decoupling first documented.
- **Loop 2 (afg-f-l2)**: tightened `flow_threshold` 2.0 → 1.5; reverted
  loop 1's floor. Result: **byte-identical to base** (no-op). Root cause:
  MES `size` is integer-valued so `_net_flow` is integer-valued; any
  threshold in (1, 2] catches the same skip set. Methodological lesson:
  integer-equivalence classes; threshold tests must cross integer
  boundaries to change behaviour.
- **Loop 3 (afg-f-l3)**: tightened 1.5 → 1.0 (crossing into class (0, 1]).
  Result: realized_pnl **+10.39 %** vs base, sharpe **+0.836**,
  trade_count -1.66 %. Validated loop 1's mechanism at the new
  equivalence class. Level-threshold lever flagged as **saturated**
  (threshold = 0 is degenerate); remaining productive directions are
  structural.
- **Loop 4 (afg-f-l4)**: halved `window_seconds` 10.0 → 5.0 at
  threshold = 1.0. Result: realized_pnl **-0.34 %** vs base, -9.72 %
  vs loop 3. Root cause: at 5 s the deque is often empty (warm-up
  unconditional path fires more), and when non-empty |net_flow| is
  dominated by single-print noise. The gate becomes mostly a no-op AND
  the residual skips are noisier. **Durability wins decisively over
  freshness.** Empty-deque warm-up path identified as a meaningful axis
  at short windows.
- **Loop 5 (afg-f-l5)**: reverted to 10 s as the starting point and
  lengthened to 15 s — the priority direction from loop 4's
  forward-looking note. Result: realized_pnl **+13.20 %** vs base,
  **+2.54 %** vs loop 3 (best-in-arm); sharpe 6.732 (+1.14 vs base,
  +0.30 vs loop 3); trade_count -2.20 % vs base; drawdown best-in-arm
  (-0.0306 %); IS roughly base-equivalent (+1.30 %) — better than
  loop 3's IS (-3.53 % vs loop 3). The durability hypothesis extended
  past 10 s: more samples = better per-skip evidence quality.

Loop 5's forward-looking note made this loop's direction unambiguous and
prioritised it #1:

> "**Continue lengthening: `window_seconds = 20.0`** at the same
> `flow_threshold = 1.0`, `min_gross_volume = 0.0`. This is the natural
> extrapolation of loop 5's positive result *and* the test loop 4
> flagged as the degeneracy boundary. Either outcome is informative:
>   - If P&L improves further, the durability curve is still rising at
>     20 s and loop 7 should push to 25-30 s.
>   - If P&L flattens or falls, loop 5's 15 s is at or near the
>     optimum, and the loop-4-flagged degeneracy regime has begun.
> Loop 5's trade_count (-2.20 % vs base) gives headroom: the gate would
> have to compress trade_count to roughly 80,000-90,000 (a ~15-25 %
> cut) before anti-cascade alternation dominated. So 20 s is a clean
> diagnostic test point."

That is what afg-f-l6 does.

**Targeted change** (single behavioural knob): **`window_seconds`
15.0 → 20.0**. `flow_threshold = 1.0` and `min_gross_volume = 0.0`
preserved unchanged.

**Mechanism / why 20 s could continue the gains, or hit the degeneracy
boundary**:

- *Durability continues* (P&L up vs loop 5): Loops 4 → 5 established
  that 5 s loses and 15 s beats 10 s; the durability mechanism (more
  samples → higher per-skip SNR on |net_flow|; deque reliably populated)
  has not yet saturated. If the curve is still rising at 15 s, the
  20 s extension should produce a smaller but positive delta (typical
  diminishing-returns shape), e.g. pnl +1 % to +3 % vs loop 5.
- *Saturation* (P&L roughly equal to loop 5): the marginal information
  from 5 additional seconds of look-back may be small at this window
  length. The per-skip edge plateaus; trade_count drops slightly more;
  net P&L is flat to small-positive vs loop 5.
- *Early degeneracy* (P&L below loop 5): the long-window risk loop 4
  flagged for 20 s+ — that integer-running |net_flow| over 20 s is
  almost always ≥ 1 in MES day-session activity, so the gate fires on
  most orders and the algo collapses toward anti-cascade alternating
  semantics (every other order forced through by the `_position_flat`
  re-entry path). At full degeneracy trade_count would approach roughly
  half the base level (~50-55k); short of that, the regime is
  "near-degeneracy" — gate is too aggressive, skip set is too large,
  some good-edge entries are skipped, and per-skip edge declines.

The trade_count at loop 5 was 104,836 (97.8 % of base 107,198). The
near-degeneracy regime would manifest as trade_count materially below
~100k — say 85-95k — alongside flat-to-negative P&L vs loop 5. The full
degeneracy regime (trade_count near 50-55k) is structurally implausible
in a single 5 s window extension; the diagnostic is on the *gradient*
of trade_count between loop 5 and loop 6.

**Expected effect (concrete, in vs_base_* terms)**:

- realized_pnl: **+11 % to +16 % vs base** if durability continues
  (modest improvement on loop 5's +13.20 %); **+12 % to +14 % vs base**
  if saturation; **+5 % to +12 % vs base** if early degeneracy. In
  vs-loop-5 terms: -2 % to +3 %.
- trade_count: **slightly lower than loop 5** — expect 102,000 to
  104,500 (i.e. -2.5 % to -5 % vs base, -0.3 % to -2.5 % vs loop 5).
  A reading below 100,000 would signal near-degeneracy.
- sharpe: tracks P&L direction; expect 6.5 - 7.0 range.
- max_drawdown_pct: not expected to worsen materially; could improve
  marginally if more adverse skips are caught.
- mean_slippage: 0.0 vs 0.0 (zero-cost fill model).
- is_weighted_bps: continues the loop 5 trajectory — could improve
  further as per-skip evidence quality rises with more samples, or
  worsen if the longer window catches a larger fraction of
  good-fill-but-bad-30s-direction setups. Hard to predict; loop 5's
  partial IS/P&L recoupling is the most-recent data point.

**Risk**: The principal risk is the early-degeneracy regime described
above. If it materialises, P&L falls below loop 5 (but likely still
above base) and sharpe declines. The downside is bounded by reverting
the window in loop 7 if the result is bad. The upside (further gains)
gives loop 7 a clear push to 25-30 s. The genuine *unknown* is the
shape of the durability curve past 15 s — loops 4 → 5 established the
direction but not the saturation point or the degeneracy onset.

**Builds on**: `afg-f-l5` (prior loop). Structurally, the only
behavioural change is `window_seconds`: 15.0 → 20.0. All other
invariants (anti-cascade `_position_flat=True` after any skip,
reduce-only-orders-always-execute, quantity-invariant preserved, O(1)
running sums for both `_net_flow` and `_gross_volume`,
`flow_threshold = 1.0`, `min_gross_volume = 0.0`) are preserved
unchanged.

---

## Implementation Decisions

- **`window_seconds` default = 20.0.** Lengthened from afg-f-l5's
  15.0. This is the priority-1 direction from loop 5's forward-looking
  note, chosen because:
    (a) it directly extends loop 5's positive result on the same lever;
    (b) it is mechanistically informative either direction (saturation,
        continued gain, or early degeneracy);
    (c) it is the test loop 4 explicitly flagged as the degeneracy
        boundary, so the result settles a known open question.
- **`flow_threshold` default = 1.0.** Carried forward from afg-f-l3 /
  afg-f-l4 / afg-f-l5. Loop 3 established this as the proven operating
  point; loops 4-5 did not touch it; loop 6 does not touch it either.
  No methodological risk: 1.0 is still in equivalence class (0, 1] for
  any window length, since the gate condition is evaluated on
  integer-valued `_net_flow` at a single decision instant.
- **`min_gross_volume` default = 0.0.** Carried forward (loop 1's
  harmful feature remains reverted). Loop 5's NOTES.md flagged a hybrid
  small-floor variant at (window=15, threshold=1) as a low-priority
  alternative; with loop 6 testing the window lever further, the hybrid
  experiment is deferred to a later loop after the window saturation
  point is known. Re-examining the floor at the new operating point
  (whatever it turns out to be) is a natural candidate for loop 7 or
  loop 8.
- **No algorithmic structure changes.** Same deque, same O(1) running
  aggregates (`_net_flow`, `_gross_volume`), same prune logic, same
  `_flow_is_adverse` decision, same `on_order` routing, same
  anti-cascade and reduce-only paths. This isolates `window_seconds`
  as the single behavioural variable.
- **The `_gross_volume` tracking code is retained** (no-op at default
  `min_gross_volume = 0.0`) so a future loop can re-enable a floor
  without code churn. Cost is one running-sum maintenance, O(1).
- **Quantity invariant preserved**: orders are still only skipped or
  submitted whole; `order.quantity` is never touched.

**Look-ahead check**: identical to all prior loops in the arm.
`on_trade_tick` only appends; only trade ticks with
`ts_event <= order.ts_init` are present at decision time (replay is
strictly chronological; the prune uses `order.ts_init`, never a
future timestamp). Lengthening the window widens the look-*back* —
it does not change look-ahead semantics. The `cutoff_ns = ts_init -
window_ns` arithmetic remains correct for any window size.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20). Baseline `simple` read
from cache (`--use-cached-baseline`).

**Results — afg-f-l6 vs base algo `aggressor-flow-gate`:**

| metric             | afg-f-l6   | aggressor-flow-gate | delta                |
|--------------------|------------|---------------------|----------------------|
| realized_pnl       |   1521.25  |              1255.50|  **+21.17 %**        |
| mean_slippage      |   0.0      |              0.0    |   0.0 (both 0)       |
| sharpe_ratio       |   6.8631   |              5.5944 |  **+1.2687**         |
| max_drawdown_pct   |  -0.03372% |             -0.03325%|  -0.00048 pp (worse) |
| win_rate           |   0.35625  |              0.35488 |  +0.14 pp            |
| trade_count        | 104515     |           107198    |  **-2.50 %**         |
| is_weighted_bps    |   0.04652  |              0.04724 |  **-1.54 %** (better)|

(vs `simple` baseline: `vs_baseline_pnl_pct` = +875.16 %, comfortably
clearing the absolute pass-gate margin; relevant comparison for this
experiment is vs base above.)

**Results — afg-f-l6 vs `afg-f-l5` (loop 5, prior best-in-arm):**

| metric             | afg-f-l6   | afg-f-l5            | delta                |
|--------------------|------------|---------------------|----------------------|
| realized_pnl       |   1521.25  |              1421.25|  **+7.04 %**         |
| sharpe_ratio       |   6.8631   |              6.7321 |  +0.1310             |
| trade_count        | 104515     |           104836    |  -0.31 % (~flat)     |
| is_weighted_bps    |   0.04652  |              0.04786 |  -2.80 % (better)    |
| max_drawdown_pct   |  -0.03372% |             -0.03057%|  -0.00316 pp (worse) |

**Hypothesis verdict: SUPPORTED — durability continues to help, no
sign of degeneracy at 20 s.** The result lands at or above the upper
end of the predicted "durability continues" range (+11 % to +16 % vs
base): +21.17 % vs base, +7.04 % vs loop 5. This is the strongest
result in this arm and considerably exceeds the diminishing-returns
prior I held going in.

- **Realized P&L: +21.17 % vs base, +7.04 % vs loop 5** — well above
  the predicted +11 % to +16 %. The marginal P&L from the 5 s window
  extension (15 s → 20 s) is larger than the marginal P&L from the
  prior 5 s extension (10 s → 15 s): +2.54 % vs loop 3 → +7.04 % vs
  loop 5. The durability curve is, if anything, *accelerating* in this
  range rather than flattening. Hypotheses for why: (a) per-skip SNR
  is sub-linear in window length but the *skip set* itself is also
  growing modestly (-0.31 % vs loop 5 trade_count), and the combined
  effect on per-skip edge × skip-count multiplies favorably; (b) at
  longer windows the gate is catching multi-print "sustained pressure"
  patterns that single-print noise at shorter windows missed entirely.
  Either way, the empirical signal is clear — the optimum is past 20 s.
- **Sharpe: +1.27 vs base, +0.13 vs loop 5** — best-in-arm. The
  vs-loop-5 sharpe gain is smaller than the vs-loop-5 P&L gain because
  variance also rose modestly (the per-trade outcomes on retained
  trades have slightly wider spread). Still a clean directional gain.
- **Trade count: -2.50 % vs base, -0.31 % vs loop 5** — essentially
  flat vs loop 5 despite the 33 % longer window. This is the most
  diagnostically important number this loop: it rules out the
  early-degeneracy regime decisively. If degeneracy were beginning,
  trade_count would have fallen meaningfully (the loop 5 NOTES
  predicted 85-95k as the near-degeneracy signal; we are at 104,515,
  well above that floor). The 20 s window is still in the selective-
  gate regime. **The degeneracy boundary loop 4 flagged for 20 s+ has
  not materialised at 20 s.** This is informative: the actual
  degeneracy onset is past 20 s, suggesting 25 s and possibly 30 s are
  still in the productive range.
- **Drawdown: -0.0337 % vs base -0.0333 %** — slightly worse than base
  (-0.00048 pp) and worse than loop 5 (-0.00316 pp). Within noise but
  the only metric that regressed vs loop 5. Hypothesis: with the
  longer window catching more skips, the few skips that are
  *wrong-directional* (formerly favorable entries) cluster more
  tightly in time, producing slightly larger short-run drawdown
  fluctuations on retained trades. Worth watching but not concerning
  at this magnitude (-0.00048 pp vs base is essentially noise).
- **Win rate: +0.14 pp vs base** — slight improvement; same pattern
  as prior loops (edge comes from average-outcome shift on
  retained/skipped trades, not a categorical win-rate rotation).
- **is_weighted_bps: -1.54 % vs base, -2.80 % vs loop 5** — IS
  improved on both axes. This is a notable extension of the partial
  IS/P&L recoupling loop 5 documented. The 20 s window's per-skip
  evidence quality is high enough that the skipped trades are, on
  average, *not* favorable-fill candidates — they are genuinely
  adverse-flow setups. The IS/P&L decoupling from loops 1 and 3 is
  now substantially relieved at this operating point.

**Interpretation.** Four pieces of evidence agree: the durability
mechanism for the aggressor-flow gate continues to strengthen with
longer look-back windows up to at least 20 s, with no evidence of the
degeneracy boundary loop 4 flagged. The combined operating point
(window=20, threshold=1, floor=0) is best-in-arm on P&L, sharpe, and
IS simultaneously — only drawdown shows a small (noise-level)
regression vs loop 5. The window-length lever has further headroom
than loop 5's prior suggested: the gain from 15 s → 20 s exceeded the
gain from 10 s → 15 s, suggesting the curve is not yet near saturation.

**Direction for loop 7.** Loop 6's evidence narrows the priors
substantially. In priority order:

  1. **Continue lengthening: `window_seconds = 30.0`** (rather than
     25 s) at the same threshold = 1.0, floor = 0.0. Reasoning: the
     marginal gain accelerated from loop 5 (+2.54 % vs loop 3) to
     loop 6 (+7.04 % vs loop 5), and trade_count barely moved (-0.31 %
     vs loop 5). This argues that the next test point should be
     larger than the prior 5 s step — a 10 s extension (20 s → 30 s)
     gives a clearer diagnostic of either continued gain or the long-
     delayed onset of degeneracy. The trade_count headroom at 20 s
     (104,515 = 97.5 % of base) is still substantial; 30 s would
     have to cut trade_count to ~85,000 (a 19 % drop from current) to
     hit the near-degeneracy floor.
       - If pnl improves further at 30 s: durability extends past 30 s
         and loop 8 pushes to 45-60 s.
       - If pnl is comparable at 30 s: saturation around 20-30 s; loop
         8 explores a different lever (hybrid floor, asymmetric).
       - If pnl falls at 30 s: degeneracy onset between 20 s and 30 s;
         loop 8 calibrates the exact knee with 25 s or returns to the
         (now-best) 20 s and pursues a different structural lever.
     **The 30 s jump is the higher-information test than 25 s.**

  2. **Conservative variant: `window_seconds = 25.0`** — smaller step,
     lower information return, more granular calibration. Use this
     only if loop 7 prefers conservative steps; the loop 6 evidence
     favours the larger jump above.

  3. **Hybrid: small gross-volume floor at (window=20, threshold=1).**
     The natural follow-up if window-length saturation has been
     reached. Loop 4's NOTES.md flagged this as a low-priority
     alternative; with loop 6's success on window-lengthening, the
     hybrid test is naturally deferred again. Re-examining the
     floor at whatever turns out to be the final window optimum
     (probably loop 8 territory) is the right ordering.

  4. **Asymmetric thresholds** at (window=20, threshold=1): unchanged
     priority (lower than the window lever while window-lever gains
     continue).

  5. **Flow acceleration / first-difference**: unchanged priority
     (structural change, defer until simpler levers stop yielding).

**What NOT to try in loop 7**: any further window shortening
(empirically inferior per loop 4); any non-integer-boundary threshold
tweak at threshold = 1 (per loop 2's discretisation lesson); large
min_gross_volume (per loop 1's strong negative).

**Methodological note.** This loop continues the pattern established
by loops 4 → 5: the full-trace context channel enabled the loop to
make the *exact* targeted change priority-1'd by the prior loop, with
full understanding of (a) the durability mechanism (loop 4), (b) the
diagnostic value of trade_count as a degeneracy proxy (loop 5), and
(c) the integer-quantisation rule (loop 2) that fixed the threshold
lever. The loop 6 result is the third consecutive win on the window-
length lever — each step has been correctly motivated by the prior
loop's micro-analysis, not just its headline metric. The trade_count
diagnostic loop 5 introduced (84-95k = near-degeneracy floor) was
particularly useful this loop: a metrics-only mode reading loop 6's
trade_count (-2.50 % vs base) would not know whether that was
"selective gate" or "edge of degeneracy"; full trace makes it clear it
is still firmly in the selective regime, justifying the priority-1
push to 30 s.

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero
fill-cost model), so `vs_base_slippage_pct` is reported as 0.0 by
convention and carries no information this loop.

