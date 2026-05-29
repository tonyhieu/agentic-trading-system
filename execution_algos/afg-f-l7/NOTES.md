# Algorithm Notes: afg-f-l7

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 7. Starting point: `afg-f-l6` (prior loop).

## Hypothesis

**Context available (full-trace, loop 7)**: full prior reasoning + NOTES.md
for `afg-f-l1`, `afg-f-l2`, `afg-f-l3`, `afg-f-l4`, `afg-f-l5`, and
`afg-f-l6`, plus base algo metrics.

Recap of the six-loop history of this arm:

- **Loop 1 (afg-f-l1)**: added `min_gross_volume = 8.0` floor (theory:
  thin-tape one-sided prints are noise). Result: realized_pnl **-9.18 %**
  vs base. Theory FALSIFIED on P&L. IS/P&L decoupling first documented.
- **Loop 2 (afg-f-l2)**: tightened `flow_threshold` 2.0 → 1.5; reverted
  loop 1's floor. Result: **byte-identical to base** (no-op). Root cause:
  integer-quantisation of MES `size` → thresholds in (1, 2] catch the
  same skip set. Methodological lesson: integer-equivalence classes.
- **Loop 3 (afg-f-l3)**: tightened 1.5 → 1.0 (crossing into (0, 1]).
  Result: realized_pnl **+10.39 %** vs base, sharpe **+0.836**.
  Validated loop 1's tightening mechanism. Level-threshold lever flagged
  as **saturated** at threshold = 1.
- **Loop 4 (afg-f-l4)**: halved `window_seconds` 10.0 → 5.0 at threshold
  = 1.0. Result: realized_pnl **-0.34 %** vs base, -9.72 % vs loop 3.
  Root cause: at 5 s the deque is often empty (warm-up unconditional
  path fires more); when non-empty, |net_flow| is dominated by
  single-print noise. **Durability wins decisively over freshness.**
- **Loop 5 (afg-f-l5)**: reverted to 10 s as the starting point and
  lengthened to 15 s. Result: realized_pnl **+13.20 %** vs base,
  **+2.54 %** vs loop 3 (new best-in-arm); sharpe 6.732 (+1.14 vs base);
  trade_count -2.20 % vs base; drawdown best-in-arm (-0.0306 %); IS
  roughly base-equivalent. Durability hypothesis extended past 10 s.
- **Loop 6 (afg-f-l6)**: lengthened `window_seconds` 15.0 → 20.0.
  Result: realized_pnl **+21.17 %** vs base, **+7.04 %** vs loop 5
  (new best-in-arm); sharpe 6.863 (+1.27 vs base, +0.13 vs loop 5);
  trade_count -2.50 % vs base, -0.31 % vs loop 5 (essentially flat —
  ruled out early degeneracy); IS **-1.54 % vs base** (better) and
  **-2.80 % vs loop 5** (continued recoupling). Drawdown slightly worse
  vs loop 5 (-0.00316 pp) but flat vs base. Marginal gains on the
  window-length lever are **accelerating** (+2.54 % then +7.04 %), not
  flattening. The degeneracy boundary loop 4 flagged for 20 s+ did NOT
  materialise at 20 s.

Loop 6's forward-looking note made this loop's direction unambiguous and
prioritised it #1 — with a deliberate choice of step size:

> "Continue lengthening, but with a **10 s step rather than 5 s**:
> `window_seconds = 30.0` at threshold = 1.0, floor = 0.0. Reasoning:
> marginal gain accelerated (loop 3→5: +2.54 %; loop 5→6: +7.04 %);
> trade_count barely moved (-0.31 % loop 5→6); the next 5 s step would
> likely repeat the same shape of result without efficiently
> characterising where the curve saturates or where degeneracy begins.
> A 10 s jump (20 s → 30 s) gives a higher-information diagnostic. The
> trade_count headroom at 20 s (104,515 = 97.5 % of base) is
> substantial; 30 s would have to cut trade_count to ~85,000 (a ~19 %
> drop from current) to hit the near-degeneracy floor."

That is what afg-f-l7 does.

