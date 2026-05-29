# Algorithm Notes: afg-isl-g1l1 (island-1, generation 1, loop 1)

## Island lineage

- Island: island-1
- Base algo: aggressor-flow-gate (rolling signed aggressor flow over 10s, threshold 2.0 contracts)
- Cross-island input: NONE — this is generation 1, no migration reports exist yet. Hypothesis derives purely from base-algo observations.

## Hypothesis

**Mechanism**: Replace the base algo's single-window static-threshold gate with
a two-window "persistence + reversal" gate.

- Maintain the same trade-tick deque, but compute net signed aggressor flow over
  two windows simultaneously:
  - `short_flow`: net flow over the most recent `short_window_seconds` (default 3s).
  - `full_flow`: net flow over the full `window_seconds` (default 10s, matches base).
- Gating rule for opening orders:
  - **Skip a BUY** when `full_flow <= -full_threshold` AND `short_flow <= -short_threshold`
    (persistent adverse selling across both timescales).
  - **Skip a SELL** when `full_flow >= full_threshold` AND `short_flow >= short_threshold`
    (persistent adverse buying across both timescales).
  - **Reversal exception**: if full_flow is adverse but short_flow has flipped
    favorable by at least `reversal_threshold` contracts (e.g. BUY order:
    `full_flow <= -full_threshold` AND `short_flow >= reversal_threshold`),
    **submit** — the adverse pressure has measurably exhausted.
  - Otherwise submit (warm-up / neutral / partial adversity).
- Closing orders (reduce-only) always submit.
- After any skip: `_position_flat = True` (anti-cascade — base contract preserved).

**Inefficiency exploited**: Base NOTES.md documents that the single-window
threshold "holds back entries during adverse-flow periods, but those exact
moments sometimes offer the best fill prices (the market is being pushed to a
temporary extreme by aggressors -- the oracle signal that fire there can have
favorable arrival prices)." The base captures persistent adverse flow but
cannot distinguish "adverse and worsening" from "was adverse but now reversing."
The two-window structure quantifies that distinction: a recent flip of the
3s window from adverse to favorable is a real signal that the local imbalance
is unwinding, and entries at that moment are often the highest-IS opportunities
(arrival mid favorable, oracle still valid for the rest of the 30s horizon).

**Why it should survive costs**: We expect a modest decrease in skip rate
(some "reversing" entries that base skipped now submit). Net P&L should hold
or improve because:
1. The skipped trades remaining (both windows adverse) are higher-confidence
   adverse-flow rejects.
2. The newly-submitted reversal entries should be net positive — they fire at
   local price extremes after the adverse leg has rolled off.
3. is_weighted_bps (the IS regression flagged in base NOTES) should improve
   because we re-capture the favorable-arrival-price entries that base lost.

**Builds on**: aggressor-flow-gate (base for island-1). Direct structural
extension — same trade-tick signal source, same deque, same anti-cascade
contract; only the gating function changes.

**Alternatives considered (and not chosen for this loop)**:
- Volume-weighted flow normalization (divide by total volume): conflates
  thin and thick periods — defer.
- Trade-count gate (require N trades in window before any gate fires):
  warm-up handling is cleaner — defer.
- Trade-size adaptive threshold (scale threshold by recent avg trade size):
  adds parameter without clear theoretical edge — defer.
- Acceleration via slope/derivative: too noisy for a 3s short window with
  futures cadence — discrete short/full comparison is more stable.

## Implementation Decisions

- **Two windows from one deque**: a single `deque[(ts_event_ns, signed_vol)]`
  holds all trades; prune to full window. `short_flow` is computed by a
  separate linear pass over the deque filtering on the short cutoff (or
  maintained via a second running sum + cutoff index). For simplicity and
  correctness, recompute short_flow by iterating the deque from newest
  backward and summing until the short cutoff. Deque sizes are small at
  3-10s in futures (typically ~50-200 entries), so the O(N) scan per order
  is cheap and avoids the bookkeeping complexity of dual running sums.
- **Parameter defaults**:
  - `window_seconds = 10.0` (matches base).
  - `short_window_seconds = 3.0` (last 30% of base window — long enough to
    contain several prints at typical futures cadence, short enough to
    register a true regime flip).
  - `full_threshold = 2.0` (matches base flow_threshold — the base value
    is known to work).
  - `short_threshold = 1.0` (lower bar in the short window because volume
    is naturally smaller; require any meaningful short-window confirmation).
  - `reversal_threshold = 1.0` (equal magnitude to short_threshold but
    opposite sign — symmetric definition of "measurable reversal").
- **Quantity invariant**: never modify `order.quantity`. Only skip or submit.
- **No look-ahead**: prune using `order.ts_init` as the cutoff anchor; the
  deque is fed strictly by `on_trade_tick` callbacks in replay order.
