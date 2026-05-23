# Algorithm Notes: position-tier-reduce-only-defer-gate

## Hypothesis

**Mechanism**: Exit-side reduce-only fast-path **restructure**. Previously,
every reduce-only (close) order was submitted immediately on the first tick
it arrived (iters 1-7). This iteration **defers** reduce-only orders for up
to `max_defer_ticks=20` quote ticks (or `max_defer_seconds=15.0`, whichever
comes first) **while the EMA book lean remains favourable to the position
direction**. The deferred order is released the instant the lean turns
adverse, the tick/time caps expire, OR a tick reveals a same-direction new
open-leg signal (the strategy has flipped intent).

Concretely:
  - LONG (net_qty > 0) closing via SELL (reduce-only): book is favourable
    when EMA imbalance > `close_favor_threshold=0.55` (bids heavy → upward
    price pressure persists → defer the close to let price drift higher).
    Release as soon as EMA imbalance ≤ `close_favor_threshold` (lean
    turned neutral/adverse) or caps expire.
  - SHORT (net_qty < 0) closing via BUY (reduce-only): favourable when
    EMA imbalance < `1 - close_favor_threshold = 0.45` (asks heavy →
    downward pressure → defer the close to let price drift lower).
    Release when EMA imbalance ≥ `1 - close_favor_threshold` or caps
    expire.

If the position is already flat at on_order time (net_qty == 0 — a stale
reduce-only after the position closed elsewhere), submit immediately.

All other components inherited verbatim from iter-2 best
(`position-tier-imbalance-ema-gate`): position_cap=1 (cascade
prevention), EMA-imbalance gate on opens (alpha=0.30, skip_threshold=0.40,
min_total_size=2.0).

**Inefficiency exploited**: The exit-side fast-path is the only mechanism
in this family that has **never** been varied across iters 1-7. Every
prior iteration submits closes the instant they arrive, ignoring the
short-horizon book information that the same algorithms use to gate
opens. If the EMA imbalance signal predicts adverse-mid-direction for
opens (the basis of the +10312% gate iter-2 achieves), it must by
symmetry predict favorable-mid-continuation for closes that align with
the lean. Deferring a SELL-close when bids are heavy lets the long
collect a few more ticks of upside before flattening; deferring a
BUY-close when asks are heavy lets the short collect a few more ticks
of downside.

**Why it survives costs**: Fill is at top-of-book (zero slippage by
construction — `research/NOTES.md 2026-04-30`) and commissions are 0,
so the only cost is the **adverse mid-drift risk** during the defer
window. The release-on-adverse-lean rule means an unfavourable turn
flushes the order at exactly the moment the EMA signal flips —
symmetric with how the entry-side gate uses the same signal. The
worst-case cost is bounded by `max_defer_seconds=15.0` × typical
intra-second mid drift of MES (~0.25 pts/sec realistic max), so an
upper bound on adverse drift per deferred order is ~3.75 pts ≈ $18.75.
On average across N deferred orders this expectation is much smaller
than the expected directional drift the EMA signal selects for.

**Builds on**: `position-tier-imbalance-ema-gate` (iter-2, family-best
pnl=$4503.25, sharpe=20.79 on N=11). This is the iter-8 pivot iter-7
NOTES.md explicitly recommended after exhausting the entry-side
gate-axis gradient (5 microstructure variations + 1 calendar variation
all clustering at ≤ iter-2 pnl). It is the ONLY remaining unexplored
structural mechanism in the position-tier family.

**Alternatives considered**:
  - Reduce-only **ladder**: split the exit into K child orders timed
    over a window (iter-7 mentioned this). Rejected for iter-8: violates
    the quantity invariant if children sum to > parent (must add
    fragmentation accounting + careful child sizing). Pure defer is the
    minimum-code-delta structural test. If pure defer succeeds, iter-9
    can extend to a true ladder.
  - Defer with a **time-only** cap (no EMA condition): rejected because
    it doesn't use any signal — pure delay equivalent to letting the
    position run longer with no logic. The whole point is to defer only
    when the EMA says continued favorable drift is likely.
  - Aggregate vs per-order deferral: chose per-order (each reduce-only
    has its own enqueue time, defer-tick counter, and release condition).
    Aggregated would risk batching adverse closes with favorable ones.

---

## Implementation Decisions

**Defer release conditions (any one triggers immediate submit)**:
  1. **Adverse lean**: EMA imbalance has crossed back through the
     favorability threshold. For a deferred SELL-close: release when
     ema_imbalance ≤ 0.55. For a deferred BUY-close: release when
     ema_imbalance ≥ 0.45. This is the primary release rule.
  2. **Tick cap**: ticks_deferred >= max_defer_ticks (20 by default).
     Bounds the longest defer in market-event terms.
  3. **Time cap**: ts_event - enqueued_ts_ns >= max_defer_seconds * 1e9
     (15 sec by default). Bounds the longest defer in wall-clock
     terms — critical for intraday_flat compliance near session close.
  4. **Position-flat check**: if net_qty for the instrument has
     dropped to 0 by the time we'd release, the order is stale — submit
     it anyway (Nautilus reduce-only logic handles the no-op safely).

