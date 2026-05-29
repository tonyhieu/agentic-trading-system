# afg-b-l6 — aggressor-flow-gate with LOOSENED absolute threshold (flow=3.0)

Brief-summary arm, loop 6. Prior context = ONLY the `summary_out`
(changed / outcome / hypothesis / brief_summary / next) blocks from
loop-1.json (afg-b-l1), loop-2.json (afg-b-l2), loop-3.json (afg-b-l3),
loop-4.json (afg-b-l4), and loop-5.json (afg-b-l5), plus the headline
metrics for each. Per the brief-summary mode boundary I did NOT read
any prior NOTES.md prose or any full_reasoning text -- only the brief
summaries and the L4/L5 source files (mechanical chassis-shape
inspection only, to know parameter and class structure; L4 and L5 are
identical except for the no-op threshold change).

## Hypothesis

L1 + L2 + L3 + L4 + L5 brief_summary collectively establish:

  1. L1 (pure-ratio gate, |r| >= 0.35): WORSE than base (-53.25% pnl,
     +13,481 extra admits). Ratio-only reformulation cannot work.
  2. L2 (CONJUNCTION base AND ratio): WORSE than base (-52.14% pnl,
     +14,245 extra admits). ANDing admits the UNION, not the
     intersection.
  3. L3 (DISJUNCTION base OR ratio-with-busy-floor): EXACTLY equal to
     base. Ratio leg structurally dominated by absolute leg.
  4. L4 (RATIO LEG REMOVED + abs threshold 2.0 -> 1.0): GENUINELY
     BEATS base (+12.16% pnl: $1088 vs $970, -1,671 trades, sharpe
     5.36 vs 4.58). Validates L1 monotone-yield rule in inverse
     direction: ~$70.6 per 1k extra skips.
  5. L5 (further tighten 1.0 -> 0.5): BIT-FOR-BIT IDENTICAL to L4.
     The flow_threshold lever has INTEGER RESOLUTION on this oracle
     (net_flow is the signed sum of integer trade sizes, so the open
     interval (0, 1) contains no admissible values). Decimal-fraction
     tweaks below 1.0 are mechanically inert.

The L5 finding is the critical update: along the absolute-threshold
axis, only INTEGER STEPS produce different gate behavior. Effective
states sampled so far:

  * threshold = 2 (base)   -> pnl $970,  trades 87,760, sharpe 4.58
  * threshold = 1 (L4=L5)  -> pnl $1088, trades 86,089, sharpe 5.36

To continue the threshold sweep with a new informative integer step,
the options are:

  * threshold = 0 -- DEGENERATE. The gate fires on |net|>=0 i.e.
    almost always (whenever the deque is non-empty). Skips nearly
    all entries. Catastrophic -- not a useful test.
  * threshold = 2 -- equals base. No new info.
  * threshold = 3 -- LOOSEN one integer step beyond base. Admits
    every order base would admit PLUS orders with |net|=2 (since
    base's predicate is |net|>=2 i.e. skip on |net|=2, while L6's
    is |net|>=3 i.e. admit on |net|=2). This is the most
    informative remaining single-parameter test.
  * threshold = 4, 5, ... -- further loosen. Save for after L6 if
    the threshold=3 result is interesting.

L5's "next" text explicitly recommends threshold = 3.0 as L6, citing
the L1 monotone-yield rule extrapolation hypothesis: extra admits
beyond base cost pnl, so loosening should DECREASE pnl below base's
$970.

