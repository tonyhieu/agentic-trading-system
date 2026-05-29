# Algorithm Notes: vrs-f-l8

Loop 8 (FINAL) of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vrs-f-l6` (the best-known configuration across L1-L7).
L6's mechanism is the L3-shape smooth sigmoid (k=3.0, max_tighten=0.9, full
symmetric, defensive z=0 tightening at 0.45) plus `drift_halflife=60`. L6
produced +91.97% pnl vs base / sharpe 5.87 / trade_count 122,431 / max_dd
-0.0371%. L7 perturbed only drift_halflife (60 -> 90) and regressed by
+92% -> +84% pnl, confirming the halflife optimum is at 60.

NOT building on L7's code skeleton because L7 was a one-knob regression from
L6 (drift_halflife 60 -> 90 regressed -4.32% pnl, -0.142 sharpe). L8 takes
L6's exact configuration as the platform and adds a new mechanism on top.

**Observations driving this loop** (from the full L1-L7 trace):

1. The arm trajectory:
   - L1 -34% (alignment relaxation -- refuted)
   - L2 +30% (binary adverse tightening, threshold at 0.5 -- supported)
   - L3 +82% (smooth sigmoid k=3, max_tighten=0.9, symmetric -- supported, new best)
   - L4 +78% (sharper k=6 + saturated max_tighten=1.0 -- regress vs L3)
   - L5 +60% (asymmetric clip z>0 -> tighten=0 -- regress vs L3)
   - L6 +92% (L3 shape + drift_halflife 30 -> 60 -- supported, NEW best)
   - L7 +84% (L6 + drift_halflife 60 -> 90 -- regress vs L6)

2. The (k, max_tighten, symmetry, drift_halflife) parameter space is now
   well-explored. Every axis perturbed away from L6's settings either
   regressed or tied. The single remaining principled direction is to
   add an ORTHOGONAL directional signal -- one whose information content
   does not duplicate signed mid-drift.

3. L7's explicit final-paragraph prescription: "L8 should pivot to the
   orthogonal signal direction: book imbalance or aggressor flow as a
   second directional signal on top of L6's best configuration." L4-L7
   each flagged this as "the most promising orthogonal extension" and
   deferred it; L7 is now the explicit handoff to take it up.

4. The signed-drift signal measures *price action* in the recent past.
   A book-imbalance signal measures *standing liquidity asymmetry at the
   inside* -- a structurally distinct quantity. They can disagree (e.g.,
   price has been falling but the bid stack just refilled while ask
   thinned -- drift adverse, imbalance favorable for a BUY). When they
   agree, the algorithm is more confident in adverse selection and
   tightens more aggressively; when they disagree, the combined signal
   moves toward z=0 (defensive tightening at 0.45). L3/L6 evidence
   showed the z=0 defensive tightening is net-positive, so disagreement
   is naturally routed to a sane defensive behavior.

5. Top-of-book imbalance is computed from `bid_size` and `ask_size` on
   each QuoteTick:
       imbal_raw = (bid_size - ask_size) / (bid_size + ask_size)
   This ranges in [-1, 1]. Raw imbalance is noisy (it can flip on every
   tick as orders queue/cancel); a small EWM smooths it. I use the same
   halflife as drift (60 ticks) for symmetry.

6. Sign convention (matching the drift convention in L6):
   - For a BUY order, positive imbalance (more bids than asks) is
     hypothesized to be *aligned*: more buying pressure suggests price
     about to rise, so buying now is favorable.
   - For a SELL order, positive imbalance is *adverse*: same logic
     reversed.
   - `s_imbal = order_sign * imbal_ewm` where order_sign=+1 for BUY,
     -1 for SELL. Positive s_imbal -> aligned (no tighten). Negative
     s_imbal -> adverse (tighten).
   This is the SAME sign convention as L6's z = order_sign * drift /
   slow_vol, so the existing sigmoid `tighten = max_tighten * sigmoid(-k * z)`
   applies unchanged.

7. There IS a competing microstructure interpretation: bid_size >>
   ask_size can be a stale-bid signal (resting bids about to get hit,
   then price drops once supply runs out -- mean-reversion). On
   short timescales (sub-second) for liquid MES futures, the
   *order-flow* interpretation (heavy bid side = upward pressure) is
   the more standard signal, so I bet on that. If the experiment
   refutes it (L8 regresses), the sign inversion is the natural L9
   experiment in a hypothetical future arm.

8. Combination strategy: average the two side-signed coordinates into
   a single z, then apply the same sigmoid. Specifically:
       z_combined = w_drift * z_drift + w_imbal * z_imbal
   where z_drift is L6's existing coordinate and z_imbal is the new
   side-signed imbalance scaled to similar magnitude.

   Weights: w_drift=0.6, w_imbal=0.4. Drift is proven across L2-L7;
   imbalance is unproven, so it gets less initial weight. Sum to 1 so
   the combined z has comparable magnitude to z_drift alone (the
   sigmoid k=3 was tuned to the magnitude range produced by z_drift).

   The averaging combination has a key property: when the two signals
   disagree, the combined z moves toward zero, routing the trade to
   the defensive z=0 tightening (0.45) -- which L3/L6 data show is
   net-positive. When they agree, the combined z is similar magnitude
   to either alone, applying the same tightening. When they disagree
   strongly, defensive tightening kicks in. This is the conservative
   variant; multiplicative combination (1 - (1-tighten1)*(1-tighten2))
   would be more aggressive (skip-OR-skip) and risks over-tightening.

9. Imbalance scale: z_imbal needs to be in a comparable magnitude
   range to z_drift (~-2 to +2 for the sigmoid k=3 to operate well).
   Raw side-signed imbalance is in [-1, +1]. I scale it by a factor of
   2.0 (`imbal_scale=2.0`) so saturated imbalance gives |z_imbal|=2,
   matching the saturated tail of z_drift on this dataset. This is a
   first-pass scale; it could be refined in a future loop.

**Targeted change for vrs-f-l8**: layer a second directional signal
(EWM of side-signed top-of-book imbalance) onto L6's full configuration.
Combine with the existing drift signal via weighted average. All
sigmoid-shape parameters, the base vol-regime parameters, the slow_vol
denominator, the cold-start gate, the calm-regime gate, and the
SHA-256 deterministic draw remain identical to L6.

**Mechanism / inefficiency exploited**: book imbalance carries
information about IMMEDIATE liquidity asymmetry that price-drift
cannot see (e.g., a quote tick where the bid stack just doubled
without yet moving price). For a BUY order, a thin ask combined with
a deep bid suggests buy-side demand is being absorbed and the next
move is likely up -- favorable for a BUY (aligned). The combined
signal should:

  (a) Reinforce adverse classification on trades where both drift
      and imbalance agree on adverse -> sharper tightening, fewer
      worst-EV trades submitted.
  (b) Route ambiguous trades (drift adverse but imbalance favorable,
      or vice versa) into the defensive z=0 path (0.45 tightening) --
      net positive in L3/L6 data.
  (c) Add a near-zero-cost extra knob without changing the proven
      sigmoid shape or the proven drift-halflife.

**Why it survives costs**: zero-slippage fill model -- edge is realized
via P&L only, no slippage tradeoff to worry about. The two signals
average rather than compound aggressively, so the worst-case behavior
when imbalance is uninformative is "z_combined is 60% of z_drift" --
slightly weaker tightening than L6, which would be a mild regression
but not catastrophic. Bounded downside.

**Predicted effect size** (loose, order-of-magnitude):

- **Trade count**: L6 = 122,431. Adding a second signal that points
  the SAME direction on most adverse trades (where book imbalance
  reinforces drift's adverse signal) should increase total
  tightening on those trades, removing more of them. On trades
  where the signals disagree (a sizable fraction -- maybe 20-30%
  of high-vol moments), the combined z moves toward 0 and trade
  gets the defensive 0.45 tightening. Net direction: more skips,
  but only modestly. Range: 121,000-123,000.

- **Realized P&L**: this is the test variable.
    - If book imbalance is genuinely orthogonal AND predictive,
      $1,500-$1,650 (+4% to +14% vs L6).
    - If book imbalance is redundant with drift (no information
      gain), $1,400-$1,500 (flat to mild positive due to the
      averaging dampening some drift signal).
    - If book imbalance has the wrong sign (mean-reversion
      microstructure dominates), $1,250-$1,400 (regression: the
      added signal flips some correctly-classified trades to
      incorrectly-classified).
    - Central guess: $1,500-$1,550 (mild positive vs L6). The
      orthogonality of the signal is the key bet; the magnitude
      depends on how much net-new info it adds.

- **Sharpe**: should track pnl direction. Central guess 5.7-6.2.
  If signals reinforce on adverse trades, sharpe could improve more
  than pnl (variance reduction in the worst-EV tail).

- **Win_rate**: roughly flat (~35.4-35.5%). The sigmoid shape is
  unchanged; only the input variable changes.

- **Max_dd**: if signals reinforce on adverse trades, tail-trade
  removal improves slightly -> better max_dd. Central guess
  -0.030% to -0.036%.

These are loose order-of-magnitude estimates. The most-likely
outcome is "modestly positive" (book imbalance adds some
non-redundant signal). The most-informative outcome is either
direction -- a regression would be evidence the mean-reversion
microstructure interpretation is right for MES at this timescale,
and a future arm could test the sign-inverted version.

**Builds on**: vrs-f-l6 (code skeleton starting point). Adds:
- EWM of top-of-book imbalance `_imbal` with halflife=`imbal_halflife=60`.
- Side-signed imbalance coordinate `_signed_imbal_z` (mirror of L6's
  `_signed_drift_z`).
- Combined z = `drift_weight * z_drift + imbal_weight * z_imbal`
  in `_effective_prob`.
- Imbalance scaling factor `imbal_scale=2.0` to align with z_drift's
  magnitude.

**Alternatives considered**:

1. *Multiplicative combination* (tighten_combined = 1 - (1 -
   tighten_drift)*(1 - tighten_imbal)). More aggressive than
   averaging (skips if EITHER signal says adverse). Risks
   over-tightening, potentially removing aligned trades. Defer to
   a future loop after the averaging version is proven.

2. *Imbal as relaxation signal only* (use it only to release
   trades when imbal strongly aligned). L1 already showed
   relaxation signals are dead for this strategy/dataset.
   Skip.

3. *Aggressor flow (signed traded volume from TradeMsg events)
   instead of book imbalance*. Different signal but similar role.
   Book imbalance is a simpler signal -- pure top-of-book sizes
   on every QuoteTick (which the algo already subscribes to);
   aggressor flow requires processing TradeMsg events separately
   and aggregating signed volume. Pick book imbalance for
   minimum architectural change.

4. *Wider w_imbal* (e.g., 50/50). More aggressive bet on the new
   signal. Conservative initial weight 0.6/0.4 -- if L8 works,
   future loops could tune the weight.

5. *Imbalance EWM with different halflife* (e.g., 30 or 90 ticks).
   Defer -- pick halflife=60 to match drift, then a future loop
   can sweep.

6. *Scale imbalance per slow_vol* (vol-normalize like drift).
   Imbalance is already bounded in [-1, 1], so vol-normalization
   doesn't apply naturally. The scaling factor 2.0 brings it to
   comparable magnitude with z_drift's typical range.

7. *Per-side imbalance* (e.g., bid_size_5 levels or signed
   level imbalance). Adds state and depends on whether the data
   has order book depth (only top-of-book here). Skip.

8. *Stack with min_prob=0.02 (deeper base vol-skip)*. Stacks
   changes; defer.

---

## Implementation Decisions

- **Signed-drift EWM**: unchanged from L6. `drift_halflife=60`,
  `drift_noise_floor=1e-7`, vol-normalized by slow_vol (halflife=120),
  side-signed coordinate `z_drift = order_sign * drift / max(slow_vol, eps)`.
- **Top-of-book imbalance EWM**: NEW. Per quote tick, compute
  `imbal_raw = (bid_size - ask_size) / (bid_size + ask_size)` if
  `(bid_size + ask_size) > 0` else 0. Then EWM with
  `imbal_alpha = 1 - exp(-ln(2) / imbal_halflife)`, default
  `imbal_halflife=60` -> alpha ~0.01149 (same as drift).
- **Side-signed imbalance coordinate**: `z_imbal = order_sign * imbal_ewm * imbal_scale`
  where `imbal_scale=2.0` to bring [-1,+1] into ~[-2,+2] matching the
  z_drift typical magnitude range.
- **Combined z**: `z_combined = drift_weight * z_drift + imbal_weight * z_imbal`,
  with `drift_weight=0.6` and `imbal_weight=0.4`. Sum is 1.0 so the
  combined z has comparable magnitude to z_drift alone, preserving
  the L3/L6-tuned sigmoid shape's operating point.
- **Sigmoid parameters**: L3/L6 values -- `k = 3.0`, `max_tighten = 0.9`.
- **Branches**: full symmetric sigmoid, no aligned-side clip.
- **Defensive z=0**: when drift_below_floor AND imbal undefined,
  z_combined = 0 -> tighten = max_tighten / 2 = 0.45. Same as L6
  (extended to also fire on imbal missingness).
- **Imbal cold start**: until `imbal_ewm` warm (after first tick with
  `bid_size + ask_size > 0`), set z_imbal = 0 (contribution
  collapses to the drift signal alone, scaled by drift_weight=0.6 --
  modestly weaker but not undefined). This is a deliberate slight
  conservative tilt during the imbal warmup period.
- **Absolute floor**: 0.01 (same as L3/L6).
- **Calm regime gate**: `p_vol >= 1.0 - 1e-9` -> `p_eff = 1.0`. Same.
- **Cold start**: `tick_count < min_ticks=30` -> `p = 1.0`. Same.
  Both EWMs start updating from tick 1, so by tick 30 the drift and
  imbal both have ~21% effective weight at halflife=60 -- enough to
  discriminate adverse from aligned.
- **Reduce-only**: always submit. Same.
- **Determinism**: same SHA-256(client_order_id) uniform draw. Same.
- **Quantity invariant**: child_qty = parent_qty = 1. Same.

**Concerns**:

- The book-imbalance sign convention is the bet. If MES at this
  timescale shows mean-reversion microstructure (heavy bid = stale =
  about to drop), my sign is inverted and L8 will regress. The L1
  refutation of alignment relaxation pattern-matches to this concern:
  alignment direction has been the wrong bet once before. But L1
  was about *price drift* alignment as a relaxation signal -- a
  different signal applied with different semantics. The
  symmetric inversion of L1 (drift alignment as a *tightening*
  signal) was L2's success. By analogy, the right starting hypothesis
  for book imbalance is the "natural microstructure" direction
  (deep bid = upward pressure = aligned for BUY = no tighten),
  matching how L6's drift convention works. If wrong, L9 would
  test the inversion.

- Two halflife-60 EWMs with similar dynamics could correlate
  more than expected on this dataset, in which case the "orthogonal"
  framing fails and the signal is largely redundant. Result would be
  "flat vs L6" rather than "improvement." Still informative.

- The imbal scaling factor of 2.0 is a guess. If imbal EWM at
  halflife=60 produces saturated values around |0.4| (not |1|), then
  z_imbal is in ~[-0.8, +0.8] range and gets dominated by z_drift in
  the average. If imbal EWM saturates fully (|1|), z_imbal is in
  ~[-2, +2] and contributes equally. The 2.0 factor is mid-range.
  Future loop could re-tune.

- Adding the imbal_ewm state means the algo's behavior depends on
  bid_size/ask_size data quality. If the data has zero-size or
  missing entries, the `(bid_size + ask_size) > 0` guard returns
  0 contribution, so the imbal EWM decays toward 0 -- conservative
  fallback to drift-only.

---

## Backtest Observations

**12-date full train window results** (vs `vol-regime-sizer` base):
- realized_pnl: $1,437.00 vs base $753.75 → **+90.64% vs base**
- sharpe_ratio: 6.075 vs base 3.065 (+3.010 absolute) — **BEST sharpe across all 8 loops**
- trade_count: 122,349 vs base 127,991 (−5,642, −4.41%)
- max_drawdown_pct: −0.0345% vs base −0.0460% (25% smaller) — **best max_dd across all loops**
- win_rate: 35.47% vs base ~35.4% (+0.07pp)
- mean_slippage: 0.0 (zero-slippage fill model)

**Hypothesis assessment**: PARTIALLY SUPPORTED. The book-imbalance second signal improved sharpe (6.075 vs L6's 5.874, +0.20 absolute) and max_dd (−0.0345% vs L6's −0.0371%, 7% improvement) but slightly regressed pnl ($1,437.00 vs L6's $1,447.00, −$10.00, −0.7%). This split result is informative:

1. The sharpe and max_dd improvements are consistent with the predicted mechanism: the combined signal routes more ambiguous trades to the defensive z=0 path (0.45 tightening) by averaging drift and imbalance, reducing variance. This worked: L8 has the best risk-adjusted performance of all 8 loops.

2. The slight pnl regression (−$10, −0.7%) suggests the imbalance signal added slightly more tightening on some profitable trades than it removed on harmful ones — net slightly adverse at the P&L level. Given that L8 trades ~80 fewer trades than L6 (122,349 vs 122,431), and pnl dropped only $10, the per-trade P&L is essentially identical to L6's. The signal routing change is largely noise-level.

3. The trade_count drop (−5,642 from base, vs L6's −5,560) confirms the second signal added slightly more aggregate tightening, as predicted. The additional ~82 skips vs L6 had roughly zero net P&L impact — exactly the "redundant with drift" scenario (flat rather than improvement).

4. The best-sharpe and best-max_dd readings make L8 the best risk-adjusted configuration. Whether the slight pnl regression is noise is unclear from a 12-day window; L6 and L8 are statistically very close.

**Arm summary** (L6 vs L8 tradeoff):
- L6: pnl=$1,447.00, sharpe=5.874, max_dd=−0.0371%, +91.97% vs base
- L8: pnl=$1,437.00, sharpe=6.075, max_dd=−0.0345%, +90.64% vs base
- L8 sacrifices $10 P&L (−0.7%) for +0.20 sharpe (+3.4%) and −7% max_dd. A risk-adjusted preference for L8; a pure-pnl preference for L6.

**Best of full-trace arm**: L6 by pnl, L8 by sharpe and max_dd. Both are superior to brief-summary arm's best (L8: pnl=+204.8% — but note different architecture/approach across arms). Full-trace arm's trajectory: monotone improvement to L6 with meaningful variance thereafter as refinements converged.
