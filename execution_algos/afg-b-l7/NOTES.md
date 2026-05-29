# afg-b-l7 — aggressor-flow-gate with SHORTENED window (window=5s, flow_threshold=1.0)

Brief-summary arm, loop 7. Prior context = ONLY the `summary_out` (changed /
outcome / hypothesis / brief_summary / next) blocks plus the headline metrics
from loop-1.json (afg-b-l1), loop-2.json (afg-b-l2), loop-3.json (afg-b-l3),
loop-4.json (afg-b-l4), loop-5.json (afg-b-l5), and loop-6.json (afg-b-l6).
Per the brief-summary mode boundary I did NOT read any prior NOTES.md prose
nor any `full_reasoning` text -- only the brief summaries plus mechanical
inspection of L4's source for class / parameter shape (L4 is the leader to
copy from and the algo holding the leader parameters).

## Hypothesis

The L1+L2+L3+L4+L5+L6 brief_summary trajectory collectively establishes:

  1. L1 (pure-ratio gate, |r|>=0.35): WORSE than base (-53.25% pnl,
     +13,481 extra admits). Ratio-only reformulation cannot work; also
     established the L1 monotone-yield rule: ~$47-$98/1k near-margin
     orders are weakly anti-informative.
  2. L2 (CONJUNCTION base AND ratio): WORSE than base (-52.14% pnl,
     +14,245 extra admits). ANDing admitted the UNION.
  3. L3 (DISJUNCTION base OR ratio-with-floor): EXACTLY equal to base.
     Ratio leg structurally dominated by absolute leg.
  4. L4 (ratio leg REMOVED + abs threshold 2.0 -> 1.0): GENUINELY beats
     base (+12.16% pnl: $1088 vs $970, -1,671 trades, sharpe 5.36 vs
     4.58). Validates L1 monotone rule in the tight direction:
     ~$70.6 per 1k extra skips of |net|=1 orders.
  5. L5 (further tighten 1.0 -> 0.5): BIT-FOR-BIT IDENTICAL to L4.
     Integer-resolution lesson: flow_threshold has integer resolution
     on this oracle (net_flow = sum of integer trade sizes); decimal-
     fraction tweaks below 1.0 are mechanically inert.
  6. L6 (LOOSEN 1.0 -> 3.0): REGRESSED vs base AND vs L4 (pnl=$832,
     -14.23% vs base, -23.5% vs L4; trades 89,157, +1,397 vs base;
     sharpe 3.83). Validates L1 monotone rule on the LOOSE side too:
     ~$98.8 per 1k newly admitted near-margin orders. The absolute-
     threshold axis is now fully bracketed and confirmed monotone:

       threshold = 1 (L4):   pnl $1088, trades 86,089, sharpe 5.36
       threshold = 2 (base): pnl $970,  trades 87,760, sharpe 4.58
       threshold = 3 (L6):   pnl $832,  trades 89,157, sharpe 3.83

     Integer optimum on this axis = L4 = 1.0. Further integer steps
     in either direction (0 = degenerate; 2 = base; 3 = L6 worse; 4+ =
     monotonic worse by extrapolation) are NOT informative.

L6's "next" text explicitly prescribes the path forward: pivot to the
ORTHOGONAL `window_seconds` axis at fixed `flow_threshold=1.0` (L4's
optimum). All of base + L1..L6 use `window_seconds=10.0`. The window
axis is the obvious untouched lever. L7 single-parameter change:

    window_seconds: 10.0 -> 5.0    (flow_threshold pinned at 1.0)

### Why this direction (10s -> 5s, not 10s -> 20s)

  * `config.yaml` strategy kwargs (visible to me as part of the
    standing environment, not as prior-loop context) sets the oracle
    `horizon_seconds=30.0` and `signal_interval_seconds=1.0`. The
    forecast window is 30s; signals arrive at 1s cadence. A 5s flow
    window is roughly the signal half-life / 6 (i.e. captures recent
    flow on a timescale comparable to the inter-signal interval) --
    plausibly more responsive than 10s. A 20s window approaches the
    oracle's full forecast horizon, where stale flow is more likely
    to mis-classify the regime.
  * Shorter window = LESS stale flow = potentially MORE SELECTIVE
    skips. Fewer false positives from old imbalance that has already
    resolved.
  * Counter-direction (20s) is a plausible L8 if L7 underperforms L4
    -- save it to bracket the window-length optimum after L7's data.

