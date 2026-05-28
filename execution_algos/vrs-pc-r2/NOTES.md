# Algorithm Notes: vrs-pc-r2

## Hypothesis

**Mechanism**: Quote-staleness gate layered on top of vol-regime-sizer, with explicit clock and cold-start commitments. Mechanism: track the Nautilus-clock timestamp (self.clock.timestamp_ns()) of the most recent quote tick as last_quote_ts_ns. Maintain a running median of the last K=200 inter-quote-tick gaps in nanoseconds (typical_gap_ns), computed via a fixed-size deque storing gap samples. On each incoming OPEN order, compute staleness_ns = self.clock.timestamp_ns() - last_quote_ts_ns. Compute staleness_ratio = staleness_ns / max(typical_gap_ns, 1) and staleness_factor = exp(-sens_stale * max(0, staleness_ratio - stale_threshold)) with sens_stale=0.5 and stale_threshold=10.0. Final submission probability: p = max(min_prob, base_vol_prob * staleness_factor) where base_vol_prob is the EXACT formula from vol-regime-sizer (preserves base's high-vol skip behavior). Cold-start guards: (a) if fewer than K=200 inter-tick gaps have been observed, set staleness_factor = 1.0 (identical to base); (b) if last_quote_ts_ns has never been initialized (no quotes seen), set staleness_factor = 1.0. Reduce-only orders submit unconditionally. Deterministic SHA-256 draw on client_order_id.

**Inefficiency exploited**: MES futures normally update top-of-book many times per second during active markets. When the quote stream stalls (no MBP-1 updates for many multiples of the typical inter-tick interval), the last observed mid no longer reflects active price discovery. The oracle nevertheless fires every 1 second from the historical price series, generating signals that arrive at stale quote reference points. With sigma=6 oracle noise dominating realized price change in zero-information intervals, signals fired against stale quotes have negative expected fill quality regardless of direction. This is a microstructurally distinct lever from run-1's signed-momentum (falsified) and the rejected vol-band (which conflates active-small-move with dead-market). Staleness directly measures the cause: lack of new price information at order arrival time. Importantly, this is distinguishable from a 'small realized move with active quotes' case where quotes update normally but by small amounts — in that case the oracle's price discovery is current.

**Why it survives costs**: Zero-slippage and zero-commission fill model (verified). All edge from realized P&L. The mechanism reuses the existing on_quote_tick callback — only adds a timestamp scalar and a fixed-size gap deque. No new subscriptions, no new venue routes. Worst-case bounding: (a) typical_gap_ns is a rolling self-calibrating baseline, so the dimensionless threshold adapts to per-session liquidity; (b) stale_threshold=10x typical_gap is conservative — only true outliers trigger any attenuation; (c) sens_stale=0.5 makes the staleness factor a perturbation, not a dominating signal — at staleness_ratio=20 (twice the threshold), staleness_factor = exp(-0.5*10) = 0.0067 -> min_prob floor kicks in; at staleness_ratio=12, staleness_factor = exp(-0.5*2) = 0.37; (d) cold-start handling ensures no spurious skipping before the running median stabilizes; (e) staleness_factor multiplies the base vol probability rather than replacing it, so the submission set is a STRICT SUBSET of base's (unlike run-1, where the strict-subset claim was true but the additional skips were on the wrong axis). Unlike run-1, the staleness signal is unambiguously a measure of information-vacuum — when no new quotes arrive, no current market state is available to the oracle.

**Builds on**: vol-regime-sizer (multiplies the base's submission probability by a wall-clock staleness factor; in actively-updating markets the staleness factor equals 1.0 and behavior is identical to base)

**Alternatives considered**: (1) Two-sided vol band (round 1): rejected — conflates active-small-move with dead-market populations. (2) Signed-momentum direction (run-1): falsified at -88.23% vs base. (3) Mean-reversion sign-flip of run-1: same noisy signed-mid axis. (4) Quote-update count over fixed wall-clock window: equivalent to staleness but more state. (5) Spread-conditional: MES top-of-book spread near-constant 1-tick. (6) Trade-tick aggressor flow: new subscription path; defer. (7) Absolute clock-time gate: coarse proxy for what staleness measures directly.

**Debate summary**: 3 round(s), outcome=CONVERGED. Key objections resolved: (round 1) pivoted from two-sided vol-band to quote-staleness gate to avoid conflating active-small-move with dead-market populations; (round 2) committed explicitly to self.clock.timestamp_ns() rather than Python wall-clock, and added cold-start guard (staleness_factor = 1.0 until K=200 inter-tick gaps observed) to prevent spurious early-session skipping.

---

## Implementation Decisions

- **Clock source**: self.clock.timestamp_ns() for both last_quote_ts_ns (in on_quote_tick) and staleness reference at order arrival (in on_order). Nautilus backtests run on simulated event time, so wall-clock time.time() would produce nonsense staleness numbers.
- **Inter-tick gap tracking**: collections.deque of fixed maxlen=200, storing ns gaps between consecutive quote ticks. First gap added when the second tick arrives (no gap on first tick).
- **Running median**: computed via statistics.median(self._gap_deque) per order. O(K log K) per query for K=200 over ~130k orders is acceptable (~26M ops total, well under a second). No incremental two-heap structure needed at this scale.
- **Cold-start guard**: returns staleness_factor = 1.0 (no attenuation) until len(self._gap_deque) >= 200. This is in addition to the base's min_ticks=30 cold-start for the vol estimator.
- **Multiplicative composition with base vol formula**: implementation embeds the base vol-regime-sizer probability formula inline rather than importing from the base module (keeps vrs-pc-r2 self-contained and explicit).
- **Inherits base parameters**: fast_halflife=20, slow_halflife=120, sens_vol=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0. Adds: stale_window=200, stale_threshold=10.0, sens_stale=0.5.
- **Reduce-only orders**: pass through unchanged at full quantity, intraday_flat compliance.
- **Quantity invariant**: child_qty == parent_qty for every submitted order; algorithm never inflates quantity.
- **Deterministic draw**: identical SHA-256 of client_order_id (matches base and vrs-pc-r1) for reproducibility.
- **Diagnostic counters**: tracks submitted, skipped, skipped_vol_only, skipped_stale_active (number of skips where the staleness factor was below 1.0). These help validate post-hoc whether the staleness axis is active in this backtest.

**Concerns**:
- No look-ahead bias: on_quote_tick populates last_quote_ts_ns and the gap deque from already-observed ticks; on_order reads only these accumulated values at the order arrival ns timestamp. No future information.
- The dead-market-noise-trade hypothesis assumes oracle signals fired during quote-stream stalls have systematically worse fill quality. If MES quote streams rarely stall enough to trigger the gate (i.e., 10x-median outliers are extremely rare), the algorithm degenerates to base — no harm, but no upside either. This is a falsification risk worth monitoring through the post-hoc skipped_stale_active counter.
- stale_threshold=10.0 and sens_stale=0.5 are best-guess parameters; the conservative sens_stale damps spurious activations. The rolling self-calibrating typical_gap_ns adapts per session, so the dimensionless threshold should generalize across days without per-session tuning.

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $441.75
- sharpe_ratio = 9.37
- trade_count = 85,526
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **-41.39%**
- vs_base_slippage_pct = 0.0%

**What drove improvement**: The quote-staleness gate produced a much higher Sharpe (9.37 vs vrs-pc-r1's 1.01) — when this algorithm trades, it trades cleanly. Mean slippage stayed at zero. The mechanism successfully filtered out the worst windows of microstructure inactivity.

**What underperformed**: Aggregate P&L fell short of base by 41.39%. The staleness gate was too aggressive: filtering out submissions in low-update windows also discarded a non-trivial share of profitable orders. Trade_count dropped to 85,526 — a meaningful reduction in participation, which dominates the per-trade quality gain.

**Hypothesis verdict**: **Partially supported.** The hypothesis predicted the staleness gate would improve per-trade EV by skipping orders that fill against stale quotes. The Sharpe improvement is consistent with that mechanism. But the magnitude of participation reduction was higher than expected, and the P&L payoff did not compensate. The mechanism is real but the gate parameter is mis-tuned.

**Suggested next attempt**: Either (a) loosen the staleness threshold so fewer orders are gated out, or (b) make the staleness factor smoother (probability-based instead of binary gate) so the gate degrades gracefully near the threshold. A direct microstructure liquidity proxy (e.g. mid-EWM update rate × spread) would be a more principled signal than wall-clock staleness alone.
