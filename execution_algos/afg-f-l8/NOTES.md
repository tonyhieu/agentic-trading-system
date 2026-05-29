# Algorithm Notes: afg-f-l8

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 8 (**final loop** of the arm). Starting point: `afg-f-l7`
(prior loop).

## Hypothesis

**Context available (full-trace, loop 8)**: full prior reasoning + NOTES.md
for `afg-f-l1` through `afg-f-l7`, plus base algo metrics. Total
context_chars_in ≈ 159,186 (~39,797 tokens). This is the largest context
window in the arm and the experiment's per-iteration context-cost budget for
this loop is at its peak.

Recap of the seven-loop history of this arm (compressed):

- **Loop 1 (afg-f-l1)**: added `min_gross_volume = 8.0` floor. Result:
  realized_pnl **-9.18 %** vs base. Theory ("thin-tape one-sided prints are
  noise") FALSIFIED on P&L. IS/P&L decoupling first documented.
- **Loop 2 (afg-f-l2)**: tightened `flow_threshold` 2.0 → 1.5; reverted
  loop 1's floor. Result: **byte-identical to base** (no-op). Root cause:
  MES `size` is integer-valued so `_net_flow` is integer-valued; thresholds
  in (1, 2] all catch the same skip set. **Integer-equivalence-class rule.**
- **Loop 3 (afg-f-l3)**: tightened 1.5 → 1.0 (crossing into (0, 1]). Result:
  realized_pnl **+10.39 %** vs base, sharpe **+0.836**. Validated loop 1's
  tightening mechanism. Level-threshold lever **saturated** at threshold = 1.
- **Loop 4 (afg-f-l4)**: halved `window_seconds` 10.0 → 5.0. Result: pnl
  **-0.34 %** vs base, -9.72 % vs loop 3. **Durability beats freshness
  decisively.** Empty-deque warm-up + single-print noise.
- **Loop 5 (afg-f-l5)**: lengthened 10.0 → 15.0. Result: pnl **+13.20 %**
  vs base, +2.54 % vs loop 3 (new best-in-arm). Durability hypothesis
  extends past 10 s. Partial IS recoupling.
- **Loop 6 (afg-f-l6)**: lengthened 15.0 → 20.0. Result: pnl **+21.17 %**
  vs base, +7.04 % vs loop 5 (new best-in-arm). Marginal gain
  **accelerating**. trade_count flat vs loop 5 ruled out degeneracy at 20 s.
- **Loop 7 (afg-f-l7)**: lengthened 20.0 → 30.0 (10 s jump rather than 5 s,
  motivated by loop 6's accelerating-marginal-gain diagnosis). Result: pnl
  **+32.59 %** vs base, +9.43 % vs loop 6 (new best-in-arm); sharpe 7.407
  (+1.81 vs base, +0.54 vs loop 6); trade_count -2.86 % vs base, -0.36 % vs
  loop 6 (still flat); IS **-4.58 % vs base** (better) — IS/P&L decoupling
  now substantially relieved in the *simultaneous-improvement* direction.
  Best-in-arm on **every** metric tracked. Per-5s marginal P&L pace flat
  across loops 5 → 6 → 7 (+1.41, +1.57 %/5s averaged) — no diminishing-
  returns signal yet.

Loop 7's forward-looking note made this loop's direction unambiguous and
prioritised it #1 — with a deliberate choice of step *size*:

> "Continue lengthening with a **DOUBLING step**: `window_seconds = 60.0`
> at threshold = 1.0, floor = 0.0. Reasoning: per-5s marginal gain has
> been flat-to-accelerating across three consecutive lengthening steps;
> trade_count has been flat across the entire 15-30 s range. The most
> consistent prior is that the curve is still rising at 30 s. A doubling
> step (30 s → 60 s) is the natural extrapolation of loop 7's successful
> 10 s jump (which was itself a doubling of the prior 5 s information
> content). It probes an entire octave of unknown parameter space in one
> loop and bounds the window-lever definitively. trade_count is the
> diagnostic: a reading below ~90k would signal anti-cascade alternation
> dominating; above ~100k means the selective regime persists."

That is what afg-f-l8 does.

**Targeted change** (single behavioural knob): **`window_seconds`
30.0 → 60.0** (a doubling step, the largest single step in the arm's
window-sweep). `flow_threshold = 1.0` and `min_gross_volume = 0.0`
preserved unchanged.

**Mechanism / why a doubling step now and what each outcome would mean**:

A doubling step in a parameter where the *per-5s* marginal gain has been
flat-to-rising across three consecutive smaller steps is the natural
extrapolation, not a wild jump. The justification chain is explicit:

- Per-5s marginal P&L gain history on the window lever:
    - loop 3 (10 s) → loop 5 (15 s):  +2.54 % vs loop 3  (+0.508 %/5s)
    - loop 5 (15 s) → loop 6 (20 s):  +7.04 % vs loop 5  (+1.408 %/5s)
    - loop 6 (20 s) → loop 7 (30 s):  +9.43 % vs loop 6  (+1.572 %/5s)
  The pace has not been diminishing across any step (it accelerated from
  loop 3-5 to loop 5-6, then was nearly constant from loop 5-6 to loop
  6-7 averaged over a 10 s extension). Linear extrapolation of the most
  recent per-5s pace would predict ~+9-12 % vs loop 7 at 60 s; that is the
  "durability-continues" prior.
- trade_count history across the window sweep (selectivity diagnostic):
    - base (10 s):            107,198 (100.0 %)
    - loop 5 (15 s):          104,836 ( 97.8 %)
    - loop 6 (20 s):          104,515 ( 97.5 %)
    - loop 7 (30 s):          104,138 ( 97.1 %)
  Over a 3× expansion of the window (10 → 30 s), trade_count contracted by
  only 2.9 percentage points. The selective regime is robust across the
  full range tested. The near-degeneracy floor loop 6's NOTES identified
  was 85-95k (anti-cascade alternation starting to dominate). 60 s would
  need to compress trade_count by ~10-15 % to hit that floor — a much
  larger move than any 5 s step has produced.
- Why this is the **right final test** for the arm:
    - The arm is hard-capped at 8 loops (this loop). After this, no more
      iterations.
    - A conservative 35 s or 40 s step would, on the per-5s extrapolation,
      almost certainly produce another modest improvement — but would
      leave the actual *boundary* of the window-length lever uncharacterised.
      A doubling step bounds the lever decisively: even if degeneracy onset
      lies somewhere in [30, 60], the result still bounds the lever's
      practical operating range and tells future arms where to start.
    - A doubling step is also the *information-maximising* choice given the
      flat per-5s pace observed: small steps are guaranteed to confirm the
      pace; the large step is the one that genuinely probes the unknown.
- Three mutually-exclusive outcome regimes the loop 8 result will
  disambiguate:

  **(i) Durability continues past 60 s** (pnl > loop 7, trade_count ≥ ~100k):
       Best-in-arm settles at 60 s. The window curve is still rising at
       a full minute of look-back. Arm closes with the strongest possible
       result; future work would explore even longer windows or pivot to
       the hybrid/asymmetric/acceleration levers from the new
       higher-anchor operating point.
  **(ii) Saturation in [30, 60]** (pnl ≈ loop 7 ± a few percent, trade_count
       still ≥ ~95k): the saturation point is somewhere in the [30, 60]
       interval; best-in-arm settles at 30 s (loop 7). The arm closes
       having mapped the lever's productive range to 10-30 s and bounded
       its upper limit at ~60 s.
  **(iii) Degeneracy onset between 30 s and 60 s** (pnl below loop 7,
       trade_count materially below ~95k, e.g., 80-95k): the anti-cascade
       alternating regime starts to dominate; best-in-arm settles at 30 s
       (loop 7). The arm closes having located the degeneracy boundary
       within the [30, 60] interval. The result still bounds the lever
       and informs future arms — a strong negative result is as
       valuable as a strong positive one for the final test.

- Mechanism arguments for *why* each regime is plausible at 60 s:
    - *Continued gain*: a 60 s window typically holds ~300-600 signed prints
      in active MES day-session activity; |net_flow| ≥ 1 is then a
      *meaningful* selectivity filter (the running integer sum is the
      net of hundreds of prints, so distinguishing 0 from ±1 is a
      genuine signal). At 30 s the same argument worked; 60 s extends
      it. The "multi-print sustained pressure" pattern loop 6
      hypothesised becomes even better characterised at 60 s.
    - *Saturation*: the per-skip evidence quality may level off once the
      window is "large enough" — additional samples beyond some point
      add noise (stale flow from earlier in the window) at the same rate
      they add signal. The empirical signal from loops 5-7 mildly
      argued against this prior (the per-5s pace stayed flat or rose),
      but it cannot be ruled out at 60 s.
    - *Degeneracy*: integer running |net_flow| over 60 s of MES activity
      is almost-always non-zero (buyers and sellers rarely cancel
      exactly across hundreds of prints). The gate would then fire on
      most orders, and the anti-cascade `_position_flat` re-entry path
      would force alternating submits. Loop 4 originally flagged "20 s+"
      for this regime; loop 6 disproved it at 20 s, loop 7 disproved
      it at 30 s, but 60 s is genuinely unprobed and a doubling is the
      natural place for the boundary to lie.

**Expected effect (concrete, in vs_base_* terms)**:

- realized_pnl: **+38 % to +44 % vs base** if durability continues at
  the same per-5s pace (linear extrapolation of +1.4-1.6 %/5s ×
  6 additional 5s steps ≈ +9-10 % vs loop 7); **+30 % to +34 % vs base**
  if saturation (P&L roughly equal to loop 7 ± 2 %); **+15 % to +28 %
  vs base** if degeneracy onset between 30 s and 60 s (giving back some
  or most of loop 7's gain). In vs-loop-7 terms: -10 % to +9 %.
- trade_count: **102,000 - 104,000** (97-97 % of base) if still
  selective; **95,000 - 102,000** if mild saturation; **below 95,000**
  if approaching degeneracy. A reading near 85,000 would confirm
  full alternating regime; a reading near 60-70 % of base would
  confirm "every-other-order" anti-cascade dominance.
- sharpe: tracks P&L direction; expect 7.5 - 8.0 range if durability
  continues, 7.0 - 7.5 if saturation, 5.5 - 7.0 if degeneracy.
- max_drawdown_pct: not expected to worsen materially; could improve
  marginally if more adverse skips are caught, or worsen modestly
  (-0.003 pp) if the longer window catches more clustered
  wrong-directional skips.
- mean_slippage: 0.0 vs 0.0 (zero-cost fill model).
- is_weighted_bps: continues loop 7 trajectory — if durability extends,
  IS improves further (per-skip evidence quality keeps rising). If
  degeneracy onsets, IS could regress (more good-fill entries caught
  in the larger skip set).

**Risk**: The principal risk is the degeneracy regime. If it materialises,
P&L falls below loop 7 (likely still above base, but giving back some of
the gain) and trade_count compresses noticeably. **The downside is
bounded**: this is the final loop of the arm; loop 7's window=30 setting
remains the best-in-arm operating point regardless of this loop's outcome.
The upside (further gains) gives a clear narrative for the arm: window
length is the dominant lever and its productive range extends past 30 s.
Either way, the result is information that bounds the lever.

**Why a doubling and not 45 s** (re-emphasised):
  - 45 s is the conservative variant loop 7 enumerated; it gives a
    finer-grained calibration but probes a smaller chunk of the
    parameter space (a +50 % step rather than a +100 % step).
  - The per-5s extrapolation from loops 5-7 predicts essentially the
    same per-5s pace at 45 s as at 30 s. A 45 s result of "another
    +5-7 % vs loop 7" would confirm the extrapolation but tell us
    nothing about the boundary. At 60 s, even a "no further gain"
    result locates the saturation/degeneracy boundary within [30, 60].
  - The downside risk is symmetric in direction but the *information*
    return is much higher at 60 s: a negative result at 45 s leaves
    [45, ?] still unprobed; a negative result at 60 s closes the
    question with a wider bracket.
  - Conclusion: **60 s is the right final test** — it is the one-loop
    move that maximises information for the arm's last available
    iteration.

**Why not pivot to the hybrid floor / asymmetric / flow acceleration
lever now**:
  - Loops 4-7 produced four consecutive wins on the window lever, with
    the marginal gain flat-to-accelerating each step. The lever is
    producing the best information-per-loop in this arm; pivoting on
    the final loop (without first bounding the lever's upper limit)
    would be the wrong methodological choice. The hybrid / asymmetric /
    acceleration levers are documented in loop 7's NOTES as natural
    follow-ups for a *future* arm; this arm's job is to characterise
    the window lever fully.
  - Loop 7's NOTES explicitly framed loop 8 as the "high-information
    final test" on the window lever. We follow that.

**Builds on**: `afg-f-l7` (prior loop). Structurally, the only
behavioural change is `window_seconds`: 30.0 → 60.0. All other
invariants (anti-cascade `_position_flat=True` after any skip,
reduce-only-orders-always-execute, quantity-invariant preserved, O(1)
running sums for both `_net_flow` and `_gross_volume`,
`flow_threshold = 1.0`, `min_gross_volume = 0.0`) are preserved
unchanged.

---

## Implementation Decisions

- **`window_seconds` default = 60.0.** Doubled from afg-f-l7's 30.0.
  This is the priority-1 direction from loop 7's forward-looking note,
  chosen with a deliberate **doubling step** (rather than the
  conservative +50 % step to 45 s) because:
    (a) per-5s marginal P&L gain has been flat-to-rising across loops
        5 → 6 → 7 (+0.51, +1.41, +1.57 %/5s), arguing against any
        diminishing-returns prior;
    (b) trade_count has been essentially flat across the entire 15-30 s
        sweep (-0.7 % total reduction over doubling the window length),
        leaving substantial headroom before anti-cascade alternation
        dominates;
    (c) this is the **final loop** of the arm, so the test must bound
        the lever's productive range — a smaller step would leave the
        upper boundary uncharacterised, defeating the purpose of the
        last available iteration;
    (d) a doubling step probes an entire octave of unknown parameter
        space and mechanistically disambiguates between three distinct
        outcome regimes (continued gain / saturation / degeneracy).
- **`flow_threshold` default = 1.0.** Carried forward from afg-f-l3
  through afg-f-l7. Loop 3 established this as the proven operating
  point; the integer-equivalence rule from loop 2 still applies for
  any window length, since the gate condition is evaluated on
  integer-valued `_net_flow` at a single decision instant.
- **`min_gross_volume` default = 0.0.** Carried forward (loop 1's
  harmful feature remains reverted). The hybrid small-floor variant
  was flagged in loop 7's NOTES as a natural alternative if the window
  lever has saturated; the loop 7 evidence did *not* show saturation,
  so the window lever takes priority on the final loop.
- **No algorithmic structure changes.** Same deque, same O(1) running
  aggregates (`_net_flow`, `_gross_volume`), same prune logic, same
  `_flow_is_adverse` decision, same `on_order` routing, same
  anti-cascade and reduce-only paths. This isolates `window_seconds`
  as the single behavioural variable, consistent with the discipline
  used across loops 3 → 7.
- **The `_gross_volume` tracking code is retained** (no-op at default
  `min_gross_volume = 0.0`) — kept for parity with prior loops and so
  a future arm can re-enable a floor without code churn. Cost is one
  running-sum maintenance, O(1).
- **Quantity invariant preserved**: orders are still only skipped or
  submitted whole; `order.quantity` is never touched.

**Look-ahead check**: identical to all prior loops in the arm.
`on_trade_tick` only appends; only trade ticks with
`ts_event <= order.ts_init` are present at decision time (replay is
strictly chronological; the prune uses `order.ts_init`, never a
future timestamp). Lengthening the window widens the look-*back* —
it does not change look-ahead semantics. The `cutoff_ns = ts_init -
window_ns` arithmetic remains correct for any window size, including
60 s.

---

## Backtest Observations

**Full 12-date train window (2026-03-08 through 2026-03-20):**

| Metric | afg-f-l8 (60s) | afg-f-l7 (30s) | base (aggressor-flow-gate, 10s) |
|---|---|---|---|
| realized_pnl | $1,672.75 | $1,664.75 | $1,255.50 |
| vs_base_pnl_pct | **+33.23%** | +32.59% | — |
| sharpe_ratio | 7.366 | 7.407 | 5.594 |
| trade_count | 103,664 | 104,138 | 107,198 |
| win_rate | 35.73% | 35.69% | 35.27% |
| max_drawdown_pct | -0.03230% | -0.03240% | -0.03888% |
| mean_slippage | 0.0 | 0.0 | 0.0 |

**What drove improvement**: The 60s window captures persistent directional pressure
over a full minute, which continues to filter out adverse entries vs the baseline (10s).
However, essentially all incremental gain over the 30s window has vanished — the P&L
improvement vs loop 7 is +0.48% (1672.75 vs 1664.75), well within noise across 12 dates.

**What underperformed**: The doubling-step expectation of continued per-5s marginal gains
(predicted +9-12% vs l7 in the "durability continues" scenario) was not realized.
Sharpe slightly regressed vs l7 (7.366 vs 7.407), and trade_count declined slightly
(103,664 vs 104,138), both consistent with mild saturation.

**Outcome regime**: This is unambiguously **saturation in [30, 60]**. The window-lever's
productive operating range is [15, 30] seconds; the optimum is at 30s (afg-f-l7).

**Key diagnostic**: trade_count at 60s = 103,664 = 96.7% of base — still firmly in the
selective-gate regime. Degeneracy did NOT onset between 30s and 60s. Future arms using
even longer windows (90s, 120s) are unlikely to recover additional P&L, since the P&L
curve is already flat at 60s with trade_count still well above the anti-cascade degeneracy
floor (~85-90k).

**Hypothesis verdict**: The hypothesis that the window-length lever's productive range
extends past 30s was FALSIFIED by the 60s result. The predicted saturation band (+30% to
+34% vs base) includes the actual result (+33.23%), consistent with the saturation regime.
The window lever is exhausted at 30s (afg-f-l7 is the best-in-arm operating point). The
arm closes with the lever's useful range bounded to [15, 30] seconds and the saturation
boundary located within [30, 60].

**Suggested next attempt**: Future arms on the aggressor-flow-gate base should start from
afg-f-l7's operating point (window=30s, threshold=1.0, floor=0.0) and explore the two
untested structural levers: (1) small gross-volume floor (min_gross_volume=2 or 3
contracts at 30s window) — may filter very-thin one-print windows without loop 1's
aggressive-floor failure mode; (2) asymmetric thresholds (tighter threshold for adverse
side, looser for neutral). The window lever is now fully characterized; further extension
is not expected to yield additional returns.
