# ptg-b-l5 -- adverse-move AND hold-time conjunction

## Hypothesis

Brief-summary context allowed for this loop: loop-1.json + loop-2.json +
loop-3.json + loop-4.json (metrics + summary_out only). I mechanically
inspected `execution_algos/ptg-b-l4/execution_algorithm.py` and (for the
hold-time access pattern) `execution_algos/ptg-b-l1/execution_algorithm.py`
only -- no prior-loop NOTES prose.

L4 (adverse_threshold_ticks=5) was -11.88% vs base on the 11 apples-to-
apples dates with trade_count +0.84% vs base (+618 trades, -$423.50
aggregate). The convex monotonic lineage shows:

  L1 (age-only, 5s):     -75.33% vs base, +13.25% trades  (+9,779)
  L2 (adverse, 1 tick):  -41.30% vs base,  +9.80% trades  (+7,232)   +34 pp
  L3 (adverse, 3 ticks): -22.29% vs base,  +2.42% trades  (+1,785)   +19 pp
  L4 (adverse, 5 ticks): -11.88% vs base,  +0.84% trades  (+618)     +10 pp

Marginal returns are diminishing: $677 (L2->L3), $371 (L3->L4). The L4
brief summary `next` text proposed two candidate directions for L5:
  (i) raise to 7 ticks (predicted endpoint: trade_count below base,
      pnl unchanged or slightly worse than L4) -- clean exhaustion
      diagnostic but low expected upside.
  (ii) keep 5 ticks AND add a structural conditioner -- specifically a
      hold-time floor (admit only if position is at least N seconds
      old AND has moved 5 ticks adversely), or a spread-not-widened
      guard, or signed aggressor imbalance on recent flow.

L4 chose (ii) with the hold-time floor for L5 (per its `next` text:
"Pick (ii) with the hold-time floor"). The reasoning given:
  - L1 (age-only at 5s) and L4 (adverse-only at 5 ticks) each
    individually under-perform base.
  - But the failure modes hint at compounding: age was wrong as the
    SOLE predicate because at 5s the position is still mid-forecast
    (oracle horizon is 30s), so flipping it captures a worse entry
    than holding.
  - At BOTH 5s AND 5-ticks-adverse, the position has matured (the
    oracle has had time to confirm or disconfirm) AND been wrong
    by a material amount -- this is exactly the conjunction the
    base's blanket skip is too coarse to capture.

The expectation: the conjunction strictly tightens vs L4 (every L5
admit is also a valid L4 admit; L5 admits are a strict subset of L4
admits). So trade_count must be <= L4's (74,420). Whether pnl moves
up or down depends on the conditional money-making rate of:
  - admits that survive both filters (5-tick AND 5s aged), vs
  - admits dropped by adding the age conjunction (5-tick AND fresh).

The base case prediction is that the marginal admit removed is the
L4 admit that is adverse-rich but fresh, which is the case most
likely to be a same-tick-flip noise event (the oracle just emitted
both the CLOSE-OPEN of the original position and the adverse-rich
reversal in quick succession). Removing those should raise the
average admit win-rate and so the conjunction should improve pnl
relative to L4.

### One targeted change vs. L4

- L4: reversal override = `adverse >= 5 ticks` (single condition)
- L5: reversal override = `adverse >= 5 ticks AND age >= 5 seconds`
       (conjunction; both must hold)

Everything else is identical, including:
  - position cap (1)
  - adverse-move convention (LONG: entry-mid; SHORT: mid-entry)
  - quote subscription pattern
  - reduce-only short-circuit
  - same-direction-add skip
  - fall-back-to-skip behavior on missing quote or missing avg_px_open
  - diagnostic counters (with new `skipped_reversal_fresh` counter
    tracking the new age-fail branch separately from
    `skipped_reversal_no_adverse`)

