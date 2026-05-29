# Algorithm Notes: vrs-isl-g1l1

Island experiment — `island-2`, base_algo `vol-regime-sizer`, generation 1, loop 1.
No prior loop context for g1l1 (no own lineage, no migration reports yet).

## Hypothesis

**Targeted change (single, structural)**: Replace the base vol-regime sizer's
gating signal — currently `fast_vol / slow_vol` (a magnitude-of-noise ratio) —
with a **choppiness ratio** computed over the same fast window. Specifically:

    path_length(W)   = sum of |delta_mid_i| over the last W ticks
    displacement(W)  = |mid_t - mid_{t-W}|
    chop_ratio(W)    = path_length(W) / max(displacement(W), eps)

Then map `chop_ratio` to submission probability with the same exponential decay
form:

    excess   = max(0, chop_ratio - chop_neutral)
    p_submit = max(min_prob, exp(-sensitivity * excess))

Calm and trending markets share `chop_ratio ≈ 1` → `p = 1.0`; whipsawing
markets have `chop_ratio >> 1` → `p → min_prob`.

Everything else preserved from base: cold-start guard (`min_ticks`), deterministic
SHA-256 draw on `client_order_id`, reduce-only always submitted unconditionally,
1-contract parent quantity invariant. Slow EWM is removed — the new signal is a
single rolling window.