**Choice of `close_favor_threshold=0.55`**: slightly above 0.5 so a
neutral book (50/50) does NOT trigger a defer. Symmetric with the
open-side `skip_threshold=0.40` interpretation: the EMA must be
*meaningfully* leaning before we act on it. Picked once on literature
prior (~10% off-neutral, matching the Lipton-Pesavento "informative
imbalance" region) — NOT tuned on the train set.

**Choice of `max_defer_ticks=20`**: at MES typical quote rate (~5-20
quotes/sec near liquid periods), 20 ticks ≈ 1-4 seconds of book time —
well inside the EMA's effective horizon (alpha=0.30 → ~6-tick window)
but allows a few EMA updates within the defer window. Picked once on
the EMA horizon prior.

**Choice of `max_defer_seconds=15.0`**: hard cap independent of tick
rate, in case a quiet period would otherwise let an order sit for
minutes. 15 sec is well under any plausible session-boundary risk
(strategy + engine's own intraday-flat trigger fires near session close
with > 15 sec margin to clean up).

**Session-close safety**: at on_order time, if the order is a
reduce-only and would defer past a presumed session boundary, we'd
still flush via the max_defer_seconds cap. We do NOT additionally
inspect session-end timestamps here — the strategy + engine handle
intraday_flat enforcement; we just guarantee no held order survives
longer than 15 sec from enqueue.

**State management**:
  - `_pending_closes: dict[str, list[dict]]` — per-instrument FIFO list
    of pending closes, each with `{order, enqueued_ts_ns, tick_count}`.
  - On each `on_quote_tick`, after updating EMA, walk pending list and
    submit any that meet a release condition; remove from list.
  - On `on_reset`, clear all pending state.

**No look-ahead**: the EMA at on_order time and at each on_quote_tick
release-check is built only from quotes already processed. Deferring
uses no future information — the order is held and released based on
later quotes, but the release decision uses the EMA at that *later*
moment, not the order's *future* fill price.

**Quantity invariant**: each pending reduce-only is submitted intact
or not at all. No splitting, no sizing. Strict preservation.

**Concerns**:
  - **OOM hazard on 2026-03-19**: this algo subscribes to quote ticks
    (same as every iter-1..7 algo in this family). Per
    `research/NOTES.md 2026-05-23`, the 8 GiB Rust OOM reproduces on
    that partition for any quote-tick-subscribing algo. Expected to
    aggregate over 11/12 train dates.
  - **Deferred-fill timing**: by the time a deferred reduce-only is
    submitted, the mid may have moved adversely. The release-on-adverse
    -lean rule should catch this in the EMA-signal-relevant fraction of
    cases; the remainder are bounded by the time/tick caps.
  - **Lifetime risk**: a reduce-only deferred past a strategy-flatten
    boundary (the strategy issues another close later) would land in the
    queue twice. The netting OMS handles double-close as a no-op for the
    second, so this is safe; just slightly noisy in the order log.
  - **Variance**: deferring SHOULD increase per-trade variance (we hold
    positions longer, exposing them to mid drift), which would lower
    Sharpe even if mean pnl rises. The hypothesis verdict must weigh
    both — a pnl rise that exactly offsets a Sharpe drop is a wash.
  - **Asymmetric error**: if the EMA signal is informative on the LONG
    side but not the SHORT side (or vice versa), deferral would help
    one direction and hurt the other. Backtest will reveal asymmetry
    via win-rate-by-side decomposition if observed.
  - **Falsification path**: if pnl falls or is unchanged, the EMA
    signal does NOT have meaningful continuation power for short
    horizons after the open decision is taken; the exit-side fast-path
    is correctly tuned at "submit immediately"; the entire position-
    tier family is genuinely exhausted at the iter-2 pnl band on this
    train window.

---

## Backtest Observations

**Aggregated across 11 of 12 configured train dates** (2026-03-08 through
2026-03-20 excluding 2026-03-19 — the documented 8 GiB Rust/Nautilus OOM
hazard for any algo in this family that calls `subscribe_quote_ticks`,
see `research/NOTES.md 2026-05-23`). Cached `simple` baseline for the
same 11 dates was used (`--use-cached-baseline`).

**Headline metrics (algo / baseline)**:
  - realized_pnl: $3521.00 / $43.25 → delta +8036.99% (PASS vs +5.0% gate)
  - sharpe_ratio: 17.79 / 0.17 (N=11 cross-day)
  - win_rate: 37.93% / 35.02% (+2.91pp)
  - trade_count: 62,160 / 111,489 (-44.2%)
  - max_drawdown_pct: -1.31% / -5.29% (improved)
  - mean_slippage: 0.0 / 0.0 (zero-cost fill model, `research/NOTES.md 2026-04-30`)

**REFINEMENT-vs-iter2 (family-best) read — HONEST**:
  - pnl REGRESSION of -21.8% ($3521.00 vs $4503.25)
  - sharpe REGRESSION -3.0 (17.79 vs 20.79) — far below min_sharpe_delta=+0.5
  - win_rate -1.36pp (37.93% vs 39.29%) — misses min_winrate_delta_pp=+2.0
  - trade_count -0.10% (62,160 vs 62,220) — essentially unchanged
  - max_drawdown +0.10pp (-1.31% vs -1.21%) — barely worse, misses min_mdd_delta_pp=-1.0

  The reduce-only-defer mechanism FAILS to meet ANY refinement-axis
  target in `config.yaml → refinement.targets` vs iter-2 best. It
  regresses on every primary axis.

**What drove improvement (vs baseline)**: Inherited verbatim from
iter-2 — the position_cap=1 + EMA-imbalance open gate carries the
+8000% baseline-delta. The defer mechanism contributed NOTHING new on
top of that; if anything it dragged pnl down.

**What underperformed (vs iter-2)**:
  - Per-date pattern: every single date's pnl is LOWER than iter-2's
    cluster ($4377-$4503 across N=11 in iters 2-6). The defer queue
    submitted closes a few ticks later than iter-2's immediate-close
    path, and on net, the mid drifted ADVERSELY in those few ticks
    more often than favourably — even after release-on-adverse-lean.
  - Trade count nearly identical to iter-2 (62,160 vs 62,220), so the
    -21.8% pnl regression is purely *per-close fill-quality* loss, not
    an entry-pattern change. Average pnl per trade fell from $0.0724
    (iter-2) to $0.0566 (iter-8) — a $0.016 / trade adverse drift per
    deferred close, on the ~62k closes.
  - The release-on-adverse-lean rule fires AFTER the EMA has already
    drifted, by which time some adverse mid movement has already
    happened; the residual cost cannot be fully reclaimed.
  - The max_defer_seconds=15.0 and max_defer_ticks=20 caps were
    binding rarely enough that the adverse-lean release dominated —
    but adverse-lean release is itself NOT zero-cost.

**Hypothesis verdict**: FALSIFIED in the direction the hypothesis
explicitly listed as the falsification path. The EMA-imbalance signal
does NOT have meaningful continuation power for short horizons AFTER
the open decision is taken; treating it as a defer-close indicator is
strictly worse than `submit_order(order)` immediately. The entire
position-tier family is **structurally exhausted** at the iter-2 pnl
band on this train window.

  Concrete falsification quote from this NOTES.md Hypothesis section:
  > Falsification path: if pnl falls or is unchanged, the EMA signal
  > does NOT have meaningful continuation power for short horizons
  > after the open decision is taken...
  Observed: pnl FALLS by -21.8% vs iter-2 — falsification met
  unambiguously.

**Structural takeaway (load-bearing for the parent batch and future
iterations)**:

  Across iters 2-8, the position_cap=1 + reduce-only-fast-path stack
  has been tested under EIGHT distinct mechanisms with NOTES.md
  hypotheses spanning:
    iter-1: single-tick imbalance gate
    iter-2: EMA-smoothed imbalance gate (family-best $4503)
    iter-3: rolling-OFI gate (regression)
    iter-4: position_cap relaxation 1→2 (regression)
    iter-5: symmetric vol-regime gate (regression)
    iter-6: directional vol-regime gate (effective wash with iter-2)
    iter-7: time-of-day open/close skip (regression)
    iter-8: EXIT-side reduce-only defer (regression — THIS iter)

  All five mechanism-axis tests (iters 3,4,5,7,8) regressed; iters 2/6
  are effectively the same algorithm. **The binding constraint of this
  family is the immediate-execution + position_cap=1 + EMA-imbalance
  pipeline; no marginal mechanism added or substituted improves pnl
  on this train window.**

**Suggested next attempt**: STOP refining this family on the
oracle-strategy / sigma=6 / horizon=30s train window. The remaining
exploration gradient is in three orthogonal directions, in priority
order:
  1. **Snapshot iter-2 to S3** for OOS Lambda confirmation — it is the
     unambiguous family-best on train. The OOS report is the only
     remaining info that can change the picture for this family.
  2. **Strategy-axis change** — request the operator switch
     `strategy.name` or `strategy.kwargs.sigma` in config.yaml. The
     execution-algorithm research loop is the variable under study,
     but it has converged within the current strategy parameters; a
     new strategy regime would re-open the design space.
  3. **Exit-side LADDER** (true child-order fragmentation across K
     subwindows, summing to parent.quantity) — distinct from the pure
     defer tested here, and still untouched. Would require careful
     quantity-invariant accounting per OBJECTIVE.md §3. Lower priority
     than (1) and (2) given the falsification result.

Trade count HIGH (62k+), not low-trade-count flagged.
Config: sigma=6, seed=42, horizon=30s; position_cap=1, skip_threshold=0.40,
min_total_size=2.0, ema_alpha=0.30, close_favor_threshold=0.55,
max_defer_ticks=20, max_defer_seconds=15.0.