L6 single-parameter monotone change: flow_threshold 1.0 -> 3.0 (i.e.
2 integer steps UP from L4=L5's effective state, or equivalently 1
integer step UP from base's 2.0). Expected admitted set: strict
superset of base's, which is itself a strict superset of L4's. Window
length (10s), anti-cascade flat-flag, and reduce-only-always-submit
semantics preserved exactly from L4 / L5.

Expected direction (per brief-summary evidence + L1 monotone rule
extrapolation hypothesis):

  * trade_count: rises above base (87,760), likely by some fraction
    of L4's delta -- depends on how many windows have |net_flow|=2
    relative to those that have |net_flow|=1. If symmetric, expect
    trade_count somewhere around 89-90k (above base).
  * pnl: by the L1 rule applied to the loose side (~$47-$70/1k extra
    admits destroys pnl), expect pnl below base's $970. If the
    newly-admitted orders at |net|=2 are similarly anti-informative
    to those at |net|=1, expect pnl roughly $880-$910.
  * Sharpe: should decline below base's 4.58 if pnl drops while
    trade count grows (variance per trade roughly unchanged).
  * If pnl > $1088 (L4): SURPRISING. Would indicate the curve has a
    secondary maximum on the loose side, contradicting the L1
    monotone-yield extrapolation.
  * If pnl between $970 and $1088: also surprising -- would mean
    loosening from base helps (monotone-yield rule reversed on this
    side). Probably indicates L1 rule was an artefact of the
    distribution near |net|=1, not a general property.

Anti-rationale check: I considered alternatives:

  * Window length change (10s -> 5s or 20s): plausible orthogonal
    axis. Would attack a different lever. But the L5 finding tells
    us we have only TWO sampled points along the (informative)
    integer-threshold axis (base=2 and L4=1); we have not yet
    bracketed the loose-side behavior. Threshold=3 is the cheapest
    way to do so. Save window length for L7+.
  * Per-side asymmetric thresholds: not motivated by brief-summary
    evidence. Distribution of BUY-skip vs SELL-skip yields not yet
    reported in summaries.
  * Reintroduce ratio: L1+L2+L3 exhausted that axis.
  * Threshold = 0: degenerate (see above).
  * Threshold = 4 or 5: further loosening, but skipping the
    threshold=3 test would leave a gap in the sweep data. Take the
    smaller integer step first.
  * Skip threshold sweep entirely and pivot to anti-cascade
    behaviour or other orthogonal change: brief-summary stream
    has not yet provided evidence that those are higher leverage
    than completing the threshold sweep.

## Implementation Decisions

  * Single structural change vs L5: NONE -- the algorithm shape stays
    identical to L4 and L5 (ratio leg already absent, absolute-only
    gate, anti-cascade flat-flag, reduce-only-always-submit, 10s
    window).
  * Single parameter change vs L5 (effective L4): `flow_threshold`
    0.5 (L5) / 1.0 (L4 effective) -> 3.0 (LOOSEN by 2 integer steps
    from L4 / by 1 integer step from base). Inclusive comparison
    preserved (skip iff |net_flow| >= 3).
  * Window kept at 10s -- isolate the threshold change.
  * Direction-side logic: BUY adverse when net <= -3.0; SELL adverse
    when net >= 3.0. Per-side signed test mirrors base + L1 + L2 +
    L3 + L4 + L5 exactly.
  * Anti-cascade semantics (`_position_flat = True` after any skip,
    forcing the next OPEN through unconditionally) preserved exactly.
    Reduce-only orders always submit (intraday_flat).
  * Quantity invariant strictly preserved -- orders are skipped or
    submitted unmodified.
  * Class names: `AfgBL6Config` / `AfgBL6Algorithm`; factory
    `get_execution_algorithm` with new defaults.

  Boundary check: the threshold 3.0 means the gate fires only when
  the 10s window has net imbalance of 3 or more contracts in the
  adverse direction. Many windows that have |net|=2 (and would be
  skipped under base) are now admitted. Trade count will rise
  meaningfully above base's 87,760.

## Backtest Observations

### Raw numbers (11-date apples-to-apples train window; 20260319 OOM-dropped on both sides)

| metric           | base (aggressor-flow-gate, threshold=2.0) | L4 = L5 (threshold=1.0) | L6 (threshold=3.0)       |
|------------------|------------------------------------------:|------------------------:|-------------------------:|
| realized_pnl     | 970.00                                    | 1088.00                 | 832.00                   |
| sharpe_ratio     | 4.5809                                    | 5.3600                  | 3.8273                   |
| trade_count      | 87,760                                    | 86,089                  | 89,157                   |
| win_rate         | 0.35441                                   | 0.35399                 | 0.35432                  |
| max_drawdown_pct | -0.0333 (full 12d)                        | -0.03235                | -0.03607                 |
| mean_slippage    | 0.0                                       | 0.0                     | 0.0                      |
| is_weighted_bps  | n/a                                       | n/a                     | 0.05039                  |
| vs simple pnl%   | +2142.77                                  | +2415.61                | +1823.70                 |
| vs base pnl%     | 0.00                                      | +12.16                  | -14.23                   |
| vs base trades   | 0                                         | -1,671                  | +1,397                   |

(`simple` baseline pnl on the matched 11 dates: $43.25 -- the same anchor L1..L5 used; ignore the full-12d $156 sum that appears in the simple/backtest-results.json header.)

### Decision per pass_gate

`config.yaml`: `min_pnl_improvement_pct=5.0`, `max_slippage_regression_pct=5.0`, `close_margin_pct=2.0`. vs simple = +1823.70% (gate cleared by ~365x). Slippage tied at 0.0/0.0 (zero fill-cost model). **STATUS = PASS** vs the formal pass_gate. But L6 REGRESSES vs the in-arm leader L4 = L5: pnl -23.5% ($1088 -> $832), sharpe -28.6% (5.36 -> 3.83), trade_count +3.6% (86,089 -> 89,157). Refinement targets vs L4: ALL FAIL (sharpe delta -1.53 vs required +0.5; pnl delta -23.5% vs required +2.0%; etc.). This is a pass but the lever moved the wrong way, as predicted.

### Mechanical diff: what L6 actually changed vs L4

Single parameter change: `flow_threshold` 1.0 (L4 effective) -> 3.0. Everything else preserved exactly: 10s window, ratio leg absent, anti-cascade `_position_flat` semantics, reduce-only-always-submit, side-signed predicate (BUY adverse when net <= -threshold; SELL adverse when net >= threshold). Equivalent to going one integer step LOOSER than base (base = 2.0, L6 = 3.0). The admit set changes:

  * base (threshold=2): SKIP iff |net|>=2 -- skips orders at |net|=2, 3, 4, ...
  * L4   (threshold=1): SKIP iff |net|>=1 -- skips orders at |net|=1, 2, 3, ... (strict superset of base's skips)
  * L6   (threshold=3): SKIP iff |net|>=3 -- skips orders at |net|=3, 4, 5, ... (strict subset of base's skips; orders at |net|=2 newly ADMITTED)

So L6 admits everything base admits PLUS orders with |net|=2.

### Hypothesis verdict

**CONFIRMED — and bracketing now complete on the loose side.** Hypothesis predicted that loosening would DECREASE pnl below base's $970 (per the L1 monotone-yield rule extrapolated to the loose side). Actual: pnl = $832 < $970 base < $1088 L4. The +1,397 newly-admitted orders (at |net|=2) cost $138 pnl, i.e. ~$98.8 per 1k extra admits. This is the same sign and similar magnitude to:

  * L1 inverse (skipping at base+ratio): cost ~$47/1k extra admits beyond base
  * L4 inverse (skipping at |net|=1 added on top of base): yielded ~$70.6/1k extra skips
  * L6 (admitting at |net|=2 removed from base's skip set): cost ~$98.8/1k extra admits

All three points are consistent with the L1 monotone rule: orders near the |net|=1-2 boundary are weakly anti-informative; admitting them costs pnl, skipping them yields pnl, with a roughly uniform per-order penalty in the $47-$100 range. The threshold sweep along the absolute axis is now confirmed monotone with the **integer optimum at threshold=1.0** (L4/L5):

| threshold | pnl    | trades  | sharpe |
|-----------|-------:|--------:|-------:|
| 1.0 (L4)  | 1088   | 86,089  | 5.36   |
| 2.0 (base)| 970    | 87,760  | 4.58   |
| 3.0 (L6)  | 832    | 89,157  | 3.83   |

Smooth monotone curve. L7 should NOT continue sweeping the absolute threshold axis -- it is fully bracketed and the optimum is L4.

### Single highest-leverage next change for L7

Pivot to an ORTHOGONAL lever at fixed `flow_threshold=1.0` (L4's optimum). Top candidate: **shorten `window_seconds` from 10s to 5s** at threshold=1.0. Rationale (within brief-summary discipline):

  * The threshold axis is exhausted (3 sample points, monotone, optimum at L4).
  * The window axis has never been touched -- all of base + L1..L6 use 10s.
  * Shorter window = less stale flow info, faster reaction to regime shifts. Could yield more selective skips (fewer false positives from old flow imbalance) without changing the per-skip yield curve.
  * Symmetric counterpart (lengthen to 20s) is the alternative; pick 5s first because oracle signals have horizon_seconds=30 (from config.yaml) -- a window comparable to the signal half-life is more likely than one near the full forecast horizon.
  * Avoid: any further threshold tweak (sweep complete), reintroducing the ratio leg (L1+L2+L3 exhausted), per-side asymmetric thresholds (no brief-summary motivation), changing the anti-cascade flag (orthogonal but high-risk).

L7 single-parameter change: `window_seconds` 10.0 -> 5.0 at `flow_threshold=1.0`.