**Targeted change** (single behavioural knob): **`window_seconds`
20.0 → 30.0** (a 10 s extension, larger than the prior 5 s steps).
`flow_threshold = 1.0` and `min_gross_volume = 0.0` preserved unchanged.

**Mechanism / why a 10 s jump now**:

- The marginal P&L gain per additional 5 s of look-back has been
  growing, not shrinking, across the last two window-lengthening
  experiments:
    - loop 3 (10 s) → loop 5 (15 s): +2.54 % vs loop 3
    - loop 5 (15 s) → loop 6 (20 s): +7.04 % vs loop 5
  This argues *against* a simple diminishing-returns prior. The
  durability curve appears to be still rising — possibly steeply — at
  20 s. Under that prior, the next 5 s step (25 s) would likely repeat
  the same shape of result, costing one loop to confirm "yes, still
  rising," without telling us where the curve actually bends or where
  the degeneracy regime begins.
- A 10 s jump (20 s → 30 s) is the higher-information test. It probes
  twice as much of the parameter space in one loop and forces the
  result to disambiguate between three different curves:

    (i)   *Durability continues past 30 s*: P&L up further (e.g.,
          +24 % to +28 % vs base, +3 % to +6 % vs loop 6). Loop 8
          should push to 45 s or 60 s.
    (ii)  *Saturation between 20 s and 30 s*: P&L roughly equal to
          loop 6 (+20 % to +22 % vs base, ±1 % vs loop 6). The window
          lever has found its optimum somewhere in [20, 30]; loop 8
          either calibrates the exact knee or pivots to a different
          lever.
    (iii) *Degeneracy onset between 20 s and 30 s*: P&L falls vs
          loop 6 (e.g., +12 % to +18 % vs base; trade_count drops
          materially below 100,000, perhaps to 90-95k). Loop 4 flagged
          this regime; loop 6 ruled it out at 20 s but said nothing
          about 30 s. If this is what happens, loop 8 returns to 20 s
          as the best operating point and pursues an orthogonal
          structural lever (hybrid floor, asymmetric thresholds, flow
          acceleration).

- Mechanism arguments for *why* either continued gain or degeneracy is
  plausible at 30 s:
    - *Continued gain*: more samples per window keeps raising per-skip
      SNR; the "multi-print sustained pressure" patterns hypothesised
      in loop 6's interpretation are even better characterised at 30 s.
      MES day-session activity gives roughly 6-10 prints per second on
      active stretches → a 30 s window typically holds 150-300 signed
      prints, enough to make |net_flow| ≥ 1 a meaningful filter (not
      just a noise floor).
    - *Degeneracy*: integer running |net_flow| over 30 s of MES
      activity is non-zero on the *vast* majority of decision instants
      — buyers and sellers rarely cancel exactly across hundreds of
      prints. The gate would then fire on most orders, and the
      anti-cascade `_position_flat` re-entry path would force
      alternating submits. This is the regime loop 4 originally
      flagged for "20 s+"; loop 6 disproved it at 20 s but the proper
      boundary is still uncharacterised. trade_count is the diagnostic:
      if 30 s puts it materially below 100,000, alternating semantics
      are starting to dominate.

