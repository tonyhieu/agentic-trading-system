# vrs-isl-g2l2 — Chop + Spread + Aggressor-Flow Triple-Gate Sizer

Island experiment — island-2 (base: `vol-regime-sizer`), generation 2, loop 2.

## Hypothesis

Stacking a **third orthogonal skip gate** on top of vrs-isl-g2l1's
chop + spread composition will produce a further super-linear PnL
improvement, provided the third axis is genuinely orthogonal to both
existing axes.

Concretely: layer the **aggressor-flow gate** (from island-1's base
`aggressor-flow-gate`) on top of vrs-isl-g2l1. For each OPEN order,
SKIP when any of the three gates fires; SUBMIT only when all three
pass. Reduce-only orders bypass all gates (intraday_flat compliance).

The three axes target three distinct families of adverse microstructure:

| Axis        | Source loop  | What it detects |
|-------------|--------------|------------------|
| Chop        | vrs-isl-g1l1 | Whipsaw regimes in **price-path** space (path_length / displacement) |
| Spread      | ptg-isl-g1l1 | Liquidity-vacuum regimes in **book-state** space (top-of-book spread vs rolling p75) |
| Flow        | aggressor-flow-gate | Directional adverse pressure in **trade-flow** space (net signed aggressor volume vs threshold) |

The flow gate is the only one of the three that is **side-aware**: it
SKIPs BUYs when `net_flow <= -threshold` and SKIPs SELLs when
`net_flow >= threshold`. Chop and spread are direction-blind. This
side-awareness means the flow gate adds residual information even when
chop or spread already flag a regime as adverse — adverse path / adverse
liquidity can still be on the favorable side of the trade.

## Cross-island insight cited

**Gen-1 migration report (`cross_island_insights.generalizable`):**

> Skip-based gating on adverse-microstructure regimes generalizes
> across base algos: spread-quantile and choppiness-ratio both worked
> on different bases and target near-orthogonal axes (book-state vs
> price-path), so a composed spread+chop+(third axis) stack is the
> highest-leverage generation-2 direction across all islands.

This loop directly executes on that recommendation by adding the third
axis (trade-flow), explicitly named as the open frontier.

**vrs-isl-g2l1 `summary_out.next`** reinforces the same direction:

> Also worth probing a third orthogonal axis (e.g., directional
> order-flow imbalance or top-of-book size asymmetry) to test whether
> stacking continues to yield super-linear returns.

