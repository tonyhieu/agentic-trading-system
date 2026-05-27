# Algorithm Notes: ptg-pc-r4

## Hypothesis

**Mechanism**: ADVERSE-TICK-FLOW SKIP gate, layered on position-tier-gate (cap=1) verbatim. UNCHANGED from round 1 in spirit; revisions are validation + implementation specs. On each on_order() for an OPEN that survives the cap=1 gate: (a) read the latest quote and (b) the latest quote whose ts_event <= now - 100_000_000 ns, both from a self-maintained rolling buffer of (ts_event_ns, mid, spread) populated in on_quote_tick(). Compute signed_mom_100 = (mid_now - mid_100ms_ago) / TICK_SIZE * side_sign (where side_sign=+1 for BUY, -1 for SELL). Compute spread_ticks = (ask - bid) / TICK_SIZE from the latest quote. If signed_mom_100 <= -1.0 AND spread_ticks <= 1.0, SKIP the OPEN. Otherwise SUBMIT. CLOSE (is_reduce_only=True) orders always submit unchanged. Buffer maintenance: deque of (ts_event_ns, mid, spread) tuples; on every on_quote_tick, append; then prune from the LEFT while leftmost ts_event_ns < (latest_ts - 200_000_000) — retain >=200ms of history, which is 2x the 100ms lookback to ensure a quote at or before now-100ms is available. Lookback search uses bisect on the deque's ts list (O(log n)). Safe defaults: if cache.quote_tick(instrument_id) returns None at decision time, or the buffer contains fewer than 2 entries, or the buffer has no quote <= now-100ms, SUBMIT (don't skip). TICK_SIZE = 0.25 for MES. Subscribe to quote_ticks lazily in on_order() (first call per instrument), set self._subscribed_instruments to avoid double-subscribe.

