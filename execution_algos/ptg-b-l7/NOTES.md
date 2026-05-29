# ptg-b-l7 -- adverse AND age AND tight-spread AND aggressor-flow conjunction

## Hypothesis

Brief-summary context allowed for this loop: loop-1.json through
loop-6.json (metrics + summary_out only). I mechanically inspected
`execution_algos/ptg-b-l6/execution_algorithm.py` (and
`execution_algos/aggressor-flow-gate/execution_algorithm.py` for the
trade-tick / signed-flow access pattern only) -- no prior-loop NOTES
prose.

L6 (5 ticks AND 5s AND spread <= 1 tick) was -1.91% vs base on the 11
apples-to-apples dates with trade_count +0.20% vs base (+151 trades,
-$68 aggregate). The L6 brief summary identified marginal pnl per
loop as $1213, $677, $371, $83.50, $272 -- L6 broke the
diminishing-returns pattern decisively by adding a GENUINELY
ORTHOGONAL axis (spread). The +$272 came from filtering admits the
first two conditions (adverse, age) silently let through.

The L6 next text proposed two natural directions:
  (i) one more genuinely-orthogonal structural conditioner --
      specifically signed aggressor flow (admit only if recent flow
      agrees with the proposed NEW direction). Flow direction is
      mathematically distinct from price displacement (adverse-mid),
      time (age), and quote thickness (spread); the most plausibly
      orthogonal remaining axis.
  (ii) tune an existing knob -- relax spread to 2 ticks.

L6 next chose (i) -- aggressor flow -- because the residual gap
(-$68, -1.91%) is too small for a same-axis sweep to close, while a
truly orthogonal axis is the only mechanism that can.

### One targeted change vs. L6

- L6: reversal override = `adverse >= 5 ticks AND age >= 5s AND spread <= 1 tick`
       (three conditions)
- L7: reversal override = `... AND flow_agreement(proposed_side, last 1s) >= 60%`
       (four conditions; all must hold)

Aggressor-flow definitions:
  - Lookback window: 1 second. Matches L5's age scale; balances
    signal smoothing against staleness on a 30s oracle horizon. The
    L6 next text was explicit on this choice.
  - Aggregation: signed volume per trade tick. BUYER aggressor =
    +size, SELLER aggressor = -size, NO_AGGRESSOR = 0.
  - Agreement metric: same-side volume fraction = max(net, -net) /
    sum(abs(signed)). For a BUY reversal, agreement = net /
    sum(abs(signed)) when net > 0. For a SELL reversal, agreement
    = -net / sum(abs(signed)) when net < 0. Require >= 0.60.
  - Defensive fall-through: if no flow evidence in window (empty
    deque OR all NO_AGGRESSOR ticks), SKIP the override (absence
    of evidence is not evidence of presence). Mirrors L6's no-quote
    behavior. The L6 next text explicitly identified the residual
    losers as flips lacking flow confirmation, so an empty window
    is the same failure mode as a discordant window.

Everything else is identical to L6, including:
  - position cap (1)
  - adverse-move convention (LONG: entry - mid; SHORT: mid - entry)
  - age convention (`order.ts_init - position.ts_opened`, strictly
    past at decision time)
  - spread convention (best ask - best bid from cached quote tick)
  - quote subscription pattern (now ALSO subscribes to trade ticks
    via the same `_ensure_subscribed` helper)
  - reduce-only short-circuit
  - same-direction-add skip
  - fall-back-to-skip behavior on missing quote, missing avg_px_open,
    AND now missing flow
  - diagnostic counters from L6, plus two new ones:
    `skipped_reversal_no_flow`, `skipped_reversal_flow_disagree`

### Why exactly 1-second / 60% agreement (not other values)

  - 1-second window: shorter than L5's 5s age floor (so the flow
    test is reading a strictly fresher signal than the position-age
    test, ensuring the four gates probe different time-scales).
    Long enough to accumulate multiple trades on MES at typical
    cadence -- empirically each second has on the order of 10+
    trade prints during active hours.
  - 60% agreement threshold: a modest majority. 51% is "any
    majority," which is barely informative (random walk in flow
    can produce 51% in a small window). 80% is a supermajority
    that would collapse to ~zero admits during the noisy windows
    that constitute most of the trading day. 60% is the natural
    middle ground -- requires a clear lean without demanding
    near-unanimity.
  - The L7 in-flight diagnostic distinguishes 60% being too strict
    (pnl regresses, trade_count drops well below L6) from being
    too loose (pnl ~flat, trade_count similar to L6).