- **Subscription**: subscribe to trade ticks AND quote ticks on first
  encounter (matches base).
- **Anti-cascade**: after any skip, `_position_flat = True`; the next open
  order submits unconditionally. Same invariant as base and all passing
  algorithms in this repo.

## Backtest Observations

**Train window**: 12 dates, 2026-03-08 .. 2026-03-20 (full configured train set).

**Raw aggregate numbers (afg-isl-g1l1 vs aggressor-flow-gate base, both vs `simple` baseline)**:

| metric            | afg-isl-g1l1 | aggressor-flow-gate (base) | vs_base |
|-------------------|--------------|----------------------------|---------|
| realized_pnl      | 714.00       | 1255.50                    | -43.13% |
| unrealized_pnl    | 0.00         | 0.00                       |  n/a    |
| sharpe_ratio (12d)| 3.0568       | 5.5944                     | -45.36% |
| max_drawdown_pct  | -0.04135     | -0.03325                   | worse   |
| win_rate          | 0.3507       | 0.3549                     | -1.2pp  |
| trade_count       | 115099       | 107198                     | +7.37%  |
| mean_slippage     | 0.0          | 0.0                        |  0.0%   |
| is_weighted_bps   | 0.0507       | 0.0472                     | +7.4%   |
| vs_baseline_pnl%  | +357.69%     | +704.81%                   | n/a     |
| vs_baseline_is_bps| +30.44%      | +21.50%                    | n/a     |

(`mean_slippage = 0.0` on both sides reflects pure marketable-order arrival-mid
slippage being zero under this strategy + symbol — not a measurement bug;
identical behavior is documented for the base. vs_base slippage % is therefore
0.0% by definition, no information content.)

**Trade count**: 115,099 — well above the 30-trade reliability threshold. Sharpe
and win-rate numbers are trustworthy. Honesty note: this is the algo running 30s
oracle horizons; raw trade_count overstates "decisions" since the strategy
generates many more signals than the base because of the slightly looser
gate (115k vs 107k, +7.4%).

**Headline interpretation**: The two-window persistence+reversal gate is
**clearly worse than the base** on this train window. PnL is **-43% vs base**,
Sharpe is **-45% vs base**, and the IS regression went the wrong way
(`is_weighted_bps` rose from 0.0472 to 0.0507, i.e. execution got *more*
expensive in arrival-mid bps terms). Hypothesis is **falsified**.

**Mechanistic diagnosis** (per Step 8 honesty: explain, do not hide):

1. **More trades, less PnL** — the gate let in ~7.4% more entries but realized
   ~43% less PnL. That means the *marginal* trades added by relaxing the gate
   (the "reversal exception" cases where short_flow flipped favorable while
   full_flow was still adverse) are net P&L destroyers, not the IS-favorable
   entries the hypothesis predicted. The "persistent adverse" gate by itself
   was leaving in nothing important; the reversal exception was the entire
   structural change and it failed.

2. **IS regression** — `is_weighted_bps` rose from 0.0472 to 0.0507 (+7.4%).
   The reversal-exception entries are firing at moments where short_flow has
   just flipped favorable but the actual arrival mid is *still* unfavorable
   — the deque is summarizing trade aggressor direction, not actual price
   level. A flow flip does not equal a price reversal. We over-indexed on
   the flow signal as a proxy for price behavior.

3. **Win rate barely moved** (-1.2pp) but PnL halved — the loser trades
   added by the relaxed gate are *larger* losers than typical, suggesting
   they fire at moments of sustained adverse pressure that the base
   correctly skipped. The 3s window is too short to confirm a real regime
   change; 3s of bouncing flow in a 30s sustained sell-off is noise, not
   signal.

4. **Persistence-only gate (full + short same-sign)** likely added almost
   nothing on top of the base. The two-window-AND requirement is stricter
   than the base single-window gate, so it *skips fewer* adverse trades;
   combined with the reversal exception *also* relaxing the gate, the
   net effect is "fewer adverse skips" in every direction.

**Implication for island-1 loop 2**: The reversal-exception mechanism is the
critical failure — don't repeat it without a price-based confirmation (e.g.,
require the mid price to have moved at least X ticks in the favorable
direction during the short window, not just trade-flow direction). The
two-window AND gate also tightened things in the wrong direction; if we want
to extend the base, start by *strengthening* the gate (e.g., requiring a
minimum trade count in the window, or weighting by trade size) rather than
loosening it.

**Note re: positive vs_baseline_pnl_pct**: afg-isl-g1l1 still beats the
`simple` baseline by +357.7%, but that's not the gate we're scored against —
island lineage is judged vs the island's *base_algo* (aggressor-flow-gate),
which itself beats simple by +704.8%. The island regressed from its base.
