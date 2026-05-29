# Algorithm Notes: ptg-pc-r5

## Hypothesis

**Mechanism**: ORDER-BOOK-DELTA-BACKED ADVERSE-MOM SKIP gate with diagnostics + staleness guards, layered on position-tier-gate (cap=1) verbatim. Three concrete changes vs r4: (1) STRUCTURAL FIX for hypothesis (c): switch from subscribe_quote_ticks() to subscribe_order_book_deltas(book_type=L2_MBP) for the MESM6 instrument, subscribed EAGERLY in on_start() (via cache.instruments() lookup at start time; if empty, fall back to instrument_id from the first on_order). on_order_book_delta(s) fires for EVERY level update (not just TOB CHANGES), which is structurally a strict superset of on_quote_tick events. From each delta, derive the current best bid/ask via self.cache.order_book(instrument_id) and append (ts_event_ns, mid, spread) to the buffer — same buffer shape as r4. (2) STALENESS GUARDS per criticizer demand: at on_order, before computing the signal, check (a) if buffer_latest_ts > order.ts_init → SUBMIT (causal violation); (b) if buffer_latest_ts < order.ts_init - 100_000_000 (>100ms stale) → SUBMIT (data-too-old); (c) if the buffered quote at <= now-100ms is itself > 500ms older than expected → SUBMIT. These three guards make the signal-bounds explicit and bounded. (3) DIAGNOSTICS per criticizer demand: increment a session counter on every on_order_book_delta(s) fire; at on_stop log a line with (instrument_id, n_deltas, n_orders_seen, n_open_orders, n_skips_cap, n_skips_adverse, n_submits_passed_both, n_safe_submits_breakdown). This makes the under-fire root cause empirically OBSERVABLE — if n_deltas is still low, we have direct evidence the simulator structurally throttles updates and the mechanism is inviable regardless of approach; if n_deltas is high but n_skips_adverse is low we know the staleness guards are firing; etc. The decision rule itself is unchanged from r4: signed_mom_100 = (mid_now - mid_100ms_ago)/TICK_SIZE * side_sign; spread_ticks = (ask-bid)/TICK_SIZE from buffer's own latest entry; SKIP if signed_mom_100 <= -1.0 AND spread_ticks <= 1.0. Buffer 200ms retention. CLOSE orders always submit.

**Inefficiency exploited**: Same as r4 + same offline +13.74% signal. The mechanism exploits the oracle's overreaction to transient 100ms price excursions in tight-spread regimes. The novel claim vs r2 is the structural fix: order_book_deltas in Nautilus emit one callback per level update (not per TOB change), so on a dense MBP-1 stream the delivery rate to on_order_book_delta(s) should approach the raw MBP-1 message rate (or at minimum a much larger fraction than on_quote_tick's TOB-change-only rate). If this assumption holds, buffer density rises ~10x and the offline +13.74% signal becomes recoverable. The instrumentation (point 3) makes this assumption FALSIFIABLE in one run rather than requiring another iteration.

**Why it survives costs**: Mean slippage = 0 and commissions = 0 unchanged. Mechanism only SKIPs OPEN MARKET orders; never modifies, never adds passive orders. CLOSE submits unchanged → intraday_flat preserved. Runtime overhead: per-delta callback does one O(1) cache lookup + 3 deque appends; per-order does one bisect + 3 boolean guards. Even at 10,000 deltas/sec (full MBP-1 rate) the overhead is microseconds per delta, negligible vs the backtest's other work.

**Builds on**: position-tier-gate (cap=1 verbatim). DIRECT FIX of r4 that ADDRESSES THE THIRD HYPOTHESIS the round-2 criticizer flagged. The structural change is the delivery channel (order_book_deltas vs quote_ticks); the staleness guards make the signal bounded; the diagnostics make the outcome interpretable regardless of which way it lands. If this run beats the gate, we have evidence the channel switch fixed it. If it doesn't beat the gate but n_deltas is high and n_skips_adverse is in the 1000s, we have evidence the signal itself doesn't transfer live — which is information; the experiment is exhausted on this axis. If n_deltas is low, the simulator structurally limits the rule and pos-tier-gate is the local optimum on this axis.

