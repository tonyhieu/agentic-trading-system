# Loop 4 Reasoning Trace

**Note on provenance**: this loop's research phase was interrupted after
the algorithm was implemented and 11 of 12 train-window dates had been
backtested. A subsequent invocation finished the 20260320 backtest,
re-aggregated all 12 dates, and wrote this trace. The trace is therefore
reconstructed from `execution_algos/sip-vrs-l4/NOTES.md` (the surviving
hypothesis document) and the per-date metrics on disk. Sections that
require recall of the original researcher's in-loop reasoning are flagged
as "(reconstructed)". The critic should treat this trace as a partial
record of method execution and weight the methodological-failure-mode
question accordingly.

## Hypothesis generation method used
Propose-falsify-commit (`prompts/prompt-l1.md`, the kept loop-1 prompt;
loop-2 and loop-3 proposals were both reverted, so the active method is
still loop-1's). The method requires: read the parent (vol-regime-sizer)
→ enumerate three substantively different candidate weaknesses → state
falsification decision rules upfront → run cheap tests against parent
on-disk artifacts → commit to the surviving candidate → justify every
parameter via inheritance, derivation from a step-4 statistic, or a
principled rule.

## How the hypothesis emerged from the method
(Reconstructed.) The surviving NOTES.md commits to a single mechanism:
add a **trendiness multiplier** to the parent's submission-probability
gate. Trendiness `T = |Σ Δmid| / (Σ|Δmid| + ε)` over a fixed window of 40
ticks (≈ two parent fast-EWM half-lives). The new submission probability
is `p = max(min_prob, T + (1 - T) · p_vol)`, where `p_vol` is the
parent's unchanged vol-regime probability. At `T = 0` (pure chop) the
gate reproduces the parent; at `T = 1` (one-signed window) the order is
re-admitted at full probability.

The motivating weakness named in NOTES.md is that the parent's vol gate
uses *unsigned* `|delta_mid|`, so it cannot separate *trending* high-vol
regimes (where the oracle's 30s signal is more reliable) from *choppy*
high-vol regimes (where the parent's skip is correct). The proposal is
therefore a layered re-admit on top of the parent's existing skip path,
adding a single new knob (`trend_window=40`), inheriting all other
parameters verbatim.

The trace cannot reconstruct the *three* candidate weaknesses or the
explicit falsification decision rules the propose-falsify-commit method
requires — only the surviving candidate is documented. Loops 2 and 3
both observed that the method tends to produce parent-centric
modifications that compete with rather than compose on top of the
running best; this loop appears to have produced another such
modification (a new submission-time gate competing with the parent's
vol gate for the same submit/skip decision space).

## Where the method helped
(Reconstructed from NOTES.md.) The method's "inherit verbatim plus one
new knob" discipline kept the proposal narrow:
- `trend_window=40` is anchored to the parent's fast-EWM half-life (two
  half-lives) — a principled rule rather than an unconstrained sweep.
- The multiplicative blend `T + (1-T)·p_vol` was constructed so that
  `T=0` reproduces the parent exactly. The method's emphasis on
  parent-inheritance produced an algorithm that degrades gracefully to
  the baseline when its signal is uninformative — a property the
  per-date results bear out (no single-date catastrophe).
- The single-knob constraint prevented a parameter-explosion failure
  similar to loop-2.

## Where the method felt limiting or unnecessary
- **Three-candidate enumeration is missing from the trace artifact.**
  Whether the original researcher enumerated three candidates and
  falsified two, or jumped to the trendiness mechanism after reading
  the parent, cannot be recovered. The prompt requires three candidates
  + decision rules upfront, but only the survivor is documented in
  NOTES.md. This is a real failure mode of the method as practiced:
  intermediate falsification artifacts are written ad hoc and lost on
  interruption.
- **Parent-anchoring instead of champion-anchoring.** The chosen
  mechanism — re-admitting orders that the parent's gate skipped — is
  a modification of the *parent*'s submission gate, not of the running
  best (loop 1, signed-headwind sizer). Loop 1 already re-shaped which
  trades the engine submits; a new gate that re-admits parent-skipped
  orders does not naturally compose with loop 1's mechanism. Loop 3's
  critique already flagged the same structural issue ("a fourth gate
  competing for the same submit/skip decision space the champion
  already occupies"). The fact that loop 4 repeated the pattern
  suggests the prompt does not anchor the researcher to the champion
  strongly enough.

## What a different method might have produced
A champion-anchored method (the kind loop 3's critique proposed before
being reverted) would have required the researcher to start from
`execution_algos/sip-vrs-l1/` (the running best), enumerate its
*residual-failure dates* (dates where l1's pnl is negative or worse
than parent's), and propose mechanisms that target those specific
failure modes. Trendiness as a *composable* layer on top of l1's
signed-headwind sizer — applied only on dates where l1 lost — might
have produced a different algorithm: l1's signed-headwind sizing in
place, with the trendiness multiplier acting as a final-stage filter
on the orders l1 would have submitted. Whether such a hybrid would
have beaten l1 in the train window is unknown, but it would not have
introduced a new gate in competition with l1's.

## What the backtest showed
Train-window aggregate, 12 dates, sip-vrs-l4 vs parent (vol-regime-sizer)
and vs the running best (loop 1):

| Metric | sip-vrs-l4 | vol-regime-sizer | Δ vs parent | sip-vrs-l1 | Δ vs champion |
|---|---|---|---|---|---|
| realized_pnl | 439.00 | 753.75 | **-41.76%** | 1062.25 | **-58.67%** |
| sharpe_ratio (cross-day) | 1.772 | 3.065 | -1.293 | 4.185 | -2.414 |
| max_drawdown_pct | -0.0485 | -0.0460 | -0.003 (worse) | -0.0427 | -0.006 (worse) |
| win_rate | 0.3515 | 0.3529 | -0.001 | 0.3539 | -0.002 |
| trade_count | 130,227 | 127,991 | +2,236 | 127,923 | +2,304 |
| mean_slippage | 0.0 | 0.0 | 0 | 0.0 | 0 |

Per-date pnl (l4 vs parent vs champion l1):

| date | parent | l4 | diff vs parent | l1 (champ) | diff vs l1 |
|---|---|---|---|---|---|
| 20260308 | 108.50 | 108.00 | -0.50 | 112.00 | -4.00 |
| 20260309 | 653.00 | 636.75 | -16.25 | 707.25 | -70.50 |
| 20260310 | 413.25 | 383.50 | -29.75 | 477.75 | -94.25 |
| 20260311 | 217.50 | 196.50 | -21.00 | 266.00 | -69.50 |
| 20260312 | -198.25 | -210.50 | -12.25 | -158.25 | -52.25 |
| 20260313 | -455.00 | -480.25 | -25.25 | -421.50 | -58.75 |
| 20260315 |  -34.25 |  -42.75 | -8.50  | -18.25 | -24.50 |
| 20260316 | -392.75 | -439.75 | -47.00 | -376.75 | -63.00 |
| 20260317 | -167.25 | -207.75 | -40.50 | -180.50 | -27.25 |
| 20260318 | 196.25 | 168.75 | -27.50 | 185.25 | -16.50 |
| 20260319 | 174.25 | 153.25 | -21.00 | 220.50 | -67.25 |
| 20260320 | 238.50 | 173.25 | -65.25 | 248.75 | -75.50 |

What surprised me: the trendiness multiplier *loses* to the parent on
**12 of 12 dates**, including dates the NOTES.md predicted it should
help most (trending high-vol regimes where the oracle should be more
reliable). The hypothesized re-admit alpha is consistently negative.
Trade count is up (+2,236 vs parent), so the multiplier *is* re-admitting
orders the parent skipped — those re-admitted orders are net losers in
aggregate.

What confirmed expectations: trade_count direction (↑) and mean_slippage
direction (unchanged) matched the NOTES.md predictions verbatim. Three
of the five other directional predictions (realized_pnl ↑, sharpe ↑/flat,
win_rate ↑/flat) were wrong-direction.

This is the worst-performing loop so far on the gate metrics: 0/5
metrics improve vs the running best loop-1. Even vs the parent the
proposal regresses on pnl, sharpe, drawdown, and win_rate; the only
"improvement" is trade_count direction, which is not on the gate.

## Where I felt uncertain
- **Whether `T` actually measures "trendiness" the way the mechanism
  story claims.** `T = |Σ Δmid| / Σ|Δmid|` is a signed-vs-unsigned ratio
  on a 40-tick window. On MES at 30s horizon, 40 ticks is ≈ 2-5 seconds
  of activity; the window may be too short to identify a "trend" in any
  meaningful 30s-horizon sense. NOTES.md anchors the window to the
  parent's fast-EWM half-life on principled grounds, but the half-life
  governs *gate responsiveness*, not the timescale at which the oracle's
  30s signal is well-aligned with mid-drift. A longer window (matched
  to the oracle horizon instead of to the gate's half-life) might
  measure the right thing — the present choice was structural, not
  empirical.
- **No falsification test was performed (or, if performed, was not
  recorded) for the trendiness mechanism on parent on-disk artifacts.**
  The propose-falsify-commit method requires a cheap test against
  parent CSVs (e.g., bucket parent's submitted orders by trendiness
  computed retroactively and compare pnl). No such test appears in
  NOTES.md. The hypothesis went straight from "plausible mechanism" to
  "implemented algorithm", which is exactly the method's principal
  failure mode that loop 1's critic introduced the propose-falsify-commit
  prompt to fix.
- **The interruption-and-resume process itself.** The original
  researcher's intermediate reasoning is lost; the trace cannot
  accurately reconstruct which alternatives were considered, what
  falsification logic was contemplated, or whether the researcher hit
  a constraint that pushed them to the trendiness candidate
  specifically. The critic should treat the methodology critique as
  partial.
- **`trend_window=40` is the only new knob, but is anchored to a
  parameter (parent fast-EWM half-life) whose own value was not
  derived for the oracle horizon. If both knobs are mis-anchored
  to the 30s horizon, the chain of justification reduces to "two
  parameters chosen for internal consistency, neither calibrated to
  the prediction-horizon timescale."
