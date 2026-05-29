# afg-isl-g3l1 — Notes

## Lineage

- **Island**: island-1 (base: aggressor-flow-gate, abbrev: afg)
- **Generation**: 3, Loop in generation: 1
- **Parent**: afg-isl-g2l2 (the gen-2 winner: +173.95% vs base; sharpe 14.45)
- **Cross-island inputs**:
  - Spread gate ported from island-0 g1l1 (rolling-spread-p75 OPEN-gate)
  - Chop gate ported from island-2 g1l1 (choppiness-ratio sizer, converted by g2l2 to a binary hard-skip)

## Hypothesis

**Single targeted change**: raise `chop_neutral` from 1.5 → 1.7 on the
binary chop hard-skip gate; all other parameters and the three-axis
spread + chop + flow AND-skip composition on the unmodified base
aggressor-flow gate are preserved verbatim from g2l2.

This loop tests the gen-2 migration's `base_specific` (1) directive
explicitly:

> "When porting a gate, port the MECHANISM and the COMPOSITION
> SEMANTICS but RETUNE the operating point against the new base's
> pre-filter population — a parameter sweep around the ported value
> is cheaper than discovering the misfire after a full backtest."

g2l2's chop gate uses `chop_neutral = 1.5` verbatim from island-2 g1l1
(`vrs-isl-g1l1`). On vrs, that threshold was calibrated against a
surviving-population distribution containing the FULL pre-chop trade
population (vrs has no other pre-filter — chop was its only gate). On
this base (afg), the chop gate runs AFTER the spread gate (book-state)
and BEFORE the base flow gate (trade-pressure), so the population
arriving at the chop gate has already had its wide-spread liquidity-
vacuum slice removed by Gate A. That filtered population's
`chop_ratio` distribution is plausibly narrower / less choppy than vrs's
because wide-spread bursts correlate with whipsaw price paths — so the
verbatim 1.5 threshold likely sits closer to the body of this filtered
distribution than it did on vrs's.

g2l2's reported chop-gate firing rate is consistent with this: total
trade_count fell only ~5% incremental when adding chop to the
spread+flow stack (well below the ~15% over-restrictive falsification
line); the chop gate is firing infrequently. Whether 1.5 is the
optimum, or merely a workable threshold that happened to port, is
unknown — and the symmetric retune to what island-0 g2l2 *should* have
done (raise threshold above 1.5 to land in the tail of the new
distribution rather than the body) is to test 1.7 here.

### Why this calibration variant (not the other)