**Alternatives considered**: (1) Pure instrumentation-only run (just count on_quote_tick fires, no behavior change): would just reproduce position-tier-gate base, wasting the run. The instrumentation is added on TOP of the mechanism, not instead of it. (2) Subscribe to BOTH quote_ticks AND book_deltas to compare delivery rates: adds complexity without benefit — book_deltas is structurally a superset; comparing rates doesn't change the decision. (3) Multi-second lookback (criticizer suggestion ii): Proposer's own r5-round-2 data shows this gives only +2.72%, below the +5% gate; not worth pursuing. (4) Abandon adverse-mom entirely and try a different axis: every axis tried so far (consensus, loss-cooldown, winners-run, layered aggressor-flow, randomized reduction) has failed empirically or in debate. The order-book-delta channel is the one untried delivery improvement on the one mechanism with measured offline alpha. (5) Hard-code the participation throttle in the staleness guards (e.g. require n_deltas in last 1s >= 5 before allowing SKIP): adds another knob; punt to follow-up if needed. (6) Use cache.order_book(instrument_id).best_bid_price()/best_ask_price() instead of maintaining a buffer: this returns the CURRENT book state but not the 100ms-ago state — still need the buffer for the lookback. (7) Use TradeTick for trade-direction microstructure + quote channel for spread: tested empirically in r5-round-1 pre-validation, the trade-flow signal removed PROFITABLE trades. Declined.

**Debate summary**: 3 rounds (CAP), outcome=CONVERGED on round 3. Round-1 BLOCKING (layered-filter additivity false) empirically refuted via offline pre-validation; hypothesis pivoted. Round-2 three MAJOR objections (hypothesis-c not addressed; need instrumentation/fallback/book-deltas; decision-time staleness) all explicitly addressed in round-3 via the channel switch + staleness guards + diagnostics. Round-3 PASSed with only MINOR objections (delta-channel granularity risk depends on dataset, warmup edge case, wider outcome distribution acknowledged).

---

## Implementation Decisions

**Gate ordering**: cap=1 check FIRST (cheapest, preserves base behavior), adverse-mom SKIP check SECOND (only on OPENs the cap would have submitted). CLOSE orders bypass both gates.

**Delivery channel — order_book_deltas instead of quote_ticks**: The single most material change vs r4. r4 used `subscribe_quote_ticks` and `on_quote_tick`, which under-fired by 10-15x in dense periods. `subscribe_order_book_deltas(book_type=L2_MBP)` fires `on_order_book_deltas` for every batch of level updates. In the Nautilus model, every individual book change (add, update, delete) is a delta — whereas quote_ticks aggregate to TOB-state changes only. This is the structural fix to hypothesis (c) from r4's NOTES.

**Eager subscription with lazy fallback**: In `on_start`, walk `self.cache.instruments()` and subscribe to each. If the cache is empty (instruments not yet loaded at strategy startup), the first `on_order` call triggers `_ensure_book_subscription(order.instrument_id)` as a fallback. This avoids the r4-class "lazy subscription means buffer is empty when the first OPEN arrives" issue while remaining robust to ordering uncertainty.

**Buffer derivation from book state, not from the deltas themselves**: Each delta could be an add/update/delete at any depth level; computing the new best bid/ask from a delta alone requires reconstructing the book state, which the cache already does. So in `on_order_book_deltas`, we look up `self.cache.order_book(instrument_id)` and read its `best_bid_price()` / `best_ask_price()`. This is the canonical Nautilus pattern.

**Buffer**: three parallel deques (`_ts_buf`, `_mid_buf`, `_spread_buf`) so `bisect.bisect_right(self._ts_buf, ts_back)` works directly. Same shape as r4 — the data structure is reused.