### Quantitative expectations (subjective, by the L1 yield rule)

  * trade_count: roughly comparable to L4's 86,089 (give or take a
    few hundred). The threshold is unchanged; the window change shifts
    WHICH orders get skipped, not the threshold predicate's
    selectivity per-tick. Net direction unclear -- shorter window has
    less flow accumulated, so |net_flow|>=1 fires LESS often (FEWER
    skips, MORE admits); but the same orders that are no longer
    skipped under 5s might or might not be the anti-informative ones.
  * pnl: bracketing scenarios:
       - 5s captures real near-term toxicity better -> skip more
         informative orders -> pnl > L4's $1088.
       - 5s misses slow-developing flow imbalance -> skip fewer
         truly-anti-informative orders -> pnl < L4's $1088. Could
         drop toward base ($970) or worse.
       - 5s and 10s skip materially overlapping order sets -> pnl
         approximately matches L4.
  * sharpe: roughly tracks pnl direction (variance-per-trade likely
    similar since threshold predicate is unchanged).
  * Refinement targets vs L4 (informational; L7 is per_iteration_
    experiment loop, not snapshotted): unlikely to clear the +0.5
    sharpe / +2.0% pnl bars unless the window change is materially
    informative. A tied or slightly-better result is the most likely
    outcome.

### Anti-rationale: alternatives I considered and rejected

  * Continue sweeping `flow_threshold` (e.g., to 4.0, 5.0): the axis
    is fully bracketed and monotone; further integer steps extrapolate
    the monotone decline -- no new information.
  * Reintroduce ratio leg with different parameters: L1+L2+L3
    exhaustively triangulated that the ratio leg cannot help on this
    oracle.
  * Per-side asymmetric thresholds (BUY vs SELL): no brief-summary
    motivation. Would be a leap into a new axis without bracketing
    the window axis first.
  * Change anti-cascade flat-flag semantics: orthogonal but high-risk
    -- could destabilize the gate. Save for after the window sweep
    bracketing is complete.
  * Window 10s -> 20s instead of 10s -> 5s: also untouched, but the
    oracle's 30s forecast horizon suggests longer windows risk stale
    flow info. 5s is the cheaper / lower-risk first probe; 20s is
    the L8 backup if L7 underperforms.

## Implementation Decisions

  * Single structural change vs L4: NONE -- algorithm shape preserved
    exactly (ratio leg absent, absolute-only gate, anti-cascade
    flat-flag, reduce-only-always-submit, side-signed predicate with
    BUY adverse <= -threshold and SELL adverse >= threshold).
  * Single parameter change vs L4: `window_seconds` 10.0 -> 5.0.
    `flow_threshold` PINNED at 1.0 (L4's integer optimum).
  * The 5s window in nanoseconds: 5_000_000_000. The deque pruning
    logic (`_prune_window`) is unchanged -- it pops entries with
    `ts_event < ts_init - window_ns` so a smaller window simply
    keeps fewer entries.
  * Direction-side logic: BUY adverse when net <= -1.0; SELL adverse
    when net >= 1.0. Identical to L4.
  * Anti-cascade semantics (`_position_flat = True` after any skip,
    forcing the next OPEN through unconditionally) preserved exactly.
    Reduce-only orders always submit (intraday_flat).
  * Quantity invariant strictly preserved -- orders are skipped or
    submitted unmodified.
  * No look-ahead bias: window prune uses `order.ts_init - window_ns`
    as cutoff, so the deque at decision time only contains ticks with
    `ts_event >= cutoff` AND `ts_event <= order.ts_init` (because
    replay is strictly chronological). Identical guarantee to L4.
  * Class names: `AfgBL7Config` / `AfgBL7Algorithm`; factory
    `get_execution_algorithm` with `window_seconds=5.0` default and
    `flow_threshold=1.0` default.

  Boundary check: with a 5s window, every adjusted order's flow
  decision is based on the last 5 seconds of trades only. Where L4's
  10s window might see a 3-second-old |net|=2 imbalance and skip
  accordingly, L7's 5s window also sees that imbalance (still within
  5s); but where L4 sees a 7-second-old imbalance and skips, L7 sees
  no such imbalance (the trade is older than 5s, pruned). So the 5s
  window is a STRICT SUBSET of the 10s view at every decision time --
  L7 should skip <= as many orders as L4 (admit >= as many).