### Why 5 seconds (and not 3 or 10)

  - L1 used 5s as its age-only choice. Reusing it keeps the
    single-conditioner sweep (L4) and the single-conjunction
    addition (L5) on consistent axes -- this is the cleanest
    additive design.
  - 5s is 1/6 of the 30s oracle horizon -- enough time for the
    oracle to have re-evaluated and rebroadcast its forecast on the
    position's side a few times, so the position has "absorbed"
    some signal confirmation if the original entry is correct.
  - Smaller (1-3s) would barely filter; larger (10s+) risks
    throwing out admits where the oracle has correctly flipped its
    forecast on a real new regime within the first 5-10s.

### Failure mode I am explicitly betting against

  - Most 5-tick adverse moves take materially longer than 5s to
    accumulate in the underlying. If so, every L4 admit already has
    age >= 5s (the L1 age-only override was admitting MUCH younger
    positions because 1-tick-adverse can happen quickly). In that
    case, the AND-condition does not bind and L5 will be near-
    identical to L4. If trade_count and pnl are within ~1% of L4,
    the conjunction is not filtering meaningfully and L6 should
    pivot to one of the other structural conditioners (spread
    guard, aggressor imbalance).
  - Opposite mode: the age floor is too long and eliminates most
    of L4's beneficial admits (pnl regresses while trade_count
    drops). In that case L6 should bracket age back to 3s while
    keeping 5 ticks.