**Staleness guards (round-2 criticizer demand)**:
1. **Causality guard**: if `buffer_latest_ts > order.ts_init`, the buffer contains future data — SUBMIT. Should never fire in a deterministic backtest replay, but defensive.
2. **Buffer-age guard**: if `buffer_latest_ts < order.ts_init - 100_000_000`, the latest buffered quote is more than 100ms older than the decision time. The signal is unreliable — SUBMIT.
3. **Lookback-staleness guard**: if the buffered quote selected as `mid_100ms_ago` is more than 500ms older than the target lookback timestamp, the buffer was sparse during the lookback window. The signed_mom_100 isn't a clean 100ms diff — SUBMIT.

Each guard increments a dedicated counter so its activation rate is observable at on_stop.

**Decision-time reference**: use `order.ts_init` (the engine's order-emission timestamp) as the "now" reference, NOT `self.clock.timestamp_ns()`. r4 used the clock, but in a backtest replay the clock advances on a per-event basis and may not equal `order.ts_init` exactly when on_order fires. Using `ts_init` directly anchors the decision to the order's own timestamp.

**mid_now from buffer's own latest entry**: per r4 NOTES suggestion #2 — guarantees mid_now and mid_back come from the same data source, eliminating r4's cache.quote_tick()-vs-buffer inconsistency.

**Lookback target**: `ts_back = buffer_latest_ts - LOOKBACK_NS` (not `order.ts_init - LOOKBACK_NS`). Together with the buffer-age guard (which ensures buffer_latest_ts is within 100ms of order.ts_init), this means we're measuring momentum over ~100ms ENDING at the buffer's view of "now", which is at most 100ms behind the order. The signal is a 100ms diff anchored to the buffer's most recent state.

**Diagnostics (round-2 criticizer demand)**: counters track every important pathway:
- `n_deltas`: total on_order_book_deltas callbacks
- `n_deltas_with_book`: deltas where the cache returned a populated book
- `n_orders_seen`: total on_order calls
- `n_closes`, `n_opens`: split by reduce-only flag
- `n_skips_cap`, `n_skips_adverse`: SKIP counts by gate
- `n_submits_passed_both`: SUBMITs that survived both gates
- `n_safe_submit_*` (7 buckets): SUBMITs forced by various defensive paths

The on_stop log line emits the full breakdown. If a future iteration needs to compare delivery densities, the raw counters are in the per-date logs.

**Hard-coded TICK_SIZE = 0.25 for MES**: instrument is fixed by config. Not parameterized.

**Reduce-only pass-through**: CLOSE (`is_reduce_only=True`) orders submit unconditionally. The mechanism only ever filters OPENs.

**No order modification**: SKIP or SUBMIT — never modify quantity, price, or order type. Quantity invariant preserved (same as base algo).

**on_reset**: clear buffer, subscriptions, and ALL diagnostic counters. Defensive (each backtest date runs in a fresh subprocess so reset is rarely needed in practice).

**Concerns**:
- **Dataset-density risk (round-3 MINOR #1)**: if the Databento glbx-mdp3 source is MBP-1 only, then the deltas may have the same effective density as quote_ticks (every TOB change emits one delta), and the channel switch will be inert. The diagnostic counter is designed to surface exactly this — n_deltas will be small if so. This is acceptable risk for a final-round attempt.
- **Warmup (round-3 MINOR #2)**: `cache.order_book(instrument_id)` may return None during the first few deltas of a session before the book is initialized. The `on_order_book_deltas` callback returns early in that case (no buffer append). Acceptable.
- **Wider outcome distribution (round-3 MINOR #3)**: realistic range is roughly [-3%, +13%] depending on how well delta-stream density approximates the offline MBP-1 stream. The staleness guards bound the worst case.
- **Look-ahead**: causality guard explicitly checks `buffer_latest_ts > order.ts_init` → SUBMIT. The buffer only contains deltas already delivered (= ts_event <= current sim time). The bisect lookup selects `<= buffer_latest_ts - LOOKBACK_NS`, never a future quote.

---

## Backtest Observations

**Metrics (train window, 12 dates)**:

| Metric | ptg-pc-r5 | position-tier-gate (base) | Delta |
|---|---|---|---|
| realized_pnl | $4,262.50 | $4,262.50 | **0.00%** |
| mean_slippage | 0.0 | 0.0 | 0.00% |
| sharpe_ratio | 17.62 | 17.62 | 0.00 |
| max_drawdown_pct | -1.73% | -1.73% | 0.00pp |
| win_rate | 37.20% | 37.20% | 0.00pp |
| trade_count | 90,433 | 90,433 | 0 (0.00%) |

vs_base_pnl_pct = **0.00%** (gate: ≥5.0% → FAIL on PASS criterion, but well within the close_margin_pct = 2.0% boundary).
vs_base_slippage_pct = **0.00%** (no regression).

**What drove improvement**: Nothing. The algorithm produced output BITWISE IDENTICAL to base position-tier-gate. The cap=1 gate fired the same number of skips on the same orders; the adverse-mom gate fired ZERO additional skips across all 12 dates. All metrics — realized_pnl, sharpe, max_drawdown, win_rate, trade_count, per-date trade counts — are exact equal to base.

**What underperformed**: The order-book-delta-backed adverse-mom mechanism. Possible causes (in order of likelihood given the bitwise-identical result):
1. **on_order_book_deltas not firing at all in this simulator/dataset.** If `subscribe_order_book_deltas` does not bind to the DBN replay's data stream (or the data backend doesn't translate MBP-1 messages into deltas), then on_order_book_deltas never runs, the buffer stays empty, and the cold-buffer safe-SUBMIT fires on every OPEN. The bitwise-identical result is consistent with this.
2. **on_order_book_deltas firing but cache.order_book() returning None.** If the cache doesn't maintain a reconstructed L2 book for the instrument (because nothing else subscribes), the buffer-append branch would be skipped on every callback. Same effective result.
3. **Buffer populated but every decision hits a staleness guard.** If the deltas are very sparse, the cold-buffer or no-lookback safe-SUBMIT would fire on every open. Same effective result.

The diagnostic counters were logged via `self.log.info` at on_stop but are NOT persisted to disk (only emitted to the Nautilus logger which is not captured by the backtest pipeline). To distinguish between these three causes, a follow-up run would need to either: (a) write the counters to a file in on_stop, or (b) parse the in-memory logger output.

**Hypothesis verdict**: **CONTRADICTED — mechanism is inert in this simulator.** The hypothesis was that switching from quote_ticks to order_book_deltas would raise delivery density and recover the offline +13.74% signal. The empirical result is that the algorithm behaves identically to base position-tier-gate, meaning the adverse-mom gate fires zero skips. Whichever of the three causes above is the actual reason, the conclusion is the same: the order-book-delta channel does not deliver the sub-second price history needed to compute a 100ms momentum signal in this backtest setup.

The bright side: the staleness guards worked exactly as intended — when the data was missing/stale, the algo defaulted to base behavior, bounding downside to 0% rather than r4's -3.14%. The criticizer's round-2 demand for staleness guards was vindicated.

**Suggested next attempt**: The position-tier-gate axis is effectively exhausted on this experiment. Five PC runs (r1 consensus filter inert; r2 loss-cooldown -6.1%; r3 winners-run -82%; r4 adverse-tick-flow via quote_tick -3.1%; r5 adverse-mom via book_deltas 0.0%) have all failed to beat the gate. Either: (a) write the diagnostic counters to disk in a follow-up minor revision (ptg-pc-r6 or backfill r5) to definitively diagnose WHICH of the three causes above is the reason — useful information for future researchers but unlikely to change the strategic conclusion; (b) pivot to a fundamentally different mechanism class (passive order types, order routing, or order timing/queuing) that does not rely on sub-second market microstructure measurement; (c) accept that position-tier-gate is at a local optimum on this strategy/cost-structure pair and use the remaining runs for different experimental questions.