## Backtest Observations

Aggregated over the same 11-date apples-to-apples train window all afg-b-*
loops use (2026-03-08..2026-03-20 ex 20260319, dropped for OOM on both
sides):

  L7  (window=5s,  flow=1.0):   pnl=$ 950.50, sharpe=4.530, trades=86,973
  L4 (window=10s, flow=1.0):    pnl=$1088.00, sharpe=5.360, trades=86,089  (in-arm leader)
  L5 (window=10s, flow=0.5):    pnl=$1088.00, sharpe=5.360, trades=86,089  (L4 in disguise)
  L6 (window=10s, flow=3.0):    pnl=$ 832.00, sharpe=3.830, trades=89,157  (regression)
  base (window=10s, flow=2.0):  pnl=$ 970.00, sharpe=4.580, trades=87,760

Headline deltas:

  L7 vs simple baseline:   +2097.69% pnl  (vs simple's $43.25)  -- PASS
                            (gate margin: +5.0% threshold cleared by ~419x;
                            slippage tied at 0.0/0.0)
  L7 vs base_algo:         -2.01% pnl    ($950.50 vs $970.00); -787 trades;
                            sharpe 4.530 vs 4.580 (-0.05, basically tied).
  L7 vs L4 (in-arm leader): -12.64% pnl  ($950.50 vs $1088.00); +884 trades
                            (+1.03%); sharpe 4.530 vs 5.360 (-15.5%).

Decision per pass_gate (baseline=simple, +5.0% pnl threshold, no slippage
regression): PASS. Slippage at 0.0/0.0 is tied (oracle has zero fill-cost
model), so the gate reduces to the pnl margin which L7 clears by ~419x.

### What L7 actually changed (vs L6 and vs L4)

L7's source preserves L4's algorithm structure exactly:
  * Ratio leg ABSENT (same as L4/L5/L6).
  * Absolute-only gate: `skip iff |net_flow_window| >= flow_threshold`.
  * BUY adverse on net <= -threshold; SELL adverse on net >= threshold.
  * Anti-cascade flat-flag (`_position_flat = True` after any skip).
  * Reduce-only orders always submitted.

The single change from L6 is TWO PARAMETERS shifted simultaneously:

  L6: window_seconds=10.0, flow_threshold=3.0   (the regressor)
  L7: window_seconds= 5.0, flow_threshold=1.0   (this loop)
  L4: window_seconds=10.0, flow_threshold=1.0   (the leader, prior best)

L7 effectively reverted flow_threshold back to L4's integer optimum (1.0)
AND additionally cut the window in half (10s -> 5s). So L7 is "L4 with a
shorter window," not "L6 with a shorter window." This was the deliberate
brief-summary-prescribed strategy: L6 confirmed the absolute-threshold
axis is bracketed (1:1088, 2:970, 3:832) with integer optimum at L4=1.0;
L6's "next" text explicitly instructed pivoting to the orthogonal window
axis at flow=1.0.

### Hypothesis verdict: PARTIALLY CONTRADICTED

Pre-loop prediction (Hypothesis section above): the 5s deque is a STRICT
SUBSET of the 10s view, so L7 should skip <= as many orders as L4 (i.e.
admit >= as many as L4). Net direction of pnl was held as bracketed:
shorter window could either capture near-term toxicity better (pnl > L4)
or miss slow-developing imbalance (pnl could drop toward base).

Observed:

  * Trade count: 86,973 vs L4's 86,089 = +884 trades (+1.03%). DIRECTION
    CORRECT -- shorter window admits MORE orders than L4 (the deque sees
    fewer of the 10s-window flow imbalances and fires the skip predicate
    less often). The strict-subset analysis was mechanically correct.
  * Pnl: $950.50 vs L4's $1088.00 = -$137.50 (-12.64%). The newly-admitted
    orders (the ones L4 skipped on the basis of a 5-10s-stale flow
    imbalance) were NET ANTI-INFORMATIVE: ~-$155 per 1k newly admitted
    orders (-$137.50 / 0.884k). That is MORE costly per extra admit than
    base's |net|=2 admits cost L6 ($98.8/k) or than L4's |net|=1 skips
    yielded vs base ($70.6/k). Interpretation: the 5-10s-stale flow
    imbalances are not stale noise -- they are GENUINELY informative
    near-future toxicity signals that the 10s window correctly catches.
    Cutting the window discards usable information.
  * Sharpe: 4.530 vs L4's 5.360 = -15.5%. Tracks the pnl drop with
    slightly degraded per-trade quality.

Read against the base ($970): L7 is also -$19.50 / -2.01% (basically a
tie within run-to-run noise, but trending slightly worse). So shortening
the window did NOT just sacrifice the L4 alpha -- it nudged the algorithm
back below base. The window axis at 5s is WORSE than 10s on this oracle.

The hypothesis's directional prediction (shorter window = less stale flow
= potentially more selective skips) is REVERSED in practice: less window
= LESS flow context = FEWER (but worse-selected) skips. The "stale flow"
framing was wrong; flow with up-to-10s memory is still informative for
the oracle's 30s forecast horizon.