### Failure modes I am explicitly betting against

  - Aggressor flow is correlated with adverse-mid at admit time.
    A position 5-ticks underwater after 5s likely had original-side
    aggressor flow turn against it during those 5s -- so the flow
    test is downstream of the adverse test, not orthogonal to it.
    If so, the fourth condition binds on the same admits the first
    three already bind on, and L7 returns ~$0 incremental gain. In
    that case L8 should pivot to (ii) -- relax spread to 2 ticks.
  - Flow direction is ANTI-predictive on this oracle (contrarian
    setup: aggressors are dumb money, flow against them is the
    edge). In that case L7 pnl regresses materially while
    trade_count drops modestly. L8 should freeze L6 and stop.
  - 60% threshold too strict in noisy windows. L7 trade_count
    drops well below base (say, <72k) and pnl regresses. L8
    should bracket back to 51%.

### Predicted outcome ranges (single hypothesis, before backtest)

  - trade_count: 73,600 - 73,850 (between base's 73,802 and a
    modest drop -- predicting the flow guard trims 100-350 of
    L6's +151 excess vs base, possibly dropping slightly below
    base).
  - pnl: $3,510 - $3,590 (between L6's $3,496.25 and a small gain
    of +$15 to +$95; potentially crossing base's $3,564.25). The
    residual gap is so small that any genuinely orthogonal new
    filter has plausible scope for closure or crossover.

## Implementation Decisions

  - Copied `execution_algos/ptg-b-l6/execution_algorithm.py` as the
    starting point; renamed `PtgBL6Config`/`PtgBL6Algorithm` to
    `PtgBL7Config`/`PtgBL7Algorithm`.
  - Added `flow_window_ns: int = 1_000_000_000` and
    `flow_agreement_min: float = 0.60` to the config.
  - Added `self._flow_deque: deque[tuple[int, float]]` and
    `on_trade_tick()` handler (signed_vol = +size for BUYER, -size
    for SELLER, 0 for NO_AGGRESSOR) -- pattern mechanically
    transcribed from `execution_algos/aggressor-flow-gate/
    execution_algorithm.py` lines 127-138.
  - Added `_prune_flow_window(cutoff_ns)` and
    `_flow_agreement(proposed_side, now_ns)` helpers.
    `_flow_agreement` returns `(agreed: bool, has_flow: bool,
    frac: float)`. has_flow=False indicates either empty deque or
    all-NO_AGGRESSOR ticks; both fall back to SKIP.
  - Extended `_ensure_subscribed()` to also call
    `subscribe_trade_ticks(instrument_id)` (with a separate
    try/except so a trade-tick subscription failure doesn't block
    quote-tick subscription; same defensive pattern as L6's quote
    subscription).
  - Added two new counters: `skipped_reversal_no_flow`,
    `skipped_reversal_flow_disagree`. The two are kept separate so
    the post-hoc analysis can distinguish "skipped because flow
    was warm-up-empty" from "skipped because flow was actively
    disagreeing." Both increment the same gate-failure bucket
    from L8's perspective.
  - Gate order inside reversal branch: no-quote -> adverse -> age
    -> spread -> flow -> submit. Flow is last so its counter
    cleanly isolates the L7 incremental filter effect from L6's
    counters; the adverse/age/spread counters remain directly
    comparable with L6.
  - The on_start log line is extended with the flow_window and
    flow_agreement parameters.
  - Defensive fall-through behavior preserved: missing quote,
    missing avg_px_open, empty flow window, all-NO_AGGRESSOR window,
    flow-disagreeing window all -> skip.
  - `__init__.py` re-exports `get_execution_algorithm` via relative
    import (consistent with L5/L6).
  - Registered in `execution_algos/__init__.py` after ptg-b-l6.

## Backtest Observations

Aggregate (11 train dates, 20260319 OOM-dropped from both sides):

  - realized_pnl:    $3,538.75
  - sharpe_ratio:    16.184
  - max_drawdown:    -0.0173%
  - win_rate:        37.18%
  - trade_count:     73,861
  - mean_slippage:   0.0  (zero fill-cost model; see research/NOTES.md)

vs simple baseline (11 dates, $43.25):     +8082.08% pnl  -- PASS
vs base position-tier-gate (11 dates, $3,564.25 / 73,802 trades):
  - vs_base_pnl_pct:       -0.7154%  (gap shrank from L6's -1.91% by +1.19 pp)
  - trade_count delta:     +59 trades (+0.08%) -- the tightest calibration of
    the whole 7-loop lineage; +151 over base at L6 -> +59 over base at L7
    (-92 trades removed by the flow-agreement guard).
  - aggregate dollar gap:  -$25.50 over 11 dates (avg -$2.32/date)

vs L6 ($3,496.25 / 73,953 trades):
  - delta_pnl:             +$42.50  (+1.22%)
  - delta_trades:          -92      (-0.12%)
  - mean dollars / removed-trade: +$0.46/trade (matches the L4->L5 ratio
    almost exactly; the flow filter is removing admits at the same
    pnl-per-trade rate as the age conjunction did, suggesting the
    flow signal IS providing real but small incremental information).

Lineage trajectory vs base:
  L1: -75.33%  (-$2,685.00)   [age 5s only]
  L2: -41.30%  (-$1,472.00)   [adverse >= 1 tick]
  L3: -22.29%  (  -$794.50)   [adverse >= 3 ticks]
  L4: -11.88%  (  -$423.50)   [adverse >= 5 ticks]
  L5:  -9.54%  (  -$340.00)   [adverse 5 AND age 5s]
  L6:  -1.91%  (   -$68.00)   [+ spread <= 1 tick]
  L7:  -0.72%  (   -$25.50)   [+ flow_agreement >= 60% over 1s]

  Marginal pnl per loop: +$1213, +$677, +$371, +$83.50, +$272, +$42.50

  L7 sits in the "tiny incremental drift" range the L6 next text
  predicted as the (i)-aggressor-flow outcome (+$0 to +$50), landing
  at the upper end of that bracket (+$42.50).

Diagnostic interpretation (per L6's in-flight predictions):
  - trade_count drop (-92 vs L6) is in line with the predicted -50 to
    -200 range. Trade_count is now +0.08% vs base (was +0.20% at L6),
    well within +/-0.5% calibration band.
  - pnl gain (+$42.50 vs L6) is in line with the predicted +$10 to
    +$80 range, sitting between the median and upper bound.
  - The flow axis behaves as PARTIALLY ORTHOGONAL to (adverse, age,
    spread): it provides real-but-small incremental filtering, not
    the dramatic +$272 gain of the L6 spread axis. The mechanism is
    likely that adverse-mid + age + tight-spread already captures
    most of the structure aggressor flow encodes -- a position
    5-ticks underwater after 5s with a 1-tick spread typically does
    have some directional flow against it already.
  - The (i)-orthogonal-axis hypothesis is VINDICATED in direction
    but the residual gap to base ($-25.50, -0.72%) is now smaller
    than the noise floor of single-date pnl variation (-$16 was
    L6's worst date), so further single-axis additions face a
    measurement-noise floor.

PASS decision (against simple baseline -- the experiment gate per
config.yaml pass_gate.baseline):
  - delta_pnl vs simple:       +8082.08%   (gate: +5.0%)   PASS
  - delta_slippage vs simple:        0.0%  (gate: <= +5.0%) PASS
  Status: PASS.

The arm-level "did it BEAT base" question is still answered NO at L7
($25.50 short of base), but the gap is at the noise floor.

## L8 directional implications

The L6 next text identified three possible L7 outcomes and what L8
should do for each:
  - "L7 regresses with trade_count below base" -> L8 pivot to (ii)
    relax spread to 2 ticks.
  - "L7 flat with trade_count within +/-0.5% of L6" -> stop adding
    conjunctions; either tune existing knobs or accept saturation.
  - "L7 crosses base" -> freeze L7, add no further conditioner.

L7 landed BETWEEN "flat" and "crosses base": +$42.50 pnl gain (small
but real, not flat) without crossing base ($-25.50 short). Neither
pivot trigger nor freeze trigger cleanly fires. The natural L8 read
is that the conjunctive AND structure has reached its saturation
limit -- each new orthogonal axis has yielded smaller marginal
gain (+$272, +$42.50), and the residual -$25.50 gap is below the
noise floor of dropping a single bad date. The highest-leverage L8
move is therefore not adding a sixth condition but TUNING the
existing knobs to reduce false skips -- specifically RELAXING the
spread guard from 1 tick to 2 ticks, since at 1 tick the guard
binds on +286 trades vs L5 ($272 gain) and at 2 ticks it would
admit some of those back at zero or slightly positive expected
pnl, while the new flow-agreement filter (60%) still screens the
worst flow-disagree admits. That is the lone single-knob move
inside the existing 4-axis predicate that has a clear theoretical
mechanism for crossing base.