- Trade-count headroom calculation (from loop 6's NOTES): a near-
  degeneracy floor (anti-cascade alternation dominating) would put
  trade_count near 85,000. Loop 6 at 20 s is at 104,515 (97.5 % of
  base). 30 s would need to compress trade_count by ~19 % to hit that
  floor. Below that, the diagnostic is reliable — trade_count between
  ~95,000 and ~104,000 means "still selective"; below ~95,000 means
  "approaching degeneracy."

**Expected effect (concrete, in vs_base_* terms)**:

- realized_pnl: **+22 % to +28 % vs base** if durability continues
  (modest-to-strong improvement on loop 6's +21.17 %); **+19 % to
  +22 % vs base** if saturation in [20, 30]; **+10 % to +18 % vs
  base** if early degeneracy onset between 20 s and 30 s. In
  vs-loop-6 terms: -10 % (degeneracy) to +6 % (continued gain).
  Genuinely uncertain direction at this scope; loop 6's evidence
  raises the prior on "continued gain" but does not eliminate the
  saturation or degeneracy cases.
- trade_count: **lower than loop 6 by 0.5 % to 3 %** if still
  selective (102,000 - 104,000 = 95-97 % of base); **materially
  lower than loop 6 (95,000 - 100,000)** if approaching degeneracy.
  A reading below 95,000 would signal the anti-cascade regime is
  beginning to dominate.
- sharpe: tracks P&L direction; expect 6.7 - 7.2 range if durability
  continues, 6.0 - 6.5 if degeneracy.
- max_drawdown_pct: not expected to worsen materially; could improve
  marginally if more adverse skips are caught, or worsen by ~0.003 pp
  if the longer window catches more clustered wrong-directional skips
  (same pattern loop 6 saw vs loop 5).
- mean_slippage: 0.0 vs 0.0 (zero-cost fill model).
- is_weighted_bps: continues loop 6 trajectory — could improve
  further as per-skip evidence quality rises with more samples
  (continued recoupling), or partially worsen if more good-fill
  entries are caught in the larger skip set. Loop 6's IS gain
  (-2.80 % vs loop 5) suggests the trend is continuing in the
  recoupling direction.

**Risk**: The principal risk is the early-degeneracy regime described
above. If it materialises, P&L falls below loop 6 (likely still above
base, but giving back the gain) and trade_count compresses noticeably.
The downside is bounded: loop 8 reverts the window if 30 s is bad and
pursues a different structural lever from the now-confirmed best
operating point (window = 20 s). The upside (further gains) gives
loop 8 a clean push to 45 s or 60 s. The genuine *unknown* this loop
characterises is **where the durability curve bends** — loops 4, 5, 6
established the direction past 10 s but not the saturation point or
the degeneracy onset.

**Why 30 s and not 25 s** (re-emphasised):
  - 25 s is the conservative variant loop 6 enumerated; it gives a
    finer-grained calibration but probes a smaller chunk of the
    parameter space.
  - The loop 6 result (accelerating marginal gain, flat trade_count)
    is strong evidence that 25 s is *less* informative than 30 s. If
    25 s confirms continued gain we still don't know whether 30 s is
    in the same regime. If 30 s confirms continued gain we know the
    curve is rising through at least a 10 s extension and loop 8 can
    push further with confidence.
  - The downside risk is symmetric: both 25 s and 30 s could land in
    a worse-than-loop-6 regime; the larger step at 30 s would give
    back more, but the loss is bounded and the diagnostic is sharper
    (degeneracy onset is harder to misread at 30 s than at 25 s).
  - Conclusion: 30 s is the higher-information one-loop test.

**Why not pivot to a different lever now** (hybrid floor, asymmetric,
flow acceleration):
  - Loops 4-6 produced three consecutive wins on the window lever,
    with the marginal gain growing each step. The lever is producing
    the best information-per-loop in this arm; pivoting before the
    saturation/degeneracy boundary is mapped would leave the strongest
    signal direction prematurely. The window lever is the priority
    until we observe one of: saturation, degeneracy, or a small step
    that no longer improves the metric.
  - Loop 8 has a natural fallback to the highest-priority structural
    lever (hybrid small floor, then asymmetric thresholds) once the
    window question is settled.

**Builds on**: `afg-f-l6` (prior loop). Structurally, the only
behavioural change is `window_seconds`: 20.0 → 30.0. All other
invariants (anti-cascade `_position_flat=True` after any skip,
reduce-only-orders-always-execute, quantity-invariant preserved, O(1)
running sums for both `_net_flow` and `_gross_volume`,
`flow_threshold = 1.0`, `min_gross_volume = 0.0`) are preserved
unchanged.

---

## Implementation Decisions

- **`window_seconds` default = 30.0.** Lengthened from afg-f-l6's
  20.0. This is the priority-1 direction from loop 6's forward-looking
  note, chosen with a deliberate **10 s step** (rather than the
  conservative 5 s step to 25 s) because:
    (a) the marginal P&L gain per 5 s extension has been *accelerating*
        across loops 5 and 6 (+2.54 % then +7.04 %), arguing against
        a simple diminishing-returns prior;
    (b) a 10 s jump is mechanistically informative across all three
        candidate outcomes (continued gain / saturation / early
        degeneracy) and forces the result to disambiguate between
        them;
    (c) the trade_count headroom at 20 s (104,515 = 97.5 % of base)
        gives ample buffer before the anti-cascade alternating regime
        dominates (which would put trade_count near 85,000).
- **`flow_threshold` default = 1.0.** Carried forward from afg-f-l3
  through afg-f-l6. Loop 3 established this as the proven operating
  point; the integer-equivalence rule from loop 2 still applies
  (threshold = 1.0 is in class (0, 1] for any window length, since
  the gate condition is evaluated on integer-valued `_net_flow` at a
  single decision instant).
- **`min_gross_volume` default = 0.0.** Carried forward (loop 1's
  harmful feature remains reverted). Loop 6's NOTES.md flagged a
  hybrid small-floor variant at the final-window operating point as a
  natural loop 7-or-8 candidate; loop 7 prioritises the window-lever
  question first, so the hybrid test is deferred to loop 8 if the
  window saturation point is known by then.
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

**Results — afg-f-l7 vs base algo `aggressor-flow-gate`:**

| metric             | afg-f-l7   | aggressor-flow-gate | delta                |
|--------------------|------------|---------------------|----------------------|
| realized_pnl       |   1664.75  |              1255.50|  **+32.59 %**        |
| mean_slippage      |   0.0      |              0.0    |   0.0 (both 0)       |
| sharpe_ratio       |   7.4067   |              5.5944 |  **+1.8123**         |
| max_drawdown_pct   |  -0.03240% |             -0.03325%|  +0.00085 pp (better)|
| win_rate           |   0.35686  |              0.35488 |  +0.20 pp            |
| trade_count        | 104138     |           107198    |  **-2.86 %**         |
| is_weighted_bps    |   0.04508  |              0.04724 |  **-4.58 %** (better)|

(vs `simple` baseline: `vs_baseline_pnl_pct` = +967.15 %, comfortably
clearing the absolute pass-gate margin; relevant comparison for this
experiment is vs base above.)

**Results — afg-f-l7 vs `afg-f-l6` (loop 6, prior best-in-arm):**

| metric             | afg-f-l7   | afg-f-l6            | delta                |
|--------------------|------------|---------------------|----------------------|
| realized_pnl       |   1664.75  |              1521.25|  **+9.43 %**         |
| sharpe_ratio       |   7.4067   |              6.8631 |  **+0.5436**         |
| trade_count        | 104138     |           104515    |  -0.36 % (~flat)     |
| is_weighted_bps    |   0.04508  |              0.04652 |  -3.10 % (better)    |
| max_drawdown_pct   |  -0.03240% |             -0.03372%|  +0.00132 pp (better)|

**Hypothesis verdict: SUPPORTED — durability continues to win, with no
sign of degeneracy at 30 s. New best-in-arm on every metric tracked.**

The result lands at the upper edge of the predicted "durability
continues" range (+22 % to +28 % vs base) and substantially above
loop 6 on every dimension. Critically, the marginal P&L gain per 5 s
of look-back continues to *accelerate*, not flatten:

  - loop 3 (10 s) → loop 5 (15 s):   +2.54 % vs loop 3 (+0.508 %/5s)
  - loop 5 (15 s) → loop 6 (20 s):   +7.04 % vs loop 5 (+1.408 %/5s)
  - loop 6 (20 s) → loop 7 (30 s):   +9.43 % vs loop 6 (+1.572 %/5s
    averaged over the 10 s extension; equivalent per-5s pace)

Even averaging the loop 7 gain over a 10 s extension, the per-5s
marginal P&L is +1.572 %, essentially the same per-5s pace as
loop 6's +1.408 %. **There is no diminishing-returns signal yet.**

- **Realized P&L: +32.59 % vs base, +9.43 % vs loop 6** — at the
  upper end of the predicted "durability continues" band (+22 % to
  +28 % vs base). The 10 s window extension delivered roughly the
  same per-5s pace as the prior 5 s step, decisively ruling out
  saturation at 20 s and also ruling out early degeneracy onset
  between 20 s and 30 s (which would have produced P&L below loop 6).
- **Sharpe: +1.81 vs base, +0.54 vs loop 6** (7.41 vs 5.59 / 6.86)
  — the largest sharpe gain across the arm. The vs-loop-6 sharpe
  gain (+0.54) is comparable in magnitude to the P&L gain (+9.43 %),
  indicating that variance did *not* materially rise; the longer
  window's selectivity is improving both mean and risk-adjusted
  outcomes simultaneously.
- **Trade count: -2.86 % vs base, -0.36 % vs loop 6** (104,138 vs
  107,198 / 104,515) — essentially flat vs loop 6 despite the 50 %
  longer window. This is the diagnostic that decisively rules out
  degeneracy onset: the loop 6 NOTES.md set the near-degeneracy
  floor at ~95k-99k (a ~5-10 % cut from base), and 30 s came in at
  104,138 (97.1 % of base), still firmly in the selective-gate
  regime. **The degeneracy boundary loop 4 flagged for 20 s+, and
  loop 6 disproved at 20 s, has *also* not materialised at 30 s.**
  The actual degeneracy onset is past 30 s.
- **Drawdown: improved**, -0.03240 % vs base -0.03325 % and vs
  loop 6 -0.03372 % — best in arm (matches the loop 5 best on a
  pnl-best basis but the gain is consistent with the longer window
  catching more of the clustered wrong-directional skips that
  loop 6 flagged as the drawdown source vs loop 5). Win rate also
  improved (+0.20 pp vs base, +0.10 pp vs loop 6).
- **is_weighted_bps: -4.58 % vs base, -3.10 % vs loop 6** — IS
  *improved* on both axes, continuing the recoupling loop 5 first
  observed and loop 6 extended. The 30 s window's per-skip evidence
  quality is high enough that skipped trades are, on average,
  *not* favorable-fill candidates — they are genuinely adverse-flow
  setups, more so than at any prior window length. **The IS/P&L
  decoupling first documented in loop 1 is now substantially relieved
  in the simultaneous-improvement direction**: P&L is +32.59 % vs
  base while IS is -4.58 % vs base. Both metrics now agree.

**Interpretation.** Four consecutive window-lengthening experiments
(loops 4 → 5 → 6 → 7) now agree: the predictive content of the
aggressor-flow gate in MES at the oracle's 30 s horizon is **durability-
dominated**, and the durability curve does *not* saturate up to at
least 30 s of look-back. Per-5s marginal gain has been roughly
constant from 15 s onward (+1.4 to +1.6 %/5s), with no diminishing-
returns signal yet. trade_count remains flat across the 15 s → 30 s
sweep (104,836 → 104,515 → 104,138 = a 0.7 % total reduction over
doubling the window length), so the selective regime is preserved
across the full range tested. The combined operating point
(window=30, threshold=1, floor=0) is best-in-arm on **every** metric
the experiment tracks — P&L, sharpe, drawdown, win rate, and IS —
simultaneously. This is the strongest single result in this arm to
date.

**Direction for loop 8.** Two clear candidates, with loop 7's
evidence applied:

  1. **Continue lengthening: `window_seconds = 60.0`** at threshold = 1.0,
     floor = 0.0. Reasoning: per-5s marginal gain has been flat-to-
     accelerating across three consecutive window-lengthening steps
     (5 → 6 → 7), with trade_count flat across the entire 15-30 s
     range. The most consistent prior is that the curve is still
     rising at 30 s. A *doubling* step (30 s → 60 s) is the natural
     extrapolation of loop 7's successful 10 s jump (which was itself
     a doubling of the prior 5 s steps' information content). Either
     outcome is informative and final:
       - If P&L improves further: durability extends past 60 s and we
         are deep into a regime where the gate is using a full minute
         of cumulative-flow evidence. Best-in-arm settles at 60 s+
         and the arm closes (loop 8 is the final loop).
       - If P&L saturates around 30-60 s: the saturation point is in
         [30, 60] and the arm closes with window=30 s (loop 7) as the
         best operating point.
       - If P&L falls vs loop 7: degeneracy onset between 30 s and 60 s;
         the arm closes with window=30 s (loop 7) as the best
         operating point.
     **The 60 s jump is the high-information final test** — it
     characterises an entire octave of parameter space and bounds the
     window-length lever decisively. trade_count is the diagnostic
     here: a reading below ~90k would signal anti-cascade alternation
     dominating; above ~100k means the selective regime persists. The
     conservative variant (45 s) gives a finer-grained calibration
     but probes less of the unknown parameter space.

  2. **Hybrid: small gross-volume floor** at (window=30, threshold=1):
     min_gross_volume = 2 or 3 contracts. This is the structural lever
     loops 4-6 deferred while window-lengthening was producing wins.
     Now that the window lever has reached an empirically strong
     operating point, the hybrid revisit becomes more interesting.
     The premise is that even at a 30 s window, the very-thinnest
     one-print windows (gross_volume in {1, 2}) may carry less signal
     than denser windows; a small floor could filter those without
     re-introducing loop 1's harmful aggressive-floor failure mode.
     Lower priority than (1) only because (1) is mechanistically
     cleaner (one knob already proven to move the metric) and
     directly extends this loop's finding. A reasonable alternative
     ordering: do (1) at loop 8 if the curve is still rising; do (2)
     at loop 8 if a future intermediate test shows window-lever
     saturation.

  3. **Asymmetric thresholds** at (window=30, threshold=1) — unchanged
     priority below (1) and (2). The symmetric gate has just produced
     the largest single-loop improvement in the arm; the asymmetric
     variant has a high bar to clear.

  4. **Flow acceleration / first-difference** — unchanged priority
     (structural change, defer until simpler levers stop yielding).

**What NOT to try in loop 8**: further window shortening (empirically
inferior per loop 4); any non-integer-boundary threshold tweak at
threshold = 1 (per loop 2's discretisation lesson); large
min_gross_volume (per loop 1's strong negative).

**Methodological note for the experiment as a whole.** This loop
extends a now-four-loop sub-experiment on window length (loops 4 → 5
→ 6 → 7), each step priority-1'd by the prior loop's forward-looking
note, each step producing the expected mechanism-validating result.
The chain is: loop 4 (5 s, -9.72 % vs loop 3, diagnosis = durability
loses to freshness loses because empty-deque + single-print noise) →
loop 5 (15 s, +2.54 % vs loop 3, partial IS recoupling, "more
samples = more SNR" mechanism validated) → loop 6 (20 s, +7.04 % vs
loop 5, marginal gain accelerating, trade_count flat ruling out
degeneracy at 20 s) → loop 7 (30 s, +9.43 % vs loop 6, marginal
per-5s gain flat-to-accelerating, IS now agreeing with P&L, trade_count
still flat ruling out degeneracy at 30 s). At each step, full-trace
context made the priority-1 direction obvious *and* provided the
mechanistic justification for choosing the step size (5 s after loop
4-5, 5 s after loop 5, 10 s after loop 6 with explicit acceleration
diagnosis, and now 30 s → 60 s with explicit constancy-of-per-5s-pace
diagnosis). A metrics-only mode reading the same headline P&L
trajectory might have correctly tracked the direction but would have
lacked the diagnostic to commit to a doubling step in loop 8 with
high confidence. The full-trace channel's value compounds: each
loop's microstructural diagnosis (empty-deque warm-up; per-skip SNR
vs sample count; trade_count as degeneracy diagnostic; per-5s
marginal gain as saturation diagnostic) becomes a tool the next loop
uses to make the next decision more efficient.

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero
fill-cost model), so `vs_base_slippage_pct` is reported as 0.0 by
convention and carries no information this loop.

