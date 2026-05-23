# Algorithm Notes: position-tier-imbalance-cap2-gate

## Hypothesis

**Mechanism**: Structural relaxation of the position-tier gate from `position_cap=1`
to `position_cap=2`, while keeping the EMA-smoothed top-of-book imbalance gate
from iter-2 (`position-tier-imbalance-ema-gate`) verbatim. Reduce-only orders
still execute immediately (intraday_flat compliance). The change is one knob:
the maximum absolute net position at which a new open-leg order is still
allowed is raised from 1 contract to 2 contracts.

**Inefficiency exploited**: Iters 1-3 of the position-tier-gate family
established empirically that the `position_cap=1` gate dominates the result
regardless of which upstream signal feeds the imbalance/flow filter (single-tick
imbalance, EMA-smoothed imbalance, and OFI all produce broadly similar pnl
deltas within a noise floor when stacked on top of `cap=1`). This is consistent
with the cap binding the netting-OMS doubled-up cascade: with the cap at 1, the
exec algo never lets the engine accumulate beyond one contract net, so the
cascading-add path (which iter-1's notes flagged as the primary source of the
$4262 baseline-of-baselines result) is closed off. The natural follow-up
question — and the one this iteration tests — is whether `cap=1` is **at the
optimum** or merely **above the bar**. If cap=2 is also restrictive enough to
block the cascade but lets the algo profitably accumulate on legitimately
strong, sustained oracle signals, pnl should rise. If cap=1 is the actual
sweet spot, pnl should fall (or stay flat) and we learn that the cap itself is
the binding mechanism rather than a sub-optimal proxy for one.

**Why it survives costs**: Slippage is 0 by construction in this fill model
(see `research/NOTES.md` 2026-04-30), so there is no cost wedge. The
mechanism is pure: more or fewer open-leg fills get through the gate, and
the realized-P&L delta tells us whether the additional position-2 entries
are systematically winning or losing trades.

**Builds on**: `position-tier-imbalance-ema-gate` (iter-2, current best in
this family at pnl=$4503.25, sharpe=20.79 across 11 of 12 train dates). Only
the `position_cap` config value is changed (1 → 2). EMA params
(`ema_alpha=0.30`, `skip_threshold=0.40`, `min_total_size=2.0`) and the
reduce-only fast-path are copied verbatim from iter-2.

**Alternatives considered**:
- Time-of-day filter — clean structural axis, but adds a fitted window
  (start/end-of-session minutes) that risks overfitting to the 12-date train
  window without an OOS hedge. Holding for a future iteration if cap=2 also
  underperforms.
- Volatility-regime sizing — would change effective parent quantity and
  violates the quantity invariant if implemented as size-up. Implemented as
  size-down (skip) it collapses to "another adverse-condition filter," which
  the iter-3 OFI result suggests does not lift this stack.
- Position cap = 3 — too aggressive as a first relaxation step; cap=2 is the
  smallest change that tests the hypothesis at all.

---

## Implementation Decisions

- Direct copy of `position-tier-imbalance-ema-gate/execution_algorithm.py` with
  only the default `position_cap=1` → `position_cap=2` change (in the config
  dataclass AND the factory default). EMA recursion, thin-book guard, and
  reduce-only fast-path are unchanged byte-for-byte.
- Class names renamed to `PositionTierImbalanceCap2Gate*` so the registry
  resolution is unambiguous; behaviour is otherwise identical to iter-2 at the
  config level except for the cap.
- The `_current_net_qty` helper returns the absolute (sum of signed quantities
  in the netting OMS) — unchanged from iter-2. Comparison is `>=` cap, so at
  cap=2 a fill that takes net_qty to 2 will block subsequent SAME-side opens
  but will not block a counter-side open (which would reduce position).
- Reduce-only orders bypass both gates, same as iter-2.

**Concerns**:
- Honest uncertainty: I do not have a strong prior on whether cap=2 will help
  or hurt. The iter-1 PASS on cap=1 against the no-cap baseline (pnl=$43.25)
  is a near-100x lift; whether the residual room above cap=1 contains
  profitable signal or net adverse-cascade trades is exactly what this test
  resolves.
- The OOM hazard on 2026-03-19 documented in `research/NOTES.md` (2026-05-23)
  is expected to reproduce here too — this algo also calls
  `subscribe_quote_ticks`. Iteration will aggregate over the same 11 of 12
  train dates as iters 1, 2, 3 for an apples-to-apples comparison.
- No look-ahead concerns introduced — the EMA mechanic is unchanged from
  iter-2 (incremental update in `on_quote_tick`, read at `on_order` time
  reflects only past quotes).

---

## Backtest Observations