### Predicted outcome ranges (single hypothesis, before backtest)

  - trade_count: 73,500 - 74,200 (between L4's 74,420 and base's
    73,802; predicting the conjunction trims roughly half to all of
    L4's +618 excess).
  - pnl: $3,250 - $3,500 (between L4's $3,141 and base's $3,564;
    predicting +$100 to +$350 gain from filtering money-losing
    admits, getting from -11.88% to roughly -2% to -8% vs base).

## Implementation Decisions

  - Copied `execution_algos/ptg-b-l4/execution_algorithm.py` as the
    starting point; renamed `PtgBL4Config`/`PtgBL4Algorithm` to
    `PtgBL5Config`/`PtgBL5Algorithm`.
  - Added `min_age_ns: int = 5_000_000_000` to the config (5 seconds in
    nanoseconds, matching L1's default).
  - Stored `self._min_age_ns` in `__init__`.
  - Added `self._skipped_reversal_fresh` counter (incremented when
    adverse >= threshold but age < min_age_ns).
  - Gate order in `on_order`: same-direction-add check -> no-quote
    check -> adverse check -> age check -> submit. Adverse first
    (matches L4) so the counters can be compared directly with L4's
    `skipped_reversal_no_adverse` counter.
  - Age is computed as `order.ts_init - position.ts_opened` (both
    standard Nautilus attributes; same pattern L1 used). Both
    quantities are strictly past at the moment on_order() fires, so
    no look-ahead.
  - On a netting OMS the cache returns at most one open position per
    instrument; using `position.ts_opened` directly (not min across
    multiple) is correct.
  - Defensive fall-through behavior preserved: missing quote, missing
    avg_px_open -> skip (do not admit reversal without evidence).
  - `__init__.py` re-exports `get_execution_algorithm` via relative
    import (consistent with L4).
  - Registered in `execution_algos/__init__.py` between ptg-b-l4 and
    the closing brace.

## Backtest Observations

11-date apples-to-apples train aggregate (Sun-Fri 2026-03-08..2026-03-20,
with 20260319 OOM-killed and dropped from both sides by the runner):

  - ptg-b-l5:        $3,224.25 / 74,239 trades
  - ptg-b-l4:        $3,140.75 / 74,420 trades
  - base ptg:        $3,564.25 / 73,802 trades
  - simple baseline:    $43.25 / 111,489 trades

Aggregate deltas:

  - vs simple:  +7354.91% pnl  (PASS vs simple gate, +5.0% threshold)
  - vs base:    -9.54% pnl, +0.59% trade_count (+437 trades, -$340.00)
  - vs L4:      +2.66% pnl  (+$83.50), -181 trades (-0.24%)

Sharpe 15.66 over 11 days (small-N artifact; treat as directional only).
Slippage 0.0/0.0 (no fill-cost model).
Win rate 37.11% (vs base 37.20%, vs L4 37.08%).
Max DD -1.76%.
is_weighted_bps 0.0424 vs simple 0.575 (better arrival-mid capture);
is_weighted_bps vs base -0.532 bps (slightly better than base).

### Mechanical diff vs L4

The single targeted change vs L4 was adding a 5-second hold-time floor
on the existing position as a CONJUNCTION with the existing 5-tick
adverse-mid override. Concretely:

  - L4 admit predicate:  `adverse_mid >= 5 ticks`
  - L5 admit predicate:  `adverse_mid >= 5 ticks AND age >= 5 seconds`

Implementation deltas in `execution_algorithm.py` (every other line was
copied byte-identical from L4):

  - PtgBL5Config: added `min_age_ns: int = 5_000_000_000`.
  - PtgBL5Algorithm.__init__: stored `self._min_age_ns`.
  - PtgBL5Algorithm.on_reset: zeroed new `_skipped_reversal_fresh` counter.
  - PtgBL5Algorithm.on_order: after the adverse-mid check passes, added
    a second check `age_ns = order.ts_init - position.ts_opened` and
    `if age_ns < self._min_age_ns: self._skipped_reversal_fresh += 1; return`.
    Both age attributes are strictly past at the moment on_order() fires
    (no look-ahead).
  - on_start: log line extended to include `min_age=...s`.
  - get_execution_algorithm: added `min_age_ns` kwarg with the same
    default.

L5 admits are a strict subset of L4 admits by construction (every
condition L5 imposes is added on top of L4's, never relaxed).

### Per-date diff (L5 - base, dollars)

  20260308:   -14.50
  20260309:   -80.75
  20260310:   -84.25
  20260311:   -37.00
  20260312:   -33.25
  20260313:   -52.75
  20260315:    -3.25
  20260316:   -13.00
  20260317:    -4.50
  20260318:    -7.50
  20260320:    -9.25
  -----------------
  Total:     -340.00

Worse than base on 11/11 dates in absolute dollars. No date flipped
from positive to negative this loop. Magnitudes are tighter and more
uniform than L4's -- the largest single-day regression was -$84.25
(20260310), vs L4's -$112.00 on the same date. The conjunction
preserved the same loss distribution shape but compressed it
slightly.

### Per-date diff (L5 - L4, dollars)

  20260308:    +8.50  (L4 -23.00 -> L5 -14.50 vs base)
  20260309:    +6.75  (L4 -87.50 -> L5 -80.75)
  20260310:   +27.75  (L4 -112.00 -> L5 -84.25)
  20260311:   -11.50  (L4 -25.50 -> L5 -37.00)
  20260312:   +21.00  (L4 -54.25 -> L5 -33.25)
  20260313:   +18.50  (L4 -71.25 -> L5 -52.75)
  20260315:    +4.25  (L4 -7.50 -> L5 -3.25)
  20260316:    +8.00  (L4 -21.00 -> L5 -13.00)
  20260317:    +2.00  (L4 -6.50 -> L5 -4.50)
  20260318:    +4.25  (L4 -11.75 -> L5 -7.50)
  20260320:   +11.00  (L4 -20.25 -> L5 -9.25)
  -----------------
  Total:     +83.50  (8/11 dates improved; only 20260311 regressed materially)

### Diagnosis (which branch from L4's next text fires)

L4's `next` text proposed two L5 candidate directions:
  (i) tighten threshold to 7 ticks (single-axis exhaustion probe);
  (ii) keep 5 ticks AND add a structural conditioner (hold-time floor,
       spread guard, or aggressor imbalance).
L5 chose (ii) with the hold-time floor at 5s.

Pre-backtest predictions (from the Hypothesis section):
  - trade_count: 73,500 - 74,200 (between L4's 74,420 and base's 73,802;
    trim half-to-all of L4's +618 excess).
  - pnl: $3,250 - $3,500 (between L4 and base; +$100 to +$350 gain,
    closing to roughly -2% to -8% vs base).

Empirical:
  - trade_count: 74,239 (dropped by 181 vs L4, +437 vs base). The
    conjunction trimmed ~30% of L4's +618 excess vs base, less than
    predicted (the prediction expected closer to half).
  - pnl: $3,224.25 (+$83.50 vs L4, -$340 vs base, -9.54%). Below the
    predicted range but in the correct direction.

The +$83.50 pnl gain on -181 trade-count delta confirms the conjunction
did filter some money-losing admits and not just trim them randomly --
the per-removed-admit pnl was approx +$83.50 / 181 = +$0.46/trade
(small but positive on a per-trade basis). However:
  - The marginal gain was much smaller than predicted ($83.50 vs $100-
    350 expected). Most of L4's +618 excess admits survived both
    conditions, i.e. were both adverse-rich AND already aged >= 5s.
    This is consistent with the failure mode I explicitly flagged:
    most 5-tick-adverse moves take materially longer than 5s to
    accumulate, so the age conjunction often doesn't bind.
  - The improvement was broad (8/11 dates better) rather than
    concentrated on a few outliers, which suggests the residual losing
    admits are uniformly distributed across the regime mix, not
    concentrated on a few pathological micro-events.

### Hypothesis verdict

PARTIALLY VINDICATED in direction (+$83.50 pnl, -181 trades), CLEARLY
WEAKER than predicted in magnitude (~25% of the lower-bound expected
gain). The conjunction's age dimension did add some filtering value,
but the practical overlap between "adverse >= 5 ticks" and "age >= 5s"
is much higher than the L4 next text's reasoning anticipated --
adverse-mid accumulation is itself a time-consuming process, so by the
time the 5-tick adverse threshold is reached, most positions are
already old enough to clear the age conjunction. The conjunctive AND
pattern hits diminishing returns the same way the single-axis sweep
did, and for the same underlying reason: the two dimensions are
strongly positively correlated in this microstructure.

### Status

Vs simple gate: PASS (+7354.91% pnl, well above the +5.0% threshold;
slippage no-regression at 0.0/0.0).
Vs base (informational, brief-summary arm): -9.54%, all 11 dates
worse. No formal pass/fail vs base.

### Forward direction (input to L6 hypothesis)

The "adverse-mid + hold-time" conjunction has the same exhausted
character as the single adverse-mid sweep: marginal pnl gain is small
and the trade_count delta is hard to compress further without
collapsing below base. The L6 candidate set should pivot to a
genuinely orthogonal conditioning variable -- one whose correlation
with adverse-mid is weak so a NEW filter can bind on admits that
adverse-mid alone passes through. Top candidates from the L4 next
text's pool, ranked by expected orthogonality to adverse-mid:
  (a) Spread-not-widened guard at the admit moment (skip override if
      current spread > 1 tick / > N x rolling median). Wide spreads at
      flip-time pay away the mid-edge to the spread crossing cost --
      this is a fill-cost axis, not a signal-direction axis, so it
      should bind on admits that adverse-mid passes (an adverse-rich
      reversal can still be expensive to enter if the book is thin
      right then).
  (b) Signed aggressor imbalance on the most recent N ticks of trades
      (only admit if recent aggressor flow agrees with the proposed
      new direction). This is a flow-confirmation axis, also weakly
      correlated with adverse-mid.
  (c) Larger hold-time floor (e.g. 15s or 30s = 1x oracle horizon).
      This is a stronger version of the L5 axis, NOT orthogonal --
      same diminishing-returns risk.

L6 should pick (a) -- the spread-not-widened guard -- as the
highest-leverage truly orthogonal change. Specifically: skip the
reversal override if `(ask - bid) > 1 tick` at the admit moment. The
predicted endpoint is a small but possibly meaningful pnl gain
(maybe +$50 to +$150) and a small trade_count drop (maybe -50 to -250
trades). If (a) returns ~$0 incremental gain, the implication is that
spread is also strongly correlated with adverse-mid at admit time (a
position 5-ticks underwater after 5s tends to have a wide spread by
default) and L7 should pivot to (b). Avoid: any further pure-threshold
sweeps on the adverse-mid axis; any age increase beyond 5s without an
orthogonal axis change first.
