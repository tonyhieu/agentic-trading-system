# Algorithm Notes: depth-participation-sizer

## Hypothesis

**Mechanism**: Scale open-leg order submission probability as a continuous
function of the current same-side top-of-book quantity at the moment the
signal fires. When the book is deep on the relevant side, use a larger
participation probability (approaching 1.0). When the book is thin, shrink
probability proportionally to preserve fill quality and avoid outsized impact.

Concretely:
  - For BUY  orders: conditioning quantity = ask_size (same-side = supply that fills us)
  - For SELL orders: conditioning quantity = bid_size (same-side = demand that absorbs us)
  - p_submit = clip(1.0, (q_same_side / depth_scale)^alpha, min_prob)
  - depth_scale: the quantity level at which p=1.0 (fully participate)
  - alpha: elasticity; alpha=1.0 is linear, alpha<1 is concave (saturates quickly)
  - min_prob: floor so no signal is permanently locked out

Reduce-only / position-closing orders execute at full probability always —
intraday_flat compliance.

**Inefficiency exploited**: The simple baseline executes every signal
unconditionally regardless of available liquidity. When the same-side book
is thin, a 1-contract order represents a large fraction of available depth,
leading to worse expected fill quality (adverse selection and potential
price impact). The oracle signal quality is not correlated with current
liquidity depth, so selectively participating when liquidity is abundant
filters execution quality without filtering signal quality.

**Why it survives costs**: The conditioning axis (same-side depth) is
independent of signal direction. By submitting only in high-liquidity
moments, we fill at better prices (lower implementation shortfall) while
preserving most profitable signals — deep books are frequent enough that
trade count doesn't collapse. The expected fill quality improvement
outweighs the reduction in participation.

**Builds on**: none — original hypothesis. Conditioning axis (current
top-of-book same-side quantity) is distinct from all prior algorithms:
  - streak-spread-tight: loss streak + spread width
  - ob-imbalance-gate: bid/ask size ratio (relative imbalance)
  - vol-regime-sizer: mid-price realized volatility ratio
  - microprice-divergence-gate: microprice vs mid divergence
  - passive-aggressive-ladder: passive limit + timeout

This is the first algorithm to condition solely on *absolute* same-side
depth magnitude as the execution quality proxy.

**Alternatives considered**:
  - Two-sided total depth (bid_size + ask_size): mixes demand and supply
    signals; same-side is more directly relevant to fill cost
  - Spread-adjusted depth: spread already captured by streak-spread-tight
    and is correlated with depth; adding spread would compound conditioning
  - EWM-smoothed depth: would introduce look-ahead if computed over future
    ticks; using only the current tick's depth is clean

---

## Implementation Decisions

- **Same-side definition**: For BUY orders, the "same side" is the ASK
  because ask_size is what gets consumed when we buy. For SELL orders, the
  "same side" is the BID because bid_size absorbs our sell. This represents
  the available counterparty liquidity at the best price.

- **depth_scale default = 10**: From prior runs, typical top-of-book sizes
  in MESM6 range from ~1-50 contracts. depth_scale=10 means we approach
  full participation at ~10+ contracts available. This is conservative;
  if the book averages 20 contracts we'd typically be near p=1.0.

- **alpha = 0.5**: Concave response function — book depth increases are
  most valuable when going from thin to moderate; marginal value of extra
  depth diminishes. This prevents over-aggressive skipping on small books.

- **min_prob = 0.1**: Even at zero depth (extreme case), 10% of orders
  execute. This prevents complete signal blackout on thin days and satisfies
  the position-entry guarantee.

- **Deterministic draw**: Uses SHA-256 of client_order_id for reproducibility
  (same approach as vol-regime-sizer). This is observable-at-order-time
  and free of look-ahead bias.

- **Quantity invariant**: At most 1 contract per parent 1-contract order.
  No quantity inflation; only probabilistic skip or full submission.

- **Subscribe-on-demand**: quotes are subscribed when the first order for
  an instrument arrives — same pattern as ob-imbalance-gate.

**Concerns**:
  - The mapping q_same_side -> p_submit uses current top-of-book size from
    the most recent quote tick. This is tick-synchronous (the fill engine
    uses current state at signal fire time), so no look-ahead bias.
  - depth_scale and alpha are fixed. If book depth varies significantly
    across dates, a fixed scale may be suboptimal. However, fixing these
    prevents overfitting to specific training dates.
  - alpha=0.5 with depth_scale=10: at q=1, p=sqrt(1/10)=0.316. At q=5,
    p=sqrt(5/10)=0.707. At q=10+, p=1.0. This seems reasonable for
    1-contract oracle orders relative to typical MES book depth.

---

## Backtest Observations

Results (12-date train window 2026-03-08 to 2026-03-20, same as prior algos;
20260314 and 20260321 missing data as in prior iterations):

  realized_pnl:         $1,962.00 (algo) vs $1,984.00 (baseline)
  vs_baseline_pnl_pct:  -1.11%  [gate requires >= +5.0%]
  sharpe_ratio:         1.099  vs 0.909 (+20.97%)
  max_drawdown_pct:     -0.0439% vs -0.0377% (slightly worse)
  win_rate:             35.14% vs 35.57% (-0.43pp)
  trade_count:          119,549 vs 132,536 (-9.80% skipped)
  mean_slippage:        0.0 (both, zero fill-cost model)
  is_weighted_bps:      0.0332 vs 0.0375 (-11.4% better IS)

**What drove improvement**: The IS bps improved meaningfully (-11.4%): when
the book was deep, orders were submitted (full p) and filled well. The Sharpe
improvement (+21%) is real and reflects lower variance from skipping thin-book
entries. On volatility-driven days like 20260312 and 20260313 where book depth
correlated with signal quality, the algo turned losing days into smaller losses.

**What underperformed**: Net P&L fell short of baseline (-1.11%). The oracle's
profitability is largely uncorrelated with book depth in this dataset. Skipping
thin-book orders removed both losing AND winning trades equally, so the skip
rate (~10%) reduced gross P&L without a proportional reduction in losses. On
9 of 12 dates the algo trailed the baseline in absolute P&L terms. The
depth_scale=10 / alpha=0.5 parameters may have been too aggressive — at mean
book depth of ~15-20 contracts, p is already near 1.0 for most orders, meaning
the algorithm barely changed participation for the majority of signals while
still skipping on the thin-book tails. The marginal benefit of the hypothesis
doesn't materialize strongly enough.

**Hypothesis verdict**: FAIL (delta_pnl_pct = -1.11%, far below +5.0% gate).
The hypothesis that conditioning on same-side absolute depth improves P&L is
NOT supported. While IS improved slightly, the net P&L effect is negative. The
mechanism is theoretically sound but the effect size is too small to matter in
this oracle strategy setting where signal quality dominates execution timing.

**Suggested next attempt**: If pursuing depth-based conditioning, consider
combining it with an existing passing gating algorithm (e.g., use depth as
a secondary filter only when ob-imbalance gate is already active), or use
depth as a continuous multiplier on the imbalance threshold rather than as
the primary conditioning axis. Alternatively, explore a dynamic depth_scale
calibrated per-session based on the rolling median same-side depth, so the
scaling function uses relative rather than absolute depth as the signal.