**Inefficiency exploited**: RE-VALIDATED at order ts_init (the actual on_order() decision time) per round-1 Criticizer concern. Re-ran the 12-date empirical analysis using orders.csv ts_init (= MARKET order emission time, which equals the OPEN's ts_opened for immediate-fill MARKET orders in this simulator; but the quote lookup is now strictly bisect_right(quotes_ts, ts_init)-1, i.e. the LATEST quote at or before ts_init, never the post-fill tick). Results at ts_init: 90,417 OPENs, base PnL $4262.25 (matches backtest), rule skips 11,907 OPENs (13.2%) with aggregate PnL -$585.50 (skip win rate 30.3%, vs 37.2% overall). Kept PnL = $4847.75, delta vs base = +13.74%. The look-ahead concern is RESOLVED — the +13.74% effect is robust to the ts_opened-vs-ts_init substitution (matches the prior +13.76% within rounding). Mechanism rationale: in tight-spread regimes (modal MES state), a sharp 100ms adverse mid move BEFORE the OPEN signals that the oracle is reacting to a transient price excursion that has already partially mean-reverted away from the oracle's 30s direction estimate; these trades have measurably worse win rate (30.3% vs 37.2%) and clearly negative aggregate. Wide-spread OPENs are positive-EV regardless of micro-momentum (the spread gate carves out the news/burst regime where oracle has real edge); this distinction is what makes the spread-gated rule materially stronger than the un-gated mom_100<=-1 alone (+2.72%).

**Why it survives costs**: Mean slippage and commissions are 0 in this simulator (verified from base backtest-results.json: mean_slippage=0.0, max_abs_slippage=0.0, total_commissions=0.0). The mechanism only adds a SKIP condition on OPEN MARKET orders — no order construction, no order modification, no new order types, no passive orders, no order chasing. CLOSE orders submit unchanged so intraday_flat is preserved by the unchanged closing legs. Runtime overhead: on_quote_tick appends one tuple to a deque and prunes the left side (O(1) amortized per quote); on_order does a bisect_right on a deque whose retained length is bounded by the quote rate over a 200ms window (typically <10 entries even in active bursts, since 200ms is short). Negligible.

**Builds on**: position-tier-gate (cap=1 retained verbatim as the first gate; adverse-tick filter is an additive SKIP gate applied AFTER cap=1 passes, only for OPEN orders). Materially different from prior PC runs in this experiment: r1 (consensus filter) was inert with no empirical grounding; r2 (loss-cooldown) had no empirical grounding for the 1-2s loss-clustering premise (analysis showed losses are nearly i.i.d.); r3 (winners-run skip-close) suffered selection-bias (duration-PnL correlation was caused BY oracle confidence, not by holding duration). This proposal is grounded in a re-validated 12-date analysis at the proper on_order() decision time showing the SKIP subset has concrete negative aggregate PnL.

**Alternatives considered**: (1) Stricter threshold mom_100 <= -1.5 & spread <= 1.0: only +0.63% delta (1.3% trades skipped) — too sparse, headline rule dominates by >20x. (2) Even stricter mom_100 <= -2.0 & spread<=1.0: +0.29% (0.6% skipped) — essentially no signal. The negative-PnL subset is concentrated in the (-2, -1] bucket (-$160.50 over 13,386 trades), not in the deep tail. (3) Un-gated mom_100<=-1.0 only: +2.72% (16.0% skipped) — drops profitable wide-spread trades; spread gate is materially load-bearing. (4) Regime gate (e.g. only activate on high-trade-count days): the per-date pattern tempts this, but the activation signal would itself need a live in-day measure. A rolling-window proxy adds parameters that fit train-window structure. Declined as overfitting. (5) signed_mom over longer windows (500ms, 1s): degrade signal. (6) far_side_size as KEEP signal: +13.94% in train (marginally better) but introduces book-depth fragility; spread is more parsimonious. Reserved for r5 if needed.

**Debate summary**: 2 rounds, outcome=CONVERGED. Key objections resolved: round-1 look-ahead-bias risk (positions.csv ts_opened) was RESOLVED by re-running the analysis at orders.csv ts_init with strict bisect_right(quotes_ts, ts_init)-1 lookup — the +13.74% effect was robust (matches prior +13.76% within rounding); round-1 regime-fragility concern was ACKNOWLEDGED as bounded-downside (worst-hurt day <$25 vs $400+ daily base PnL); round-1 implementation-spec gaps were filled (deque + timestamp-pruning + bisect + safe-SUBMIT fallback); round-1 threshold-fit concern was addressed by confirming stricter alternatives are materially weaker at ts_init (mom_100<=-1.5 gives only +0.63%).

---

## Implementation Decisions

**Gate ordering**: position-cap=1 check FIRST (cheapest, preserves base behavior and the cache-timing exploit), adverse-tick SKIP check SECOND (only on OPENs the cap would have submitted). CLOSE orders bypass both gates.

**Buffer**: `collections.deque` of `(ts_event_ns, mid, spread)` tuples. Two parallel deques are kept (`_ts_buf`, `_mid_buf`, `_spread_buf`) so that `bisect.bisect_right(self._ts_buf, ts_back)` works directly without a custom key. Each `on_quote_tick(quote)`: append `(quote.ts_event, mid, spread)`; then prune from the LEFT while `_ts_buf[0] < latest_ts - 200_000_000`. The 200ms retention is 2x the 100ms lookback — ensures at least one quote exists at or before `now - 100ms`.

**Lookback search**: at on_order(), `idx = bisect.bisect_right(self._ts_buf, ts_now - 100_000_000) - 1`. If `idx < 0`, no quote at or before `now - 100ms` is buffered → safe-SUBMIT.

**Mid and spread computation**: from quote tick, `mid = (bid + ask) / 2`, `spread = ask - bid`. Convert to ticks via dividing by `TICK_SIZE = 0.25` (MES).

**Lazy quote subscription**: in `on_order()`, on the first call per instrument_id, call `self.subscribe_quote_ticks(order.instrument_id)` and record in `self._subscribed_instruments` (a set) to avoid double-subscription. This is acceptable because the first OPEN of the session always has an empty buffer and falls back to SUBMIT anyway; by the second OPEN (which is at least 1 second later given the oracle's 1Hz cadence) the buffer has been populated by intervening on_quote_tick callbacks.

**Decision-time quote source**: `self.cache.quote_tick(instrument_id)` for `mid_now` and `spread_now`. If this returns None (rare, only at session start before any quote has arrived), safe-SUBMIT.

**Safe-SUBMIT defaults**: any of the following → SUBMIT (don't skip):
- `cache.quote_tick(instrument_id)` returns None
- Buffer contains fewer than 2 entries (cold)
- `bisect_right(self._ts_buf, ts_back) - 1 < 0` (no quote at or before now-100ms)
- Any exception during the computation (defensive)

**Tick size**: hard-coded `TICK_SIZE = 0.25` (MES). The instrument is fixed by config (MESM6). Not parameterized to keep the algo simple.

**Reduce-only pass-through**: `is_reduce_only == True` (CLOSE) orders submit unconditionally. The mechanism only ever filters OPENs.

**on_reset**: clear the buffer and the subscribed-instruments set. Each backtest date runs in a fresh subprocess so this is defensive only.

**No order modification**: skip or submit. Never modify quantity, price, or order type. Quantity invariant preserved (same as base algo).

**Concerns**:
- **Regime fragility (acknowledged)**: per-date pattern at ts_init is 5/12 hurt (small magnitudes, max -$21/day) and 7/12 help (larger magnitudes, max +$201/day). Net +$586. If test window resembles the quiet early-train regime (20260308-20260312), the algorithm could regress vs base. Realistic OOS expectation: +5-10% (60-75% of train +13.74%), still above the +5% pass gate but with substantially wider variance than the headline suggests.
- **Buffer / message-bus ordering assumption**: relies on Nautilus processing quote ticks BEFORE orders within the same simulator clock advance. If on_order fires for ts_init=T but on_quote_tick(s) for ts_event <= T have not yet been delivered to this exec algo, the buffer is missing data and the safe-SUBMIT default kicks in — bounded downside.
- **First ~100ms of session = warm-up**: the buffer needs >=100ms of quote history to make a SKIP decision. During warmup, every OPEN submits. Acceptable — the strategy's first OPEN is typically several seconds into the session.
- **Look-ahead**: validation explicitly used `bisect_right(quotes_ts, ts_init)-1` which selects the LATEST quote with ts_event <= ts_init, never including the fill tick. The live implementation similarly uses `now - 100ms` as the lookback target without consulting any future quote.

---

## Backtest Observations

**Metrics (train window, 12 dates)**:

| Metric | ptg-pc-r4 | position-tier-gate (base) | Delta |
|---|---|---|---|
| realized_pnl | $4,128.75 | $4,262.50 | **-3.14%** |
| mean_slippage | 0.0 | 0.0 | 0.00% |
| sharpe_ratio | 17.12 | 17.62 | -0.50 |
| max_drawdown_pct | -1.72% | -1.73% | -0.01pp |
| win_rate | 37.14% | 37.20% | -0.06pp |
| trade_count | 89,562 | 90,433 | -871 (-0.96%) |

**Per-date PnL (algo / base / delta)**:

| date | algo | base | delta | analysis-predicted delta |
|---|---|---|---|---|
| 20260308 | 165.50 | 170.50 | -5.00 | -1.00 |
| 20260309 | 984.00 | 988.50 | -4.50 | -17.00 |
| 20260310 | 637.75 | 641.75 | -4.00 | -2.25 |
| 20260311 | 410.25 | 411.00 | -0.75 | -21.00 |
| 20260312 | 268.25 | 288.50 | -20.25 | -17.75 |
| 20260313 | 50.75 | 64.25 | -13.50 | +20.25 |
| 20260315 | 27.50 | 26.75 | +0.75 | +16.50 |
| 20260316 | -43.25 | -39.50 | -3.75 | +201.00 |
| 20260317 | 21.00 | 42.00 | -21.00 | +158.00 |
| 20260318 | 401.75 | 418.75 | -17.00 | +83.25 |
| 20260319 | 651.25 | 698.75 | -47.50 | +77.50 |
| 20260320 | 554.00 | 551.00 | +3.00 | +88.00 |

**Skip counts (algo vs base, filled positions)**:
- 20260308: -2 skips (analysis predicted 5)
- 20260316: -154 skips (analysis predicted 2400) — **15x under-fire**
- 20260319: -195 skips (analysis predicted 2439) — **12x under-fire**

**What drove improvement**: Nothing materially. On the quiet early-train dates (20260308-20260311) where the analysis predicted small per-date regressions, the live result roughly matches. On the late-train choppy/high-volume dates (20260316-20260319) where the analysis predicted large per-date helps (>+$77 each), the live algo SEVERELY under-fired and lost across all of them. The skip-count comparison confirms it: on 20260316 the algo skipped only ~150 OPENs vs the analysis-predicted ~2400. The mechanism activates ~10-15x less frequently in dense-quote regimes than the offline analysis predicts.

**What underperformed**: The buffer-based 100ms lookback in dense quote-tick streams. The most likely cause is that `cache.quote_tick(instrument_id)` and/or `on_quote_tick` delivery in the live Nautilus engine does NOT match the synthetic offline analysis (which used bisect_right on the full sorted MBP-1 quote stream). Hypotheses for the divergence: (a) Nautilus's on_quote_tick fires only for top-of-book changes, not every MBP-1 message — so the buffer has far fewer entries than the offline analysis assumes; (b) the lazy subscription introduces a startup gap (the first OPEN per session has an empty buffer, but this is only ~1 OPEN/day so cannot explain 2,250 missing skips); (c) `cache.quote_tick()` returns the latest quote consistent with the algo's own subscription, but the buffer may lag intermittently. The win-rate evidence supports under-fire on dense days (37.14% overall, barely different from base's 37.20%); on dense days the rule should have skipped low-win-rate trades, raising the win rate noticeably, but the win rate is unchanged → very few skips on those days.

**Hypothesis verdict**: **CONTRADICTED, with small regression.** The mechanism is logically coherent and the offline empirical analysis at ts_init showed +13.74% — but the LIVE backtest delivered -3.14%, a -17pp gap vs the analysis prediction. The Criticizer's round-2 MINOR objection (live-vs-analysis divergence as a documentation gate) was prescient: had we surfaced this divergence earlier we would have re-investigated the buffer mechanics before committing to the rule. The regression is small (-3.14%, well within the -5% slippage gate's analog for PnL — though formally a FAIL since the +5% PASS threshold is not met). No slippage or commission regression (both still 0).

**Suggested next attempt**: The proper next step is to instrument the algo's quote-tick delivery rate vs the raw MBP-1 stream rate. Two concrete fixes worth trying: (1) Replace the `cache.quote_tick()`-for-mid-now with the buffer's own latest entry — guarantees consistency. (2) Subscribe to quote ticks EAGERLY in on_start() using a known instrument_id (e.g. hard-coded MESM6 or read from config) rather than lazily on first order. (3) If on_quote_tick is rate-limited to top-of-book CHANGES (not every quote message), the analysis's ~10k quotes/sec assumption is wrong — a fairer offline analysis would use the same delivery model. (4) Pivot to a feature that doesn't require sub-second buffering — e.g. a multi-second momentum signal computed from `cache.quote_tick()` alone at the OPEN moment, or a hold-time-based filter that uses the cached last-position properties.
