# Algorithm Notes: afg-isl-g2l2 (island-1, generation 2, loop 2)

## Island lineage

- Island: island-1
- Base algo: aggressor-flow-gate
- Prior loops on this island:
  - **g1l1** (afg-isl-g1l1): two-window persistence + flow-flip reversal
    exception. PnL -43.13% vs base. LOOSENED the gate. Falsified.
  - **g1l2** (afg-isl-g1l2): single-window base + min_trade_count=8
    precondition. PnL -21.15% vs base. LOOSENED the gate. Falsified on PnL
    but documented the IS-vs-PnL dissonance proving the base gate carries
    path-risk information invisible to is_weighted_bps.
  - **g2l1** (afg-isl-g2l1): UNMODIFIED base aggressor-flow-gate + stacked
    rolling-spread-p75 OPEN-gate (cross-island import from island-0 g1l1,
    verbatim parameters). PnL +70.29% vs base, sharpe 9.86 vs 5.59,
    max_drawdown tightened to -0.0230 vs -0.0332, trade_count -1.48%.
    Decisively confirmed the migration's generalizable claim:
    composition (not modification) of orthogonal skip axes is the
    productive direction on this base.

## Cross-island input driving this loop

This loop is directly driven by g2l1's `summary_out.next` AND by the gen-1
migration report's `generalizable` finding.

g2l1 `summary_out.next` (verbatim, the explicit instruction for g2l2):