**Aggregate (11 of 12 train dates; 2026-03-19 EXCLUDED — reproduces the
`subscribe_quote_ticks` 8 GiB Rust OOM hazard documented at
`research/NOTES.md` 2026-05-23, as expected for this algo family)**:
- realized_pnl = $2686.50
- trade_count = 86,259 (HIGH; not low-trade-count flagged)
- win_rate = 37.77%
- cross-day sharpe (N=11) = 10.89
- max_drawdown_pct = -3.57%
- mean_slippage = 0.0 (zero-cost fill model; not informative)

**Vs baseline (simple, same 11 dates aggregate)**:
- pnl_delta = +6111.6% ($43.25 baseline) — well above +5.0% gate. PASS vs baseline.
- trade_count_delta = -22.6% (86259 vs 111489)
- win_rate_delta = +2.75pp

**Vs prior best in family (iter-2 `position-tier-imbalance-ema-gate`)** —
the structural-comparison axis this iteration was designed to probe:
- pnl_delta = -40.3% ($2686.50 vs $4503.25) — STRUCTURAL REGRESSION
- sharpe_delta = -9.90 (10.89 vs 20.79) — STRUCTURAL REGRESSION
- win_rate_delta = -1.52pp (37.77% vs 39.29%)
- trade_count_delta = +38.6% (86259 vs 62220) — cap=2 admits 24k more entries
- max_drawdown_pct_delta = -2.36pp (-3.57% vs -1.21%) — worse drawdown
- All refinement-vs-iter-2 axes in `config.yaml -> refinement.targets`
  MISSED: `min_sharpe_delta=+0.5` missed; `min_pnl_delta_pct=+2.0` missed;
  `min_winrate_delta_pp=+2.0` missed; `min_mdd_delta_pp=-1.0` missed.

**What drove improvement (vs baseline)**: Same mechanism as iter-1/2/3 —
the positional gate still blocks the doubled-up netting-OMS cascade
sufficiently to lift pnl ~60x vs the baseline, and the inherited EMA
imbalance filter still removes some adverse-direction entries (win-rate
delta vs baseline is +2.75pp). PASS-vs-baseline is preserved even with
the cap relaxed by one contract.

**What underperformed (vs iter-2)**: Relaxing the position cap from 1 to
2 strictly hurt pnl, sharpe, win-rate, and drawdown across the aggregate.
The additional ~24k entries that cap=2 admits (vs cap=1) are net adverse:
their win rate is materially below the cap=1 stack's win rate (the
aggregate win rate drops by 1.52pp despite the EMA filter being
identical), and the per-date pnl deltas swing both ways — date 20260311
even goes negative-vs-baseline (-10.23%) where iter-2 was positive. The
per-date pattern is consistent: cap=2 hurts most on quieter,
choppier dates (early train window) and recovers some on high-flow dates
(late train window: 20260317/18/20 all PASS-vs-baseline by >+225%, but
still underperform what iter-2 would have achieved on those dates).

**Hypothesis verdict**: CONTRADICTED — the data resolves the open
question from iter-3's notes ("is cap=1 strictly binding or arbitrary?")
in favor of cap=1 being the actual structural optimum, not just a
sufficient guard against the cascade. Relaxing the cap admits net-losing
trades; cap=1 is the binding mechanism, not a proxy for one. The
positive-information takeaway is significant: future iterations should
NOT explore cap relaxation further, and the +9945% (iter-1) to +10312%
(iter-2) regime is at or very near the local optimum for the
positional-gate axis with this baseline and signal stack.

**Suggested next attempt**: Structural directions still untested in this
family (in priority order):
1. **Time-of-day filter** on opens — orthogonal to all current gates;
   tests whether oracle skill is non-stationary intraday (open/close
   noise periods most likely candidates for skipping).
2. **Volatility-regime open-skip** — skip opens when realized vol over a
   short window exceeds a threshold (oracle is most likely to fade in
   high-vol regimes per general microstructure intuition).
3. **Reduce-only delayed-execution** — currently reduce-only orders fire
   immediately; splitting them across a few seconds might capture better
   exit prices on dates where intraday-flat squaring is large. Risk:
   miss the intended exit moment entirely.
The structural takeaway from iters 1-4 of this family is converging:
position_cap=1 + ANY reasonable adverse-condition open filter is at or
near the local optimum (+4344 to +4503 pnl band on 11 dates), and the
remaining improvement gradient is on a DIFFERENT axis than gate
threshold/signal class/cap size.

**Honesty**: PASS-vs-baseline does NOT mean this iteration improves the
research line. The honest framing is "PASS vs baseline, structural
REGRESSION vs iter-2." Do not snapshot this algorithm as an improvement
over iter-2 — its value is the negative-result information that
constrains future exploration. Trade counts HIGH (86k+), not
low-trade-count flagged. Cross-day sharpe of 10.89 on N=11 carries the
standard small-N caveat (~0.4 unit standard error per OBJECTIVE.md §8).

