# Algorithm Notes: sip-afg-l4

## Hypothesis

**Mechanism**: Same rolling 10-second aggressor-flow window as
`aggressor-flow-gate`, but replace the gate INPUT from a raw signed
aggressor-volume sum (`net_flow`) to a **volume-normalized signed flow
fraction**:

    flow_fraction = net_signed_volume / total_volume

where `total_volume = sum(|signed_vol|)` over the same 10s window (i.e.
the absolute trade volume regardless of side, equivalent to the total
aggressor-traded contracts in the window). For BUY orders, skip when
`flow_fraction <= -frac_threshold`. For SELL orders, skip when
`flow_fraction >= frac_threshold`. Threshold `frac_threshold = 0.25`
(i.e. require at least a 25-percentage-point one-sided imbalance of
aggressor volume before gating). All other mechanics (10s outer window,
warm-up unconditional submit, reduce-only bypass, anti-cascade
`_position_flat = True` after a skip) are preserved verbatim from base.

**Inefficiency exploited**: The base algo uses an ABSOLUTE threshold
(`net_flow <= -2` contracts). This treats `net_flow = 2` identically in
two very different regimes:
- A quiet 10s window with 4 total contracts traded (`net_flow=2` =
  75% directional imbalance — strong, decisive signal). Gate fires
  correctly.
- A busy 10s window with 80 total contracts traded (`net_flow=2` = 2.5%
  directional imbalance — pure noise, well within sampling variation).
  Gate fires spuriously.

