# Algorithm Notes: position-tier-gate

## Hypothesis

**Mechanism**: Cap concurrent open exposure by skipping new open-leg
executions when the current portfolio net position size (absolute value)
is at or above a threshold. Reduce-only / position-closing orders always
execute unconditionally — they reduce exposure, never add to it. The
conditioning variable is current portfolio state, specifically the
absolute net quantity across all open positions for the instrument.

**Inefficiency exploited**: The oracle signal is noisy (sigma=5 in config)
and the strategy fires at 1-second intervals. Multiple concurrent open
legs compound the directional error of any individual signal — if the
signal is wrong or adversely timed, holding a larger gross position
amplifies the loss. The baseline `simple` algorithm executes every order
without any cap, building up potentially large concurrent exposures.
By capping at a small number of contracts (default: 2), the algorithm
prevents runaway adverse selection on compounded positions.

**Why it survives costs**: The conditioning axis is portfolio state —
current net exposure — not market microstructure or historical P&L
history. An open leg is skipped only when the position is already at the
cap, meaning the algorithm concentrates execution on entries made when the
book is "fresh" (position near-zero), avoiding incremental adverse
exposure. In a regime where the oracle is right, the cap doesn't hurt much
(the first entry captures the move; subsequent ones add marginally). In a
regime where the oracle is wrong, the cap limits drawdown directly.

**Builds on**: none — original hypothesis. This is a genuinely new
conditioning axis. None of the nine prior algorithms (streak-spread-tight,
ob-imbalance-gate, vol-regime-sizer, microprice-divergence-gate,
passive-aggressive-ladder, depth-participation-sizer, session-clock-gate,
aggressor-flow-gate, cooldown-entry-gate) condition on current portfolio
state. All nine condition on market microstructure signals (book data,
trade flow, volatility) or wall-clock time.

**Runtime interface confirmed**: `ExecAlgorithm` exposes `self.cache`
(Nautilus `Cache` object) with `positions_open(instrument_id=...)` that
returns a list of open `Position` objects, each with `quantity` and
`signed_decimal_qty`. No look-ahead: we read the cache state at
`on_order()` invocation time, which reflects fills up to that point in
the deterministic replay.

**Alternatives considered**:
- Volume/event-time pacing (pivot path): skip entries until X contracts
  have traded in the market since the last open. This was the stated pivot
  if position access were unavailable. Since it IS available, we implement
  the primary idea.
- Signed (directional) cap rather than absolute cap: skip new LONG if
  long > cap, skip new SHORT if short > cap. This is directional risk
  limiting. We use absolute net because the netting OMS means a single
  instrument position can flip sign — absolute cap is cleaner.

---

## Implementation Decisions

**Position cap**: default 1 contract (NOT 2 as originally hypothesized).
Rationale: empirical inspection of the oracle strategy's position lifecycle
shows it only ever holds 1 contract at a time (peak_qty=1 on all positions,
all dates). With cap=2, the gate is NEVER triggered (delta_pnl=0.0% on
initial run). Cap=1 is the effective threshold.

The oracle fires CLOSE+OPEN orders at the **same timestamp** (ts_init).
At `on_order()` invocation for the OPEN, the CLOSE has been submitted but
not yet filled — the Nautilus cache still shows the old position (net_qty=1).
Thus cap=1 reliably gates the concurrent OPEN, serializing entries.
Empirically verified: cap=1 on 20260309 reduced trade_count from 2863 to
1936 (32% reduction) while increasing realized_pnl from $867.75 to $1188.25
(+36.9%).

**Netting OMS**: Nautilus uses a netting OMS (one position per instrument).
`self.cache.positions_open(instrument_id=...)` returns either a list with
one Position (if open) or an empty list (if flat). We read
`position.quantity` which is the absolute (always positive) filled quantity.

**When to check**: at `on_order()` invocation, before deciding to submit.
The cache reflects the net position at the moment the order is received by
the exec algorithm — strictly in the past relative to the order's ts_init.

**Reduce-only pass-through**: `is_reduce_only` orders always execute. They
reduce exposure (bring the position toward zero) and are required for
intraday_flat compliance.

**Edge: flat position at start of session**: `positions_open()` returns
empty list → net_qty = 0 → always below cap → always submit. Correct.

**No modification of order quantity**: quantity invariant preserved. We
skip or submit — never change the order's quantity.

**Concerns**: The only subtle look-ahead risk would be if the cache were
updated *before* `on_order()` with the fill of the *current* order. Since
the fill hasn't happened yet (we're deciding whether to submit), the cache
reflects the prior state. No look-ahead.

---

## Backtest Observations

**Train window**: 12 dates (20260308–20260320, excluding 20260314 and 20260321 — no data).
- **Algo**: realized_pnl=$6049.25, sharpe=3.79, trade_count=87,544, win_rate=38.1%, max_drawdown=-0.012%
- **Baseline (simple)**: realized_pnl=$1984.00, sharpe=0.91, trade_count=132,536, win_rate=35.6%, max_drawdown=-0.038%
- **vs_baseline_pnl_pct**: +204.9% (gate: ≥5%)
- **vs_baseline_slippage_pct**: 0.0% (no regression; gate: ≤5%)
- **Status**: PASS

**What drove improvement**: The oracle fires CLOSE+OPEN at the same timestamp. With cap=1, the OPEN is skipped whenever the cache still shows a net position (i.e., the previous position has been submitted to close but not yet cleared from the cache). This "forced gap" between consecutive entries concentrates execution on lower-density oracle signals — instead of trading every oracle tick, the algorithm trades ~34% fewer orders by skipping immediate re-entries. On high-noise days (20260312, 20260313, 20260316, 20260317) where the oracle flip-flops rapidly, this dramatically reduces churn: the baseline loses $-13.25, $-327.75, $-355.00, $-134.25 respectively; the algo earns $492.50, $264.00, $124.50, $166.50. The improvement is consistent on ALL 12 dates.

**What underperformed**: Nothing materially underperformed. On low-volume days (20260308, 20260315) the absolute improvement is smaller ($52.75 and $77 respectively) but still positive. The trade count reduction (~34% fewer trades) is consistent with the skip rate.

**Hypothesis verdict**: SUPPORTED. The hypothesis that capping concurrent exposure via portfolio state reduces drawdown and improves risk-adjusted P&L is confirmed. However, the mechanism is not "cap at N contracts when position > N" as originally conceived — it's "skip OPEN while any position is in-flight." The cap=2 initial default failed to gate anything (oracle never exceeds 1 contract). Cap=1 exploits a Nautilus timing detail: the cache shows the old position when the OPEN's on_order() fires at the same ts_init as the CLOSE. See research/NOTES.md for the timing assumption alert.