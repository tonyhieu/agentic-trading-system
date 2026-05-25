# Algorithm Notes: sip-vrs-l4

## Hypothesis

**One plausible weakness of vol-regime-sizer (the base algo)**: it uses
*symmetric* volatility — the EWM of `|delta_mid|` — and so cannot
distinguish a *trending* high-vol regime from a *choppy* high-vol regime.
Both regimes deliver the same `vol_ratio` and therefore the same
submission-probability cut. But for a 30s-horizon directional oracle,
these regimes have very different execution quality:

- *Choppy* (mean-reverting bursts): vol high, signed price drift small.
  The oracle's directional signal often catches the wrong leg of the
  oscillation — adverse selection. Skipping is correct.
- *Trending* (unidirectional moves): vol high, signed price drift large.
  The oracle's 30s-forward signal is more reliable here. Skipping forgoes
  alpha.

The parent's gate over-skips trending regimes by lumping them with chop.

**One concrete modification**: add a *trendiness multiplier* to the
submission probability. Trendiness is the directional ratio of recent
mid-changes over a fixed rolling window:

    T = |sum(delta_mid over window)| / (sum(|delta_mid| over window) + eps)
    p_vol = parent vol-regime probability (unchanged)
    p     = max(min_prob, T + (1 - T) * p_vol)

`T = 0` (pure chop, signed deltas cancel) gives exactly the parent's
behavior. `T = 1` (one-signed window) re-admits the order at full
probability. Mixed regimes interpolate linearly.

The window is a deque of length `trend_window = 40` ticks — two parent
fast-EWM half-lives, so the window matches the time scale on which
`fast_vol` reacts. The trendiness signal is independent of the vol level
(it's a normalized ratio), so it does not double-count what the vol gate
already measures.

**Why this is one knob, not many**: the only change is a multiplicative
re-admit on top of the parent's existing skip logic. Parent parameters
(fast/slow halflife, sensitivity, min_prob, min_ticks, max_vol_ratio) are
all inherited verbatim. The single new knob `trend_window=40` is
principled: it matches the fast-EWM time scale that already defines what
"recent" means in this algorithm.

**Predicted direction vs vol-regime-sizer (the base)**:
- realized_pnl: ↑ — trending high-vol regimes (currently skipped) on
  net carry oracle-signal alpha, so re-admitting them adds P&L.
- mean_slippage: unchanged — still top-of-book-only, never walks the book.
- trade_count: ↑ slightly — fewer skips on trending regimes.
- sharpe_ratio: ambiguous — more trades increase variance, but each
  re-admitted trade should be net positive in expectation. Likely flat-to-up.
- win_rate: ambiguous — adds participation in regimes where the oracle
  signal is more reliable; net effect depends on how strongly trendiness
  predicts oracle accuracy in this train window.

**Constraint compliance**:
- Quantity invariant: child_qty = parent_qty = 1 — never inflates.
- Top-of-book only: untouched — the gate decides submit/skip; the engine
  still routes at top-of-book.
- Participation cap: untouched — orders that submit go through the same
  routing path as the parent.
- Intraday-flat: reduce-only orders bypass the gate (submitted
  unconditionally), same as the parent.