### Partial recovery diagnosis (L6 -> L7)

L6 was -14.23% vs base; L7 is -2.01% vs base. The "recovery" comes almost
entirely from reverting flow_threshold from 3.0 back to L4's 1.0 -- that
alone (per the bracketed sweep) would have placed L7 at L4's $1088 if the
window were unchanged. The remaining gap (L4's $1088 -> L7's $950.50 =
-$137.50) is the COST of the orthogonal window cut from 10s to 5s.

Decomposing: at flow=1.0, window=10s -> $1088 (L4 leader); window=5s
gives $950 (L7). Direction of "shorter window helps or hurts" is now
firmly: HURTS by ~$137 / -12.6% at this step size on the oracle.

### Single highest-leverage next change (informs L8)

The window axis at flow=1.0 has TWO data points now: 10s ($1088 leader)
and 5s ($950.50 regressed). The gradient at 10s is negative going DOWN
(10 -> 5 hurts $137.50). The OPPOSITE direction (window 10 -> 20s) is
the one informative remaining probe to bracket the window-length
optimum:

  * If pnl@20s > $1088: the optimum is on the LOOSE/LONG window side and
    the window axis is the new productive lever beyond L4.
  * If pnl@20s < $1088 but > $950.50: window length is near-flat around
    10s with mild degradation in both directions; L4 remains the best
    bracketed point.
  * If pnl@20s <= $950.50: window length is convex around 10s with the
    optimum tightly bracketed at 10s; further window probes are dead.
  * Either way the window axis will be triangulated after L8 with three
    points (5, 10, 20), mirroring the threshold sweep (1, 2, 3) that
    closed in L6.

Risk consideration: a 20s window approaches the oracle's 30s forecast
horizon (visible in config.yaml: horizon_seconds=30.0). At 20s the deque
contains 2/3 of the predictive horizon worth of flow, which is the
maximum reasonable look-back before the gate's "past flow predicts near
future" assumption begins to break down. So 20s is the natural ceiling
for this single-axis sweep -- 30s or beyond would be expected to
mechanically degrade because flow >= 20s old can already have resolved
into price moves the gate is now misclassifying.

Alternative paths I considered and rejected for L8:
  * Asymmetric per-side thresholds (different BUY vs SELL flow_threshold)
    -- no brief-summary motivation across L1..L7; would be a leap into a
    new axis without bracketing window first.
  * Reintroducing the ratio leg with new params -- L1/L2/L3 exhausted
    that axis structurally.
  * Time-of-day or session regime gating -- no brief-summary motivation;
    introduces 2+ new parameters without a single-axis bracketing first.
  * Changing anti-cascade flat-flag semantics -- orthogonal but high-
    risk; should be the LAST untouched lever, after both axes
    (threshold, window) are fully bracketed.

The brief-summary-disciplined L8 = pivot to window=20s at flow=1.0.