So the symmetric absolute threshold *under-fires* in quiet regimes (where
even a 1-contract imbalance is meaningful) and *over-fires* in busy
regimes (where 2 contracts is noise). The base algo's NOTES.md does not
address this — it picks 2.0 by intuition ("2 contracts of net adverse
flow in 10s is a meaningful signal") without conditioning on regime
volume. A volume-normalized fraction fixes this by definition: the same
threshold (e.g. 0.25) means "25% one-sided imbalance" whether the window
saw 4 contracts or 800.

**Why it survives costs**: This is purely a change to the gate
DECISION INPUT, not to the order's quantity, price, or routing. The
algorithm still calls only `submit_order(order)` or skips. Therefore:
- Quantity invariant preserved (never modify `order.quantity`).
- `top_of_book_only` preserved (no fill mechanics change).
- `participation_cap` preserved (no order sizing).
- `intraday_flat` preserved (reduce-only orders always submit).
- `mean_slippage` should remain 0.0 in the zero-fill-cost backtest.

**Builds on**: `aggressor-flow-gate` (the SIP base algo for this
experiment arm). Single concrete change: replace raw signed-volume sum
with a volume-normalized signed-flow fraction over the same 10s window.
The categorization in the seed prompt's method calls this "a different
gate input."

**Why this is meaningfully different from l1/l2/l3**:
- **l1 (EWMA recency-weighting)** changed the WEIGHTING within the
  window (recent prints weighted more). The signal type stayed
  volume-summed; only the kernel changed. Refuted.
- **l2 (asymmetric SELL-gate disable)** changed the SIDE-CONDITIONALITY
  of the gate decision rule (SELL gate disabled entirely based on
  EDA). The signal stayed identical for the BUY side. Refuted.
- **l3 (two-window AND confirmation)** changed the DECISION RULE
  SHAPE (added a second 3s window as a confirmation requirement). The
  signal stayed raw signed volume. Refuted.
- **l4 (this loop) — volume-normalized signed-flow fraction**
  changes the GATE INPUT TYPE itself (from contracts to fraction).
  Orthogonal to weighting (l1), side-asymmetry (l2), and confirmation
  rule (l3). The fraction reframes "how much pressure" in
  regime-adjusted units rather than absolute units. It directly
  addresses a mechanism the base NOTES did not consider.

**Alternatives considered**: None explored — the seed prompt-l0 method
(Steps 1–4) calls for picking ONE weakness and ONE concrete
modification. I have not run EDA on the train data to calibrate the
0.25 fraction threshold against the empirical distribution of
`flow_fraction`. Per the experimental boundary I am not allowed to
improvise additions to the method.

---

## Implementation Decisions

- **Threshold value (0.25)**: Chosen by proportional reasoning, not
  EDA-calibrated. The base algo's `flow_threshold = 2.0` contracts maps
  to a 25% imbalance in a window seeing 8 total contracts (2 / 8 =
  0.25). 8 contracts per 10s is plausibly near the median or somewhat
  below-median total-volume window in MES intraday (single-lot prints
  arriving at ~0.5–2 Hz). So 0.25 is intentionally near the base
  algo's effective imbalance threshold for a "typical" volume window,
  making this hypothesis a fair head-to-head: the gate fires at a
  similar rate in median-volume regimes but DIFFERS in quiet vs busy
  regimes (over-firing avoidance in busy, under-firing recovery in
  quiet). Flagging this as armchair — the critique phase will see I
  did not measure the distribution.

- **Symmetric threshold preserved**: I am NOT making the threshold
  side-asymmetric — l2 already explored that and was refuted. This
  loop holds the symmetric design unchanged so any P&L delta cleanly
  attributes to the contracts→fraction change, not to a side
  asymmetry. Both BUY and SELL gates use the same `frac_threshold =
  0.25`.

- **Warm-up handling**: If the deque is empty OR `total_volume == 0`
  (e.g. only NO_AGGRESSOR prints in the window), submit
  unconditionally. The `total_volume == 0` guard prevents
  divide-by-zero and matches the base algo's "no signal, no skip"
  warm-up principle.

- **Window length kept at 10s**: Same outer window as base. The
  hypothesis is about NORMALIZING the signal, not changing the time
  horizon over which it's measured. Holding window fixed isolates
  the input-type change.

- **NO_AGGRESSOR prints**: Continue to contribute 0 to signed flow
  AND 0 to total_volume (they are neither buyer-initiated nor
  seller-initiated aggressor activity, so they should not inflate
  the denominator). Defensive — futures MBP1 rarely emits these.

- **Running denominator**: Maintain `_total_volume` as a running sum
  of `|signed_vol|` over the deque entries, updated O(1) per print
  and re-pruned in O(k) on each gate evaluation (same pattern as the
  base algo's `_net_flow`). At gate evaluation time, divide
  `_net_flow / _total_volume` (with the warm-up zero-volume guard
  above).

- **Anti-cascade**: After any skip (BUY or SELL), set `_position_flat
  = True` so the next open is unconditional. Preserved verbatim from
  base.

- **Constraint compliance**: Quantity invariant preserved (only
  submit/skip decisions, never modify order.quantity).
  `top_of_book_only`, `participation_cap`, `intraday_flat` all
  preserved because the change is gate-only.

**Concerns**:
- The 0.25 fraction-threshold choice is uncalibrated. If empirical
  `|flow_fraction|` over the train window typically clusters near 1.0
  (because in MES the modal trade-tick signs are highly correlated
  within a 10s window), 0.25 may be too LOW and the gate fires more
  often than the base — possibly hurting P&L if those extra skips
  include profitable trades. Conversely, if empirical fractions
  cluster near 0.0 with the base's `net_flow=2` being a rare tail
  event, 0.25 may be too HIGH and the gate almost never fires —
  degenerating toward `simple` baseline behavior.
- I have NOT measured the empirical `|flow_fraction|` distribution
  on the train window. Per the seed prompt's single-pass method I
  am not running an EDA calibration step. This is precisely the
  failure-mode pattern the critique phase will identify.
- Look-ahead bias: each evaluation uses `order.ts_init` as the
  reference time for both pruning operations; only ticks with
  `tick.ts_event <= order.ts_init` are present (replay is strictly
  chronological). No future trades leak in.

---

## Predicted Backtest Outcome

Direction relative to `aggressor-flow-gate` base on the 12-date train
window:

- `realized_pnl`: **expected to rise** (+3% to +12% vs base, broad
  range due to uncalibrated threshold). Mechanism: the
  volume-normalized signal correctly suppresses spurious gates in
  busy regimes (recovering profitable orders the base wrongly
  skipped) while increasing sensitivity in quiet regimes (correctly
  skipping orders the base let through). The net effect is a
  regime-adapted gate.
- `trade_count`: **directionally ambiguous** vs base's 107,198. The
  fraction reframing redistributes WHICH orders get skipped, not
  necessarily how many. Could go up (if busy-regime over-firing was
  the dominant base failure) or down (if quiet-regime under-firing
  was).
- `mean_slippage`: **unchanged at 0.0**. Gate only affects which
  orders are submitted, not how fills happen.
- `sharpe_ratio`: should rise if the recovered trades have positive
  expected value AND the per-trade variance does not blow up.
- `max_drawdown_pct`: directionally ambiguous.
- `win_rate`: should rise marginally if the regime-adapted gate
  picks better entries on average.
- `is_weighted_bps`: directionally ambiguous. The base flagged a
  +21.9% IS regression vs `simple`; the fraction normalization
  doesn't directly address that mechanism but doesn't worsen it.

**Single-result falsifier**: if `trade_count` is within ±2% of base
AND `realized_pnl` is flat or negative vs base, the fraction reframing
has not meaningfully changed gating behavior — the 0.25 threshold is
miscalibrated for the actual `|flow_fraction|` distribution. That
would falsify the parameter choice but not the underlying
contracts→fraction mechanism. (The mechanism itself is harder to
falsify with a single backtest because a wrong threshold can mask a
correct mechanism.)