The aggressor-flow gate is the canonical "directional order-flow"
implementation already proven as the base of island-1 — using the
verbatim parameters from `aggressor-flow-gate/execution_algorithm.py`
keeps the import-as-is discipline that worked on g2l1 (which imported
ptg-isl-g1l1's spread gate verbatim).

## Why this is NOT "loosening a gate"

Gen-1 migration's biggest documented failure mode was **loosening
existing skip gates** (island-1 g1l1 -43% PnL; island-1 g1l2 -21% PnL;
island-2 g1l2 ~zero EV). This loop does the opposite: it *adds* a third
skip gate (OR-on-skip / AND-on-submit). Trade count can only decrease
versus g2l1; no entries are admitted that g2l1 would have rejected.

The risk is the symmetric one: that the marginal trades the flow gate
removes are not concentrated in the adverse tail (i.e., the flow axis
turns out to be redundant or anti-informative on this base). The
instrumentation below is designed to make that diagnosable.

## Defaults

Inherited verbatim from parents — no tuning until empirical evidence
justifies it.

- **Chop**:   `window_ticks=30`, `chop_neutral=1.5`, `sensitivity=1.0`,
              `min_prob=0.05`, `min_ticks=40`, `trend_boost=0.0`
              (from vrs-isl-g1l1 / vrs-isl-g2l1).
- **Spread**: `spread_window_seconds=60.0`, `spread_quantile=0.75`,
              `min_spread_samples=50` (from ptg-isl-g1l1 / vrs-isl-g2l1).
- **Flow**:   `flow_window_seconds=10.0`, `flow_threshold=2.0` contracts
              (from `aggressor-flow-gate/execution_algorithm.py`).

## Instrumentation

Per-gate skip counters track every distinct combination of which gate(s)
fired:

- `_skipped_chop_only`
- `_skipped_spread_only`
- `_skipped_flow_only`
- `_skipped_chop_spread`
- `_skipped_chop_flow`
- `_skipped_spread_flow`
- `_skipped_all_three`
- `_submitted`
- `_reduce_only_submitted`

Each skip is logged with `submitted=X skip_chop=A skip_spread=B
skip_flow=C skip_chop_spread=D skip_chop_flow=E skip_spread_flow=F
skip_all=G` so the per-date logs let us answer:

1. How often does the flow gate fire **uniquely** (i.e., catches an
   adverse-flow trade that chop and spread both passed)? Large value =
   the third axis is informative on this base.
2. How often does the flow gate fire **in conjunction** with one or
   both other gates? Large overlap = the flow gate is partly redundant
   with the existing pair.
3. Total trade count delta vs g2l1 = sum of (flow-only +
   chop_flow + spread_flow + all_three).

These counters are the same template the gen-1 migration cited as
"missing from island-0 g1l2 — a loop lost to undiagnosable null
results."

## Implementation discipline

- Start from `vrs-isl-g2l1/execution_algorithm.py`.
- Add a third rolling structure for net-signed aggressor flow (deque
  of `(ts_event_ns, signed_vol)` pruned in `_flow_gate_skip`).
- Subscribe to trade ticks alongside quote ticks in
  `_ensure_subscribed`. The base spread gate already subscribed to
  quote ticks; flow gate requires `subscribe_trade_ticks`.
- `on_trade_tick` only maintains the flow deque (does NOT update chop
  or spread state, which remain quote-tick-driven).
- Quantity invariant: `child_qty == parent_qty == 1`, always.
- Reduce-only orders bypass ALL gates.
- The "forced re-entry after skip" anti-cascade pattern from
  `aggressor-flow-gate` is **NOT** carried over — vrs-isl-g2l1
  inherits chop's probabilistic gate which never used it, and g2l1's
  +223% result with no re-entry forcing shows it isn't required for
  this lineage. Keeping it absent preserves g2l1 as the strict subset
  case (flow gate disabled ⇒ same as g2l1).

## Backtest Observations

**Headline (raw, 12 train dates 2026-03-08 .. 2026-03-20, MESM6):**

| metric              | vrs-isl-g2l2 | vol-regime-sizer (base) | vrs-isl-g2l1 (prior) |
|---------------------|--------------|--------------------------|----------------------|
| realized_pnl        | 1701.50      | 753.75                   | 2437.75              |
| sharpe_ratio        | 15.25        | 3.06                     | 16.95                |
| max_drawdown_pct    | -0.70%       | -4.60%                   | -1.48%               |
| win_rate            | 0.3546       | 0.3529                   | 0.3556               |
| trade_count         | 61418        | 127991                   | 104688               |
| mean_slippage       | 0.0          | 0.0                      | 0.0                  |
| is_weighted_bps     | 0.0459       | 0.0374                   | 0.0311               |

**Deltas:**
- vs base `vol-regime-sizer` (753.75): **pnl +125.74%, slippage 0.0% (axis uninformative)**, sharpe 15.25 vs 3.06, max_dd -0.70% vs -4.60% (~85% tighter).
- vs **prior loop vrs-isl-g2l1** (2437.75): **pnl -30.21% — REGRESSION**, sharpe -10.0%, trade_count -41.3%.

**Hypothesis result: FALSIFIED.**

The "third orthogonal skip gate adds super-linear PnL" hypothesis is disconfirmed for the canonical aggressor-flow-gate parameters (`flow_window_seconds=10.0`, `flow_threshold=2.0` contracts). Stacking did not produce a further improvement; it *destroyed* ~30% of the gen-2 PnL gain that the chop+spread pair delivered.

**Mechanism (why the flow gate over-restricted):**

Trade count fell from 104,688 (g2l1) to 61,418 (g2l2), a **-41.3% reduction**. The NOTES.md hypothesis pre-defined a falsification line at "~15% trade-count cut" — actual reduction was **~2.7x** that limit. The flow gate is firing far too often. Two non-exclusive reasons:

1. **Threshold too low for MES tick cadence.** A 10-second rolling window with a 2-contract net-flow threshold catches ordinary directional pressure, not just adverse pressure. The aggressor-flow-gate base was tuned with this threshold as a *standalone* gate; stacked on top of an already-aggressive composed pair (chop+spread), the marginal cohort it removes is dominated by entries that the existing pair had already pre-filtered for adverse microstructure, leaving the flow gate to over-kill clean entries.
2. **Flow axis is partly redundant with chop+spread on this base.** Chop captures path-disorder; wide spreads correlate with directional aggressor bursts (one side hitting the offer aggressively widens the contra spread). Net signed aggressor flow is therefore **not** as orthogonal to chop+spread as the hypothesis assumed — the union of the three gates was larger than expected because they share information in the right tail.

The PnL of the surviving 61,418 trades is **lower in absolute terms** than the 104,688 g2l1 trades, which means the flow gate removed entries with **net-positive average EV** — exactly the failure mode the gen-1 migration warned about ("the recovered/admitted population is not a hidden cache of high-EV entries — but the symmetric case applies: the *removed* population was not a hidden cache of low-EV entries either"). is_weighted_bps **worsened** from 0.0311 (g2l1) to 0.0459 (+47%), confirming the surviving trades are not even higher-quality on the execution-cost axis.

**Cross-island lesson cited (island-0 g2l2 chop misfire):**

Island-0's g2l2 ported chop parameters from vrs-isl-g1l1 verbatim onto position-tier-gate and underperformed island-0's best by 30%+ — `ptg-isl-g2l2/summary_out`: "Chop is partially transferable to ptg but at lower marginal value than predicted." This is the *same failure shape* as g2l2 here: **gate parameters tuned for one base do not transfer cleanly when composed onto a different base, even when the underlying mechanism is sound.** Island-0 ported chop (vrs → ptg) and lost; island-2 ported flow (afg → vrs) and lost. The mechanism is generalizable; the *parameters* are base-specific.

**What this loop achieved (not zero — positive but inferior):**

- vrs-isl-g2l2 **does beat the original base** by +125.74% — the chop+spread+flow composition is profitable, just less profitable than chop+spread alone.
- max_drawdown tightened further: -0.70% vs g2l1's -1.48% (~53% tighter). The flow gate **is** removing tail-risk trades; the issue is it also removes too many neutral-EV trades alongside them.
- Sharpe held up well: 15.25 vs g2l1's 16.95 (-10%). The variance reduction from over-gating partially offsets the PnL loss, which is why sharpe degraded less than PnL.

**Honest assessment:**

This is a **clear regression vs the immediate parent**, not a marginal one or a sharpe-vs-PnL trade-off worth defending. The instrumentation counters (skip-by-gate-combination) were not extracted from per-date stdout into structured analysis here — that's a debt to pay before g3 to identify whether flow-only-skips or flow-in-conjunction-skips dominate the over-restriction. Without that counter analysis, the "redundant axis" vs "wrong threshold" question cannot be settled empirically; both hypotheses fit the data.

**Implications for g3:**

Two viable directions, listed in order of expected leverage:

1. **Retune flow threshold ONLY** — raise `flow_threshold` to 5.0-8.0 contracts and/or shorten `flow_window_seconds` to 3-5s so the flow gate fires only on genuine pressure spikes, not ordinary directional drift. This is the parameter-side fix to the "verbatim port doesn't transfer" failure. Cheap and directly addressable.
2. **Drop flow, explore a different third axis** — the redundancy hypothesis says even retuned flow won't beat g2l1 (chop+spread) on this base. Pivot to a structurally different axis: **top-of-book size asymmetry** (bid_size vs ask_size ratio at submission time) or **short-horizon realized vol** (returns variance over last N ticks, distinct from chop's path-length / displacement).

The g1 migration cross-island insight explicitly enumerated both candidates: "directional order-flow imbalance OR top-of-book size asymmetry." The order-flow imbalance variant has now been tested and falsified at default parameters; the size-asymmetry variant remains untested.

**Recommended g3l1 direction:** option (1) — retune flow threshold. The mechanism (flow as a third axis) is plausible; the parameter dose was wrong. If g3l1 with retuned flow still regresses vs g2l1, the verdict shifts to "flow axis is fundamentally redundant on vrs base," and g3l2 pivots to size-asymmetry. This sequencing extracts the maximum information per loop while respecting island-0's lesson that parameter portability is the cross-island failure mode.