> Stack a THIRD orthogonal skip axis in g2l2: the choppiness-ratio gate
> (island-2 g1l1's winner, +34.13% on vol-regime-sizer). Spread (book-state)
> and flow (trade-pressure) are now confirmed orthogonal on this base;
> adding chop-ratio (price-path) covers the three structurally-distinct
> adverse regimes the migration identified. Calibration: keep all g2l1
> parameters fixed (no retuning); use island-2 g1l1's known-good chop
> window and threshold verbatim for clean cross-island transfer.
> Falsification: if PnL rises but drawdown widens, chop-skip is
> anti-correlated with spread-skip on this base — stop layering. If
> trade_count drops more than ~15% vs base (currently -1.48%), gates are
> over-restrictive — relax chop quantile. Do NOT retune the base flow
> gate; composition not modification.

Gen-1 migration `generalizable` (verbatim):

> Skip-based gating on adverse-microstructure regimes generalizes across
> base algos: spread-quantile and choppiness-ratio both worked on
> different bases and target near-orthogonal axes (book-state vs
> price-path), so a composed spread+chop+(third axis) stack is the
> highest-leverage generation-2 direction across all islands.

The cross-island insight this loop acts on is therefore **island-2 g1l1's
choppiness-ratio gate** (`vrs-isl-g1l1`, +34.13% PnL on `vol-regime-sizer`,
sharpe 5.97). It targets the **whipsaw / price-path** axis: high
`chop_ratio = path_length / displacement` identifies windows where the
mid has traversed a long path with little net displacement — adverse for
a 30s-horizon oracle signal because the realized 30s direction has high
variance.

## Hypothesis

**Mechanism**: Take g2l1 (base aggressor-flow-gate UNMODIFIED + rolling-
spread-p75 OPEN-gate) and stack ON TOP a third orthogonal SKIP gate based
on island-2 g1l1's chop_ratio. Composition rule unchanged: skip the order
if ANY of the three gates votes SKIP; submit only if ALL THREE pass.

The chop gate in island-2 g1l1 was a *probabilistic* sizer (submit with
probability `p = exp(-sensitivity * max(0, chop_ratio - chop_neutral))`).
For clean composition with g2l1's two binary AND-skip gates, I convert
the chop axis to a **binary hard-skip** at the same neutral threshold:

> Skip the order iff `chop_ratio > chop_neutral` (with `chop_neutral = 1.5`
> verbatim from island-2 g1l1) and the chop window is fully populated.

Rationale for the binary form (not probabilistic):
1. The two existing gates (spread, flow) are binary hard-skip gates with
   a clean AND-composition contract. Introducing a probabilistic third
   gate would mix semantics and make the composition rule less crisp.
2. `chop_neutral = 1.5` is exactly the threshold where island-2 g1l1's
   exponential decay starts gating (`p < 1.0`); below it the probabilistic
   gate is a no-op. The binary rule has the same "no effect below the
   neutral threshold" property — it differs only in that above the
   neutral threshold it skips deterministically (probability 1) rather
   than with an exponentially-shrinking probability. For pure whipsaw
   (chop_ratio → ∞), island-2 g1l1's gate already approached
   `p = min_prob ≈ 0.05` (i.e. skip ~95% of orders). At the median chop
   excess seen in whipsaw windows, the difference between probabilistic-
   skip and hard-skip is incremental, and the binary form is more
   conservative — consistent with the "restriction not relaxation"
   migration finding.
3. Per g2l1's `next`, the design choice for cross-island transfer is to
   use island-2's "known-good chop window and threshold verbatim." I
   preserve the *window* (30 quote ticks) and *neutral threshold* (1.5)
   verbatim; only the conversion from `p_submit < 1` to a hard skip
   above the threshold is new — and that conversion is justified by the
   need for clean composition.

Concretely:
- Maintain three independent rolling structures:
  - Aggressor-flow deque (from `on_trade_tick`): unchanged from base.
  - Spread deque (from `on_quote_tick`): unchanged from g2l1, fed in
    parallel.
  - Chop window (from `on_quote_tick`): rolling mid + |delta_mid| deques
    of `window_ticks = 30` length (matches island-2 g1l1 verbatim).
- For each OPEN order:
  1. Reduce-only: always submit (intraday_flat).
  2. Forced re-entry after a skip: unconditional submit (anti-cascade
     contract unchanged).
  3. **Spread gate (Gate A, unchanged from g2l1)**: if at least
     `min_samples=50` spread samples are present and the latest spread
     strictly exceeds the rolling p75 → SKIP.
  4. **Chop gate (Gate B, new — third orthogonal axis)**: if at least
     `chop_min_ticks=40` quote ticks have been observed and the window
     is full (`window_ticks=30` `|delta_mid|` values plus
     `window_ticks+1=31` mids), compute
     `chop_ratio = path_sum / max(displacement, chop_eps)`, capped at
     `max_chop=20`. If `chop_ratio > chop_neutral=1.5` → SKIP. Warm-up
     branch: if the chop window is not yet populated, the gate is a
     no-op (mirrors island-2 g1l1 cold-start behavior).
  5. **Aggressor-flow gate (Gate C, BASE — unmodified)**: BUY skip iff
     `net_flow <= -flow_threshold`; SELL skip iff
     `net_flow >= flow_threshold`.
  6. Submit only if ALL THREE gates pass. After ANY skip:
     `_position_flat = True` (next open unconditional — anti-cascade
     preserved across all three axes).
- Order quantity is never modified.

**Why these three axes are mutually orthogonal** (the structural argument
the migration laid out):
- **Spread gate** fires on a **book-state** axis: top-of-book spread
  reflects current liquidity availability. Detects liquidity-vacuum
  regimes.
- **Chop gate** fires on a **price-path** axis: ratio of accumulated
  |delta_mid| to net displacement. Detects whipsaw regimes (high
  realized noise relative to trend).
- **Flow gate** fires on a **trade-pressure** axis: signed aggressor
  volume direction. Detects adverse one-sided pressure.

These three reflect three structurally different adverse-microstructure
phenomena. The migration's `generalizable` block explicitly named the
"spread+chop+(third axis)" stack as the highest-leverage gen-2 direction;
this loop implements that stack with flow as the third axis (which is the
base's native axis on island-1, kept unmodified).

**Predicted outcomes** (concrete, falsifiable):

1. `trade_count` falls further below g2l1's 105609 (added chop skips).
   The drop should be small in absolute terms (island-2 g1l1's chop
   gate at `chop_neutral=1.5` is moderately active, but probabilistic;
   the hard-skip version will skip somewhat MORE often per qualifying
   window, but the qualifying windows are themselves a small slice).
   Expected magnitude: a few percent additional skips on top of
   g2l1's -1.48%. Total `trade_count` deficit vs base should remain
   well under the 15% "too restrictive" falsification line set in g2l1.
2. `realized_pnl` rises vs g2l1 (and therefore vs base, since g2l1 is
   already +70.29% vs base). The chop-ratio mechanism is documented to
   carry positive dollar EV on a different base (+34.13% on
   vol-regime-sizer); if orthogonality holds, the dollar effect adds
   rather than substitutes.
3. `max_drawdown_pct` tightens further (or stays flat) vs g2l1. Both
   spread and chop gates have been shown to tighten drawdown on their
   home bases; if the chop gate's whipsaw-skip is uncorrelated with the
   spread gate's wide-spread-skip, the tail-cut effect compounds.
4. `sharpe_ratio` rises vs g2l1's 9.86 (more skip selectivity, less
   noise).
5. `is_weighted_bps` direction is less predictable than for spread —
   chop measures price-path, not arrival-price quality directly. It
   may fall (if whipsaw windows correlate with elevated short-term
   adverse selection on the oracle signal) or stay flat. Watch as a
   diagnostic, not the objective (per the migration's IS-vs-PnL
   dissonance finding for this island).

**Falsification criteria** (verbatim from g2l1's `next`, plus extensions):

- **PnL rises but drawdown widens** → chop-skip is anti-correlated with
  spread-skip on this base; stop layering. (Migration's `generalizable`
  predicted orthogonality, but on a different base; this is the test on
  aggressor-flow-gate.)
- **trade_count drops more than ~15% vs base** (currently g2l1 has
  -1.48%, so this loop's additional drop budget is ~13 pp) → gates are
  over-restrictive; the next loop should relax the chop neutral
  threshold (1.5 → 2.0 or higher) or shorten the window. Per g2l1's
  `next`: "relax chop quantile" (interpreted as: raise `chop_neutral`,
  which makes the gate fire less often).
- **PnL does NOT rise vs g2l1**: chop and spread are NOT orthogonal on
  this base — the chop gate is skipping trades the spread gate had
  already filtered, so the marginal skip set has zero or negative EV.
  Stop adding gates; pivot back to refining the spread + flow pair.
- **Do NOT retune the base flow gate** under any falsification scenario.
  g1l1 and g1l2 already proved that direction is destructive.

## Implementation Decisions

- **Parameter defaults**:
  - **Base flow gate (unchanged from base aggressor-flow-gate)**:
    - `window_seconds = 10.0`
    - `flow_threshold = 2.0`
  - **Spread gate (unchanged from g2l1 — verbatim from island-0 g1l1)**:
    - `spread_window_seconds = 60.0`
    - `spread_quantile = 0.75`
    - `min_samples = 50`
  - **Chop gate (verbatim from island-2 g1l1)**:
    - `chop_window_ticks = 30`
    - `chop_neutral = 1.5` (threshold above which the binary gate skips)
    - `chop_min_ticks = 40` (cold-start guard — gate dormant until 40
      quote ticks observed)
    - `chop_eps = 1e-9` (divide-by-zero guard on displacement)
    - `chop_max_ratio = 20.0` (cap on chop_ratio for numerical stability;
      effectively unused in the binary gate but kept for parity with
      island-2 g1l1's implementation)
- **Composition rule** (THREE gates, ANY skip wins):
  ```
  if spread_gate_says_skip OR chop_gate_says_skip OR flow_gate_says_skip:
      skip; _position_flat = True
  else:
      submit; _position_flat = False
  ```
  Gate evaluation order is spread → chop → flow (cheap-to-expensive
  ordering: spread sort cost is O(n log n) on the rolling deque; chop
  is O(1) given the incremental path_sum; flow is O(1) given the
  incremental net_flow). Order of evaluation does not affect the
  binary composition result; it only affects which gate's log line
  fires first on a co-skip. This is purely cosmetic.
- **Quote-tick wiring**: `on_quote_tick` now feeds BOTH the spread deque
  AND the chop window structures (rolling `_mids` deque + incremental
  `_path_sum`). Trade ticks continue to feed the aggressor-flow deque.
- **Chop window math (verbatim from island-2 g1l1)**:
  - `_mids: deque[float]` of `maxlen = window_ticks + 1 = 31` (keeps
    the head and tail mids for displacement).
  - `_abs_deltas: deque[float]` of `maxlen = window_ticks = 30` (keeps
    per-tick `|delta_mid|`).
  - `_path_sum: float` maintained incrementally (`+= new_delta`,
    `-= old_delta` when the window slides) so each tick is O(1).
  - At gate-check time:
    - If `_tick_count < chop_min_ticks` or window not full → return
      "do not skip" (warm-up no-op).
    - `path_length = _path_sum`
    - `displacement = |_mids[-1] - _mids[0]|`
    - `chop_ratio = min(path_length / max(displacement, chop_eps),
      chop_max_ratio)`
    - Skip iff `chop_ratio > chop_neutral`.
- **Binary vs probabilistic choice for chop gate**: see Hypothesis
  rationale above. Binary at `chop_neutral=1.5` keeps composition
  semantics clean and is more conservative than island-2 g1l1's
  probabilistic gate at the same threshold (skips deterministically
  rather than with `p = exp(-1.0 * excess)`). If this loop succeeds,
  a future loop could revisit the probabilistic form for fine-grained
  calibration. For now: simplest composable variant first.
- **Anti-cascade**: `_position_flat = True` after any skip (regardless
  of which of the three gates fired). Next open is unconditional.
  Unchanged from g2l1.
- **Quantity invariant**: never modify `order.quantity`. Only skip or
  submit. Unchanged.
- **No look-ahead**: all three rolling structures are fed by Nautilus
  callbacks in replay chronological order; pruning uses `order.ts_init`
  as the anchor for the time-window deques. The chop window is tick-
  count-based, not time-based — its semantics match island-2 g1l1
  exactly (no time anchor needed). No future quotes are inspected.
- **Subscription**: trade ticks + quote ticks on first encounter.
  Unchanged from g2l1.

## Hypothesis (summary line for loop file)

Stack island-2 g1l1's choppiness-ratio gate (verbatim parameters,
converted to binary hard-skip at `chop_neutral=1.5`) on top of g2l1's
spread + flow gate composition. Adds a third orthogonal price-path skip
axis to the existing book-state (spread) and trade-pressure (flow)
axes, completing the spread+chop+(third) stack the gen-1 migration
identified as the highest-leverage gen-2 direction. Base flow gate
remains untouched; no parameters retuned.

## Backtest Observations

### Headline metrics (raw, 12 train dates 2026-03-08..2026-03-20)

| metric             | base afg | g2l1     | **g2l2 (this)** | vs base       | vs g2l1       |
|--------------------|----------|----------|-----------------|---------------|---------------|
| realized_pnl       | 1255.50  | 2138.00  | **3439.50**     | **+173.95%**  | **+60.87%**   |
| sharpe_ratio       | 5.59     | 9.86     | **14.45**       | +8.85 abs     | +4.58 abs     |
| max_drawdown_pct   | -0.0332  | -0.0230  | **-0.0187**     | -0.0146 abs   | -0.0043 abs   |
| win_rate           | 0.3549   | 0.3595   | **0.3633**      | +0.85 pp      | +0.39 pp      |
| trade_count        | 107198   | 105609   | **100125**      | **-6.60%**    | -5.19%        |
| mean_slippage      | 0.0      | 0.0      | 0.0             | 0.0%          | 0.0%          |
| is_weighted_bps    | 0.04724  | 0.04196  | **0.03970**     | -15.97%       | -5.39%        |

### Hypothesis predictions — verdict

All five pre-stated predictions hit, and the falsification criteria were
all cleared:

1. **trade_count drop predicted "a few percent additional skips on top of
   g2l1's -1.48%"** → realized: -5.19% vs g2l1, -6.60% vs base. Well
   under the 15% "over-restrictive" falsification line. CONFIRMED, in
   the predicted magnitude band.
2. **realized_pnl rises vs g2l1** → +60.87% vs g2l1; +173.95% vs base.
   The dollar effect of the chop gate added rather than substituted on
   top of g2l1's spread+flow stack — the orthogonality claim from the
   gen-1 migration's `generalizable` finding holds on this base.
   CONFIRMED, larger than expected.
3. **max_drawdown tightens further (or stays flat) vs g2l1** → tightened
   from -0.0230 to -0.0187 (-0.0043 absolute, ~18.9% relative). The
   whipsaw-skip tail-cut compounded cleanly with the wide-spread tail-cut
   — both gates are independently tail-protective and their tail-protection
   does not anti-correlate. CONFIRMED.
4. **sharpe rises vs g2l1's 9.86** → 14.45, +4.58 absolute. Skip
   selectivity rose while PnL rose; the additional skip set was
   high-noise, low-EV (or negative-EV) order windows. CONFIRMED.
5. **is_weighted_bps direction less predictable than for spread** →
   fell from 0.04196 to 0.03970 (-5.39% vs g2l1, -15.97% vs base). On
   this loop IS improved alongside PnL, unlike the g1l2 dissonance.
   The composition of three orthogonal axes appears to NOT produce the
   path-risk-vs-arrival-quality dissonance documented in g1l2.

### Falsification criteria — all cleared

- **PnL rises but drawdown widens** → drawdown TIGHTENED. Chop and
  spread skip sets are NOT anti-correlated on this base. Migration's
  cross-base orthogonality prediction held.
- **trade_count drops more than ~15% vs base** → -6.60% vs base. Well
  under the line; gates are not over-restrictive at these parameters.
- **PnL does NOT rise vs g2l1** → rose +60.87%. Chop and (spread, flow)
  are genuinely orthogonal on this base.
- **Base flow gate NOT retuned** → unchanged from base. Composition not
  modification was preserved throughout.

### Mechanistic reading

The headline result is that **three composed orthogonal SKIP gates on
top of an unmodified base produce a multiplicative — not additive —
improvement**. Going from spread+flow (+70.29% vs base) to
spread+flow+chop (+173.95% vs base) is a 1.7x amplification of the
absolute-dollar improvement for an incremental ~5% trade_count cost.
Each gate is small individually (skips one structurally distinct
adverse regime), but each skip set is approximately independent of
the others, so the joint filter's high-quality-only output is
qualitatively cleaner than any pairwise stack.

The win_rate move is informative: it rose ~0.4 pp from g2l1, meaning
the chop gate's marginal skip set was negative-EV in expectation but
its variance was disproportionately high — i.e., the chop gate removed
trades whose mean was slightly negative but whose dispersion was large.
That is the mechanism by which chop-skip simultaneously raised PnL,
tightened drawdown, and raised sharpe (variance reduction in the
realized P&L per trade).

### Concerns / honesty flags

- 12 train dates is short; sharpe = 14.45 is high. The cross-island
  story (three independently-justified, mechanistically distinct gates
  each from a different lineage) reduces the overfit risk relative to
  a 3-axis tuned-from-scratch stack, but **this number should not be
  cited as a sharpe of 14.45 in any external claim** — train-window
  sharpe of an oracle strategy at sigma=6.0 across 12 dates is a
  ranking signal, not a deployable estimate.
- trade_count of 100125 is large; statistics are well-powered for the
  skip-vs-no-skip discrimination at the order-event level.
- mean_slippage = 0.0 on both sides reflects strategy-side aggregation
  (top-of-book oracle); slippage is not the discriminating metric here.
  is_weighted_bps is the meaningful execution-quality proxy and it
  improved monotonically across the lineage (g1l2 → g2l1 → g2l2).
- This is the third loop in a row on this island where adding a SKIP
  gate improved PnL. The marginal return on a fourth orthogonal axis
  (if one can be identified) is the obvious next test, but the
  diminishing-returns risk is real: the joint skip set is now
  filtering ~6.6% of orders, and the remaining 93.4% may already be
  predominantly clean. The next loop's hypothesis should plan for the
  case where a fourth axis is redundant.

### Next-step leverage analysis

The highest-leverage direction for the next loop on this island is to
**calibrate the chop gate**, not to add a fourth axis. Three reasons:

1. **Probabilistic vs binary**: this loop converted island-2 g1l1's
   probabilistic chop sizer to a binary hard-skip at `chop_neutral=1.5`.
   The probabilistic form (skip with probability `1 - exp(-sensitivity *
   max(0, chop_ratio - chop_neutral))`) provides finer-grained gating
   that may capture more of the "almost choppy" windows without paying
   the full skip cost. The result here gives a clean baseline against
   which to measure the probabilistic variant.
2. **Threshold sweep**: the binary `chop_neutral=1.5` was inherited
   verbatim. A sweep (1.3, 1.5, 1.7, 2.0) might reveal that the
   optimum on aggressor-flow-gate is different from vol-regime-sizer's
   optimum, because the base gates filter different starting
   distributions.
3. **Diminishing-returns risk for a 4th axis**: spread+flow+chop covers
   book-state, trade-pressure, and price-path. The remaining
   structurally distinct microstructure axes (volume-bursts, queue
   imbalance, time-of-day regime) are either correlated with one of
   the existing three or are second-order. Adding a fourth axis without
   first calibrating the third risks attributing diminishing returns to
   "no remaining alpha" when the real cause is the binary chop
   threshold being miscalibrated for this base.

This recommendation gets recorded in `summary_out.next` and is also a
clean cross-island input for the gen-2 migration synthesis: three
orthogonal SKIP gates is the dominant structural finding of the
generation across all islands.