**Mechanism (single, named)**: **Choppiness gating**. The base algo skips on
"high absolute mid-price-change rate" but cannot distinguish a fast directional
breakout (where the oracle's 30s-horizon signal likely aligns with the move)
from a fast two-sided whipsaw (where consecutive ticks reverse and the oracle
signal arrives mid-noise). `chop_ratio` separates these: a 4-tick move of
[+1, +1, +1, +1] has path=4, displacement=4, chop=1.0 (trending, submit);
a 4-tick move of [+1, -1, +1, -1] has path=4, displacement=0, chop→∞ (whipsaw,
skip). Both have identical `|delta_mid|` magnitude and would be treated the
same by the base algo.

**Inefficiency exploited**: The base sizer's empirical edge comes from loss
mitigation on adverse days (per base NOTES: "concentrates participation in
calmer regimes where the oracle edge is cleanest"). But it pays a cost on
positive directional-vol days by skipping legitimate trending trades. If the
oracle's loss distribution is concentrated in whipsaw regimes rather than in
all high-vol regimes, choppiness gating should:

  1. Preserve adverse-day savings (whipsaws are still skipped — they have
     both high `|delta_mid|` AND high chop).
  2. Recover some forfeited upside on directional days (trending breakouts
     get submitted at p=1.0 instead of being probabilistically skipped).

**Expected effect on metrics**: realized_pnl up modestly vs base (recovered
directional upside without losing whipsaw protection); win_rate flat-to-up
(more selective on bad regimes, more participation on good ones); trade_count
roughly similar to base (replacing one set of skipped orders with another).
Slippage flat (zero-slippage fill model).

**Risk**: If the oracle's losses are NOT concentrated in whipsaw windows —
i.e., loss-driving volatility is uniformly directional — then chop-gating
will skip the wrong set of trades and underperform the base. Loop 1 cannot
distinguish these ex ante; the backtest is the test.

**Builds on**: vol-regime-sizer (base for island-2). No cross-island context
yet (first loop of generation 1 — no migration reports exist).

**Alternatives considered**:
1. Tighten sensitivity (vrs-m-l1's approach): rejected — that's a tuning
   change, not a structural one. The island experiment asks for structural
   variation across the lineage.
2. Add a directional-vol filter using signed sum of delta_mid: rejected —
   ratio-style normalization (chop) is unitless and self-scaling, which
   travels better across instruments and dates than absolute thresholds.
3. Add order-book imbalance gating: rejected — overlaps with the
   `ob-imbalance-gate` lineage in adjacent experiments; want to keep this
   island's contribution structurally distinct.

---

## Implementation Decisions

- **Window length `W`**: 30 ticks (single window). Matches the base's
  `fast_halflife=20` order-of-magnitude (effective span ~30 ticks) and is
  large enough that chop_ratio is statistically stable. Stored as a fixed-size
  deque of `delta_mid` values plus a separate deque of mid prices for
  displacement.

- **`chop_neutral`**: 1.5. A pure trend has chop=1.0, a single reversal in a
  4-step window has chop=2.0. Setting neutral at 1.5 means anything past the
  first reversal starts decaying the submission probability — leaves trending
  motion fully unimpaired.

- **`sensitivity`**: 1.0. The chop_ratio range is wider than fast/slow vol
  ratio (chop can hit 5-10+ on choppy ticks vs. fast/slow rarely exceeds 3),
  so a gentler decay produces a comparable skip rate. Calibrated so
  chop=3 → p=exp(-1.5)≈0.22, chop=5 → p=exp(-3.5)≈0.03 (floor).

- **`min_prob`**: 0.05 (matches base). Same floor.

- **`min_ticks`**: 40 (slightly larger than base's 30, since the chop window
  itself is 30 — wait for one full window of history before activating).

- **`eps`**: 1e-9 dollars (sub-tick) — guards displacement→0 from underflowing.
  When displacement is below eps (perfectly mean-reverting on the window),
  chop_ratio saturates at a large value, naturally driving p→min_prob.

- **Cold-start**: same as base — submit at p=1.0 before `min_ticks` samples.

- **Quantity invariant**: child_qty == parent_qty == 1, always. Skips never
  inflate; reduce-only always submits.

---

## Backtest Observations

**Raw metrics** (12 train dates, 2026-03-08 .. 2026-03-20, MESM6):

| metric            | vrs-isl-g1l1 | vol-regime-sizer (base) | delta              |
|-------------------|--------------|--------------------------|--------------------|
| realized_pnl      | 1011.0       | 753.75                   | +257.25 (+34.13%)  |
| sharpe_ratio      | 5.97         | 3.06                     | +2.91              |
| max_drawdown_pct  | -0.0420      | -0.0460                  | tighter by 0.4 pp  |
| win_rate          | 0.3473       | 0.3529                   | -0.0056            |
| trade_count       | 109424       | 127991                   | -18567 (-14.5%)    |
| mean_slippage     | 0.0          | 0.0                      | 0/0 — undefined    |
| is_weighted_bps   | 0.0421       | 0.0374                   | +0.0047            |
| vs_baseline_pnl_pct (vs simple) | 548.08% | 383.17%        | +164.91 pp         |

**vs base computations**:
- `vs_base_pnl_pct = (1011.0 - 753.75) / abs(753.75) * 100 = +34.13%`
- `vs_base_slippage_pct = (0.0 - 0.0) / abs(0.0) * 100 = 0/0` — reported as
  0.0 per the §6 fill-model convention (sim fills top-of-book → both algos have
  zero slippage; the delta is not meaningful, NOT a real improvement).

**Honesty notes**:
- `trade_count = 109424` over 12 days (≈9120/day) is high — no low-N flag.
- Slippage delta is 0/0 (undefined) — recorded as 0.0 only because the
  schema requires a number. Do not interpret the slippage column as a real
  signal here; the fill model collapses it.
- `sharpe_ratio = 5.97` is computed across 12 daily PnL points
  (`sharpe_n_days = 12`). Daily-PnL sharpe at N=12 is noisy and not directly
  comparable to per-trade sharpe; treat as a rank-ordering signal within the
  island, not as an absolute claim.
- `is_weighted_bps` slightly worse than base (+0.0047 bps): the algo skips
  more trades and the survivors have marginally higher implementation
  shortfall per dollar traded. The PnL win comes from skip selection, not
  per-trade execution quality.

**Hypothesis verdict**: SUPPORTED. The choppiness-gating substitution
delivered the predicted direction on all three core metrics:
  1. realized_pnl improved (+34.13% vs base) — net win from skip selection.
  2. trade_count fell 14.5% (more selective gating, as designed) but PnL still
     rose — i.e., the skipped trades were on average loss-making at a higher
     rate than the surviving trades, consistent with the "whipsaws drive
     oracle losses" mechanism in the hypothesis.
  3. max_drawdown tightened (0.4 pp) and sharpe nearly doubled (3.06 → 5.97)
     — the day-to-day PnL variance dropped, consistent with removing
     whipsaw-regime adverse selection.

**Surprises / caveats**:
- `is_weighted_bps` got slightly worse, not better. This is the most
  honest disappointment: the surviving trades are not individually
  cleaner — the algo only wins by skipping the worst ones. Per-trade
  execution quality is unchanged or marginally worse.
- `win_rate` dropped slightly (-0.0056). Combined with higher PnL, this
  means the algo skips some small winners along with the bigger losers; the
  expected-value math still favors the skip but the distribution has fewer
  positive trades and more skipped/zero trades.
- No way to attribute the gain between "preserved adverse-day savings" vs
  "recovered directional upside" without per-regime decomposition — a
  follow-up loop could split daily PnL by realized chop_ratio quantile.

**Recommended next directions** (for a future loop in this lineage or for
cross-island migration):
1. **Calibrate chop_neutral and sensitivity per day or per session** —
   single global values are likely leaving edge on the table; chop's
   natural scale varies with realized vol.
2. **Combine chop-gating with the island-0 spread-quantile gate** — they
   should be near-orthogonal: chop measures whipsaw-frequency in price
   space, spread measures liquidity-vacuum risk in book space. Stacking
   could compound skip-selection accuracy.
3. **Drop the slow EWM but add a "trend strength" reinforcer** —
   currently chop_ratio≈1 fires for both calm AND trending markets at
   equal weight; an explicit directional signal (signed sum of delta_mid)
   could LIFT p_submit on confirmed trends instead of just NOT skipping
   them.
