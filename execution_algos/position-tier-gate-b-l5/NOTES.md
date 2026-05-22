# position-tier-gate-b-l5 — NOTES

Per-iteration experiment. Arm: `base_algo=position-tier-gate`,
`mode=brief-summary`, **loop 5**. Starting point: `position-tier-gate-b-l4`
(this algorithm is a modified copy of that file).

## Hypothesis

The brief summaries of loops 1-4 converge on a single remaining lever.
Loops 1-3 exhausted binary skip/submit *entry gating* (equity circuit
breaker, then re-arming breaker, then order-time book-imbalance) — all
failed because the `sigma=200` per-trade edge is structurally negative and
spread roughly uniformly across entries. Loop 4 removed every gate (a
zero-latency pass-through) and confirmed implementation shortfall (IS) is
*fixed across binary submit/skip policies*: loop-4 `is_weighted_bps`
(0.04497) sits within 0.08% of base (0.04501). Loop-4's `next` directive
names exactly one untried structural lever: **order TRANSFORMATION** —
modify order quantity (child-order slicing) or add genuine timing offsets,
not binary skip/submit.

A pre-implementation check ruled out the *quantity* half of that lever:
`backtest_low_level.py` sets `strategy_options.setdefault("trade_size",
Decimal("1"))`, and `simple`'s order log confirms every order is
`quantity == 1` (894/894 on 20260308). A 1-lot cannot be split into smaller
children — `spawn_market` requires `quantity > 0` and children must sum to
`<= primary.leaves_qty`. Child-order slicing is therefore structurally
impossible in this pipeline.

That leaves the *timing/order-type* half. Every prior loop and the base
submit **market** orders, which take liquidity and pay the full bid-ask
spread on every fill. The untried transformation is to make the opening
order **provide** liquidity instead of taking it:

> **H5:** Replace the immediate market submission of each OPEN leg with a
> *passive-then-aggressive* execution — first spawn a **post-only LIMIT at
> the same-side touch** (BUY at the cached bid, SELL at the cached ask),
> then set a short time alert; on the alert, cancel the limit if it is
> still unfilled and submit a **MARKET** order for the residual quantity.
> Reduce-only CLOSE legs always route straight to market (intraday_flat —
> closes are never delayed).

Why this should move IS where skip/submit could not: IS is measured as
`(fill_px - arrival_mid) * direction / arrival_mid * 1e4`. A market BUY
fills at the **ask** — roughly `+half_spread` of IS. A post-only limit BUY
that rests at the **bid** and fills there costs roughly `-half_spread` of
IS (a price *better* than the arrival mid). On every order where the
passive limit fills before the timeout, IS improves by approximately the
full spread; on every order where it does not fill, the market fallback
reproduces exactly the base/loop-4 outcome. The transformation is therefore
weakly IS-dominant by construction: it can only match or beat the base on
IS, never lose — the question the backtest answers is *what fraction* of
opens fill passively under `sigma=200`, and whether capturing that spread
also lifts per-trade realized P&L.

This is genuine order transformation, not the skip/submit dichotomy that
failed four ways: total filled quantity is always exactly the parent
quantity (passive fill + market residual = parent), and intraday_flat holds
because the passive window is short and every CLOSE bypasses it.

### Parameters
- `passive_timeout_ms = 750` — how long a post-only limit may rest before
  the market fallback fires. Short enough that a 30s-horizon oracle signal
  is not stale by fill time and intraday_flat is uncompromised; long enough
  to give the touch a realistic chance to be hit.
- Post-only is used so the limit can never cross the spread and accidentally
  act as a market order (which would defeat the purpose and could fill
  *worse* than the touch).

### Risk / invariants
- **Quantity invariant**: on the timeout, the market fallback is sized to
  `primary.leaves_qty` (the unfilled residual), so total fills == parent
  quantity exactly. If the limit fully filled, `leaves_qty == 0` and no
  fallback is sent.
- **intraday_flat**: CLOSE (reduce-only) orders never enter the passive
  path. The 750 ms passive window on opens is far inside the session.
- **No look-ahead**: the touch price comes from `cache.quote_tick()` at
  `on_order()` time — the most recent quote at or before the order's
  `ts_init`. No future data is read.
- **Fail-open**: if no quote is cached yet (session warmup), the order is
  submitted immediately as a plain market order — identical to base/loop-4.