g2l2's `summary_out.next` named two calibration directions:

  (a) Probabilistic-vs-binary form (per island-2 g1l1's decay).
  (b) Threshold sweep around `chop_neutral` (1.3, 1.5, 1.7, 2.0).

Picking (b) at 1.7:
1. Direction (a) changes BOTH the shape AND firing rate of the gate at
   once — confounded with the binary-AND-skip composition rule that g2l2
   showed worked. Direction (b) holds the mechanism and composition
   semantics constant and varies only the operating point — the cleanest
   one-axis calibration test.
2. Lowering to 1.3 would tighten further (chop gate fires more); g2l2
   was already at trade_count -6.6% vs base. Pushing toward the -15%
   falsification line risks an ambiguous loss (was 1.5 right, or did we
   overshoot?). Raising to 1.7 admits more "near-choppy" trades; if
   those are positive-EV the per-base retune direction is confirmed, if
   negative-EV the body of this filtered distribution does contain
   higher-EV trades than the tail and the optimum is at-or-below 1.5
   (g3l2 would then test 1.3).
3. Asymmetric upside: a successful retune validates the gen-2
   `base_specific` lesson on this island specifically (so far only
   demonstrated by FAILURES on the other two islands' g2l2); a failed
   retune narrows the chop calibration optimum on this base to ≤ 1.5
   without crossing falsification thresholds.

### Falsification predictions

- If pnl ↓ and trade_count ↑ — admitted "near-choppy" trades are net
  negative-EV; 1.5 is at or below the true optimum; g3l2 should test 1.3.
- If pnl ↑ and trade_count ↑ modestly — calibration retune confirmed;
  optimum on this composed stack is at or above 1.7.
- If pnl flat (±2%) and trade_count moves <1% — chop axis approaching
  saturation; g3l2 should pivot to (a) the probabilistic form or to a
  different fourth axis.
- If trade_count rises >10% AND pnl ↓ — chop axis is now toothless on
  this base at the new threshold; the threshold sweep has overshot the
  tail; consider 1.6 in g3l2.

### What is NOT changed

Per gen-2 `generalizable` finding (1) "ADD orthogonal SKIP axes ON TOP
of an unmodified base; never modify the base":

- Base aggressor-flow gate: `window_seconds=10.0`, `flow_threshold=2.0`
- Spread gate: `spread_window_seconds=60.0`, `spread_quantile=0.75`,
  `min_samples=50`
- Chop window shape: `chop_window_ticks=30`, `chop_min_ticks=40`,
  `chop_eps=1e-9`, `chop_max_ratio=20.0`
- Chop gate mechanism: binary hard-skip (NOT probabilistic)
- Composition: AND-skip across all three binaries
- Gate evaluation order: spread → chop → flow (invariant for AND-skip
  composition; affects only which gate's log line fires first on co-skip)
- Quantity invariant: `order.quantity` never modified
- Anti-cascade contract: `_position_flat = True` after any skip
- Reduce-only orders submit unconditionally (intraday_flat compliance)

## Implementation

Started from `execution_algos/afg-isl-g2l2/execution_algorithm.py`
(the gen-2 winner). The only structural change is the default of
`chop_neutral` in `AfgIslG3L1Config` and in `get_execution_algorithm`,
both flipped 1.5 → 1.7. Class names renamed to match the algo id.
Identifier and registry entry added under `execution_algos/__init__.py`.

## Backtest Observations

### Headline (raw, 12-date train aggregate)

- realized_pnl = **3399.50** (vs base afg 1255.50 → **+170.77%**; vs prior afg-isl-g2l2 3439.50 → **-1.16%**)
- sharpe_ratio = **14.4245** (vs base 5.5944 → **+8.83 abs**; vs g2l2 14.4452 → **-0.0207 abs**, indistinguishable)
- max_drawdown_pct = **-0.018675** (identical to g2l2 to 6 decimals; vs base -0.033250 → 43.8% tighter)
- win_rate = **0.36338** (vs base 0.35488 → +0.85 pp; vs g2l2 0.36335 → +0.00 pp, indistinguishable)
- trade_count = **100173** (vs base 107198 → -6.55%; vs g2l2 100125 → **+48 trades, +0.048%**)
- mean_slippage = **0.0** (book-cross order pattern; no regression possible)
- is_weighted_bps = **0.03980** (vs base 0.04724 → -15.74%; vs g2l2 0.03970 → +0.25%, indistinguishable)

### Hypothesis verdict against the four pre-stated falsification criteria

The pre-stated outcomes were partitioned by `(pnl, trade_count)` direction. Mapping the
observed result onto those bins:

| criterion stated | observed | matches? |
|---|---|---|
| `pnl ↓ AND trade_count ↑` → admitted trades net negative-EV; optimum ≤ 1.5 | pnl -1.16%, trade_count +0.048% | **YES (degenerate boundary case)** |
| `pnl ↑ AND trade_count ↑ modestly` → retune confirmed; optimum ≥ 1.7 | — | no |
| `pnl flat (±2%) AND trade_count moves <1%` → chop axis saturating; pivot | pnl |Δ|=1.16% < 2%, |Δtrade_count|=0.048% < 1% | **YES** |
| `trade_count rises >10% AND pnl ↓` → overshot tail; try 1.6 | — | no |

Two of the four bins describe this result, because the magnitude of change in BOTH axes
is essentially within measurement noise: pnl moved -1.16% (inside the ±2% flat
band), trade_count moved +0.05% (well inside the <1% saturation band), sharpe moved
-0.02 abs (indistinguishable from zero given sharpe_n_days=12), drawdown is identical
to 6 decimals, win_rate to 5 decimals. Only 48 incremental trades were re-admitted by
loosening 1.5 → 1.7. Their net pnl is -40.0 (=3399.50-3439.50), or **-0.83 per
incremental trade** vs the prior surviving population's +34.35 per trade — meaning the
admitted "near-choppy" trades around chop_ratio ∈ (1.5, 1.7] are individually below
the cohort mean but the count is too small to be statistically separable from noise
across 12 dates.

### Interpretation

The chop_neutral=1.5 calibration ported from vrs-isl-g1l1 is **already near-optimal**
on this base's composed (spread → chop → flow) stack. The retune to 1.7 is a true
null-result, not a falsification: the per-base distribution argument in the
Hypothesis section (that the spread pre-filter shifts the surviving chop_ratio
distribution upward and the optimum should also shift upward) is not supported by
this data — between 1.5 and 1.7 the chop_ratio distribution has essentially zero
mass.

This is structurally consistent with island-0 g2l2's evidence (porting vrs's 1.5
threshold to ptg admitted only ~1.7k trades) and island-2 g2l2's evidence (its own
verbatim 1.5 is its lineage optimum). Across all three islands, the chop_neutral=1.5
operating point appears robust to base context — falsifying the gen-2 migration's
`base_specific` (1) claim that the threshold needs base-specific retuning. The
**chop-ratio distribution** appears to have a sharp tail that 1.5 sits inside on all
three bases.

### Implication for g3l2

The chop axis is **saturated** on this base — neither tighter (g3l2 candidate: 1.3,
already a-priori risky given g2l2 was -6.6% trade_count) nor looser (this loop: 1.7,
demonstrated flat) provides headroom. The bin-(c) directive in the Hypothesis names
the right next step: **either probabilistic chop dosage** (varies firing rate at the
margin, not just the threshold), **or a structurally distinct fourth axis**.

The gen-2 migration's `base_specific` (3) section named top-of-book size asymmetry
(`bid_size` vs `ask_size` ratio) as a candidate fourth axis for vrs. On afg
specifically, the gen-2 migration's `generalizable` (4) section flagged the three-axis
ceiling as the working hypothesis — but explicitly named four candidate alternatives
(queue imbalance, top-of-book size asymmetry, volume bursts, time-of-day) for
post-calibration test. With calibration now exhausted (this loop is the calibration
result), g3l2 should select the most independent-from-existing axis.

Of the four candidates:
- **top-of-book size asymmetry** measures queue depth imbalance, a distinct snapshot
  of book state from spread (which measures top quote DISTANCE, not depth). Likely
  independent of spread, partially independent of flow (signed flow rebalances queue
  asymmetry but only at trade arrivals, not between trades).
- **queue imbalance** is essentially the same metric expressed differently.
- **volume bursts** correlate with the existing flow gate.
- **time-of-day** is a phase axis, not a microstructure axis — likely correlated with
  both spread (open/close widening) and flow.

Recommendation for g3l2: **try top-of-book size asymmetry** as the fourth orthogonal
SKIP axis on top of the unmodified spread+chop(1.5)+flow stack, with binary AND-skip
composition consistent with g2l2's working composition rule. Falsification: if
trade_count drops >10% OR pnl regresses, the four-axis ceiling is real and the
lineage should pivot to probabilistic-chop variation as the alternative direction.