## Backtest Observations

Train window: 12 dates (2026-03-08 .. 2026-03-21), all completed. Per-date
trade counts 449-28377 — no low-sample date.

| metric             | loop-5    | base ptg  | simple    |
|--------------------|-----------|-----------|-----------|
| realized_pnl       | -6548.25  | -5892.25  | +156.00   |
| is_weighted_bps    |  0.03359  |  0.04501  |  0.03893  |
| sharpe_ratio       | -16.56    | -27.23    |  0.60     |
| max_drawdown_pct   | -0.1461   | -0.0986   | -0.0529   |
| win_rate           |  0.3286   |  0.3285   |  0.3506   |
| trade_count        | 152300    | 101304    | 136734    |

vs base: `vs_base_pnl_pct = -11.13%`, `vs_base_slippage_pct = 0.0%`
(slippage is identically 0.0 on every algo in this pipeline).
vs baseline (`simple`): `vs_baseline_is_bps = -13.60` — IS *improved*.
Suggested verdict: FAIL (delta_pnl_pct vs simple = -4297.6%).

### What the hypothesis got right

H5 predicted the passive-then-aggressive transformation would lower
implementation shortfall, and it did — decisively, and for the first time
in this arm. `is_weighted_bps` fell to **0.03359**, a 25.4% reduction
versus the base (0.04501) and *below* `simple` itself (0.03893).
`vs_baseline_is_bps` went negative (-13.60), the canonical execution
objective. Every prior loop in this arm left IS pinned within 0.08% of the
base (loops 1/2/4) or made it worse (loop-3 at 0.064); loop-5 is the only
one to actually move it, confirming that order-type transformation — not
the skip/submit dichotomy — is the lever that touches IS. The per-date IS
trace also shows the mechanism clearly: on the high-volume late-window
dates the passive limit fills far more often (20260318 IS -0.0009,
20260320 IS 0.0004 — essentially zero or spread-capturing), while the
thin early dates (20260308 IS 0.28, 20260309 0.22) barely fill passively
and behave like the market-fallback base.

### What the hypothesis got wrong

H5 implicitly assumed that lowering IS would lift realized P&L. It did not.
realized_pnl fell to -6548.25, an 11.13% *worse* result than the base.
The transformation is genuinely IS-dominant yet P&L-negative, which forces
a clean diagnosis: **IS and realized P&L are decoupled here.** Two
concrete reasons:

1. *Adverse selection on the passive fills.* A post-only limit at the
   touch fills precisely when the market is willing to trade against it —
   i.e. disproportionately when price is about to move through the touch
   adversely. The spread captured at fill time (the IS gain) is handed
   back, and then some, as the position is marked against the very move
   that produced the fill. The passive limit is selected into the worst
   subset of entries. This is the same lesson loop-3 found for book
   imbalance, now re-confirmed from the opposite direction: you cannot
   improve P&L by *choosing how* to fill a structurally negative-edge
   signal.

2. *trade_count rose to 152300* — identical to loop-2 and loop-4, the
   ungated "submit everything" upper bound on order flow. Loop-5 keeps
   every order (no gating), so under the sigma=200 negative per-trade edge
   it loses about as much as loops 2/4 in aggregate; the IS improvement
   shaves the *execution* cost component but cannot offset the structural
   directional loss.

### Constraint this loop establishes for future loops

The passive-then-aggressive transformation is the *correct* tool for the
*IS* objective and the wrong tool for the *P&L* objective. is_weighted_bps
is now genuinely beatable (loop-5 already beats both base and simple on
it); realized P&L is not, because the sigma=200 per-trade edge is
structurally negative and order-execution choices (gate / no-gate,
market / passive limit) only redistribute a cost that is small relative to
the directional loss. A future loop that wants to move *P&L* must change
*which orders enter the fill set* in a way correlated with the sign of the
forward return — and loops 1-3 already showed equity-feedback and
book-imbalance do not carry that signal. A future loop that wants to move
the *execution* objective (is_weighted_bps / is_bps) should build on
loop-5: tune `passive_timeout_ms` (longer timeout => more passive fills =>
lower IS but more staleness/adverse selection), or post the passive limit
one tick *inside* the touch to trade fill-rate against price improvement.
