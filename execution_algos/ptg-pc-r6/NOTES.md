# Algorithm Notes: ptg-pc-r6

## Hypothesis

**Mechanism**: ROLLING-WINDOW WIN-RATE COOLDOWN, layered on position-tier-gate (cap=1) verbatim. The exec algorithm overrides on_position_closed() to receive position-close events (Nautilus standard hook — verified available on ExecAlgorithm base class; same hook r2 attempted but with a different trigger). On each position close, it pushes a boolean (is_win = realized_pnl > 0) into a rolling deque of length WR_WINDOW (default 100). On each on_order() for an OPEN that survives the cap=1 gate, if the deque is full AND the rolling win-rate (mean of the deque) is below WR_THRESHOLD (default 0.32), SKIP the OPEN. Otherwise SUBMIT. CLOSE orders (is_reduce_only=True) always submit unchanged. Warmup: until the deque is full, the cooldown is inactive (SUBMIT). On session reset (per-date subprocess), the deque is cleared.

**Inefficiency exploited**: Win-rate REGIME variation across the train window. Empirically pre-validated via offline analysis of position-tier-gate positions.csv across all 12 train dates (90,433 positions, total realized_pnl $4,262.50): the rolling 100-position win-rate ranges from ~20% to ~55% within each session, and the subset of OPENs preceded by a 100-position window with win-rate < 0.32 has CONCRETELY NEGATIVE aggregate PnL (-$188.75 over 23,019 trades = -$0.0082/trade, vs the overall +$0.047/trade). Skipping that subset yields kept_pnl=$4,451.25 = +4.43% vs base. Per-date pattern: HELPS on 7 of 12 dates (most prominently the high-volume late-window choppy days 20260316 +$106.5, 20260317 +$44.8, 20260319 +$22.5); HURTS on 2 of 12 (20260318 -$23.5, 20260320 -$27.8); 3 dates (20260308, 20260309, 20260310) have no skips because their session position count never fills the 100-position warmup. The signal is robust: nearby parameterizations all produce delta in [+2.8%, +4.7%] range. Why this works mechanically: the oracle (sigma=6.0, R^2~14%) has time-varying realized accuracy; in 100-position windows where it has achieved <32% win rate, it is in a noisier regime and the next signals are disproportionately likely to also lose.

**Why it survives costs**: Mean slippage = 0 and commissions = 0 in this simulator (verified from base position-tier-gate backtest-results.json). The mechanism only adds a SKIP condition on OPEN orders that survive the cap=1 gate — no order construction, no order modification, no new order types, no passive orders, no market-data subscriptions. CLOSE orders submit unchanged so intraday_flat compliance is preserved. Runtime overhead: O(1) per OPEN (running-sum maintained) + O(1) per close (one deque push/pop). No dependency on simulator-delivered sub-second market data — the signal source is the algorithm's own running record of CLOSED position outcomes, delivered via the on_position_closed hook which is verified working on ExecAlgorithm (r2 used the same hook and its -6.1% outcome confirmed the hook fires reliably).

**Builds on**: position-tier-gate (cap=1 retained verbatim as the first gate; rolling-WR cooldown is an additive SKIP gate applied AFTER cap=1 passes, only for OPEN orders). Structurally distinct from all 5 prior PC runs: r1 (consensus filter, inert); r2 (single-position loss-cooldown, -6.1% because losses are i.i.d. at the SINGLE-TRADE level); r3 (winners-run extend-close, -82%); r4 (adverse-mom via quote_tick, -3.1%); r5 (adverse-mom via book_deltas, 0.0%); and from round-1's chop-cooldown (empirically refuted as mechanically constant). This proposal differs by conditioning on the AGGREGATE win-rate over a 100-position rolling window — a noise-averaged regime signal that is NOT directly determined by either the oracle's fixed 1Hz cadence (uniform) or the per-trade pnl distribution (i.i.d. at single-trade level). The win-rate at the 100-position scale aggregates 100 i.i.d. trials and IS empirically regime-sensitive.

**Alternatives considered**: Empirically tested in offline pre-validation (deltas measured on the 12-date train window via positions.csv): (1) prior single position pnl<0 (r2 reproduction): -37.14%. (2) prior dur<2s AND prior pnl<0: -8.19%. (3) prior dur<2s only: -21.5%. (4) prior pnl < -2.5: -1.57%. (5) loss_streak>=3: -10.53%, >=5: -1.33%, >=7: -0.32%. (6) Late-session SKIP (criticizer suggestion): -0.2% to -0.7% across various N-minute thresholds. (7) UTC-hour filter (skip negative-pnl hours): +0.65% to +1.23%, all below gate. (8) Rolling-window total-pnl-sum threshold: all variants -8% to +0.7%. (9) Adjacent rolling-WR parameterizations: N=200 wr<0.30 (+2.76%, more bias-resistant); N=200 wr<0.35 (+4.67% headline but 5/4 help/hurt, less consistent than chosen N=100 wr<0.32 at 7/2). The chosen point optimizes empirical help/hurt consistency.

**Debate summary**: 2 rounds, outcome=CONVERGED on round 2. Round-1 BLOCKINGs (cap-block density signal is mechanically constant at ~1/sec because driven by oracle 1Hz cadence + deterministic netting; degenerate threshold-5-in-10s activates on ~100% of OPENs) empirically refuted via my own offline density measurement showing Pr(blocks_10s>=5) = 98-100% across all sampled dates. Round-2 pivoted to rolling-WR cooldown with full 30+ candidate empirical sweep. Round-2 PASS with acknowledged MAJOR residuals (offline-to-live feedback bias, parameter-search overfit risk, per-date concentration in high-volume dates, choice between N=100 wr<0.32 and N=200 wr<0.30 parameterizations) — none structural; downside bounded to delta=0 worst case.

---

## Implementation Decisions

**Gate ordering**: cap=1 check FIRST (cheapest, preserves base behavior), rolling-WR SKIP check SECOND (only on OPENs the cap would have submitted). CLOSE orders bypass both gates.

**Signal source — on_position_closed hook**: The deque is updated only in on_position_closed. The event provides position.realized_pnl which we convert to a boolean (is_win = realized_pnl > 0). r2 verified this hook fires reliably on ExecAlgorithm.

**Deque structure**: A `collections.deque(maxlen=WR_WINDOW)` of booleans (True/False). We also maintain a running integer count of wins (`self._n_wins_in_buf`) updated incrementally: increment when pushing True, decrement when an old True falls off the maxlen edge. This gives O(1) win-rate computation at each OPEN, avoiding O(N) sum() over the deque.

**Win-rate threshold check**: `if len(buf) == WR_WINDOW and (n_wins_in_buf / WR_WINDOW) < WR_THRESHOLD: SKIP`. Strict less-than per the empirical analysis (positions matching the boundary are kept).

**Default parameters**: WR_WINDOW=100, WR_THRESHOLD=0.32. Both configurable kwargs on the factory function for future tuning.

**Warmup behavior**: while the deque is not yet full (`len(buf) < WR_WINDOW`), the cooldown is inactive — every cap-passing OPEN submits. Empirically this means dates with fewer than ~100 cap-passing OPENs run as pure base PTG. On the train window, dates 20260308 (253 positions), 20260309 (757), 20260310 (436), 20260315 (340) will have early-session positions that all submit during warmup; only after 100 closes does the filter start contributing.

**Reduce-only pass-through**: CLOSE (`is_reduce_only=True`) orders always submit unconditionally — intraday_flat compliance, exits never blocked.

**No order modification**: SKIP or SUBMIT — never modify quantity, price, or order type. Quantity invariant preserved (same as base algo).

**on_reset**: clear the deque and reset the win count to 0. Each backtest date runs in a fresh subprocess so this is rarely needed in practice, but defensive.

**Position-state read for the cap=1 gate**: uses `self.cache.positions_open(instrument_id=...)` identical to the base position-tier-gate algorithm.

**Skipped positions are NOT added to the deque**: The deque is updated only on actual on_position_closed events. A skipped OPEN never creates a position and never fires PositionClosed. This is the intended behavior (the algorithm tracks ACTUAL trades it took, not hypothetical ones) but means the live sequence differs from the offline base-PTG sequence. This is the round-2 MAJOR #1 feedback-loop concern — see Concerns below.

**Concerns**:

- **Feedback-loop bias (round-2 MAJOR #1)**: The offline +4.43% pre-validation was computed on the base-PTG position sequence. In live, the deque only contains positions the algorithm DID NOT SKIP — a sequence biased toward higher win-rate (because skipping removes losers). The live rolling-WR will run HIGHER than the offline-computed WR, meaning the activation rate will be LOWER than the 25.5% offline figure. The realistic live delta could range from ~0% (filter barely activates) to the full +4.43% (if the WR signal is dominated by true regime structure not noise). The Backtest Observations section below will measure the live activation rate to falsify this.

- **Parameter-search overfit risk (round-2 MAJOR #2)**: The sweep of 30+ candidates produced deltas in [+0%, +4.7%]. The chosen point (N=100, wr<0.32) is the local optimum on the train window. Realistic OOS-expected delta is 50-70% of headline, i.e. +2% to +3%. Below the +5% gate.

- **Per-date concentration (round-2 MAJOR #3)**: 3 of 12 train dates contribute 0 delta (warmup-inactive); the +4.43% is concentrated in 4 high-volume late-window dates. OOS results depend on whether test dates resemble high-volume or low-volume train dates.

- **on_position_closed hook semantics for skipped positions (round-2 MAJOR #4)**: Resolved by design — skipped OPENs don't create positions, so they don't fire PositionClosed. The deque tracks only ACTUAL trades, which is intentional. The feedback loop above is the consequence.

- **Parameterization choice (round-2 MAJOR #5)**: N=200 wr<0.30 was a candidate alternative (more bias-resistant, lower headline at +2.76%). Sticking with N=100 wr<0.32 because the help/hurt ratio is stronger (7/2 vs 4/4) and the realistic outcome distribution covers PASS within close_margin (close = within 2% of the +5% gate).

- **Bounded downside (round-2 MINOR)**: Worst case is filter inactive (delta=0, matching r5). Cannot regress slippage or commissions (both 0). No -82% (r3) or -37% (r2 reproduction) catastrophe possible because activation rate is capped at ~25% offline and likely lower live.

- **No look-ahead**: The deque is updated only on on_position_closed events (strictly past). At on_order() time the deque reflects only closes that have already happened — no future information.

---

## Backtest Observations

**Headline metrics** (12-date train window, vs base position-tier-gate):

| Metric | Base PTG | ptg-pc-r6 | Delta |
|---|---|---|---|
| realized_pnl | $4,262.50 | $1,785.25 | -$2,477.25 (-58.12%) |
| sharpe_ratio | 17.62 | 7.31 | -10.31 |
| max_drawdown_pct | -0.0173 | -0.0029 | improved (smaller) |
| win_rate | 0.3720 | 0.4556 | +8.4 pp |
| trade_count | 90,433 | 6,875 | -92.4% |
| mean_slippage | 0.00 | 0.00 | 0 |
| total_commissions | $0 | $0 | 0 |
| is_weighted_bps | 0.0389 | 0.0367 | slightly better |
| vs_baseline_pnl_pct | +2632.4% | +1044.4% | -1588 pp |
| vs_baseline_is_bps | -0.039 | -5.592 | improved (more negative = better IS) |

**vs base computed per spec**:
- vs_base_pnl_pct = (1785.25 - 4262.5) / |4262.5| * 100 = **-58.12%**
- vs_base_slippage_pct = 0.0 (both base and algo have mean_slippage=0.0)

**What drove improvement**: Nothing on the headline objective — realized PnL collapsed by 58%. Per-trade win-rate did rise (+8.4 pp), suggesting the WR filter does deselect some loser-cluster regimes as hypothesized. is_weighted_bps modestly improved (0.039 -> 0.037) and IS-vs-baseline improved meaningfully (-0.04 -> -5.59 bps), so the kept trades are higher quality per-unit. The retained subset is more disciplined.

**What underperformed**: Trade-count collapse is the dominant effect — only 6,875 positions vs 90,433 base (7.6% retention, i.e. the filter SKIPPED ~92% of OPENs in live, not the ~25% predicted offline). The realized-PnL collapse tracks the trade-count collapse roughly linearly (algo retains 7.6% of trades and 41.9% of PnL — slightly better per-trade economics but nowhere near enough to compensate for volume loss). Sharpe halves (17.62 -> 7.31) because PnL dispersion shrinks faster than mean.

**Hypothesis verdict**: **CONTRADICTED**. The offline +4.43% pre-validation badly missed the live outcome (-58.12%). The mechanism's failure mode is the OPPOSITE of what the round-2 Criticizer's feedback-loop concern predicted. The Criticizer hypothesized that skipping losers would RAISE the live rolling-WR above the offline-computed WR (because the deque tracks only kept positions, biased toward winners), thus LOWERING the activation rate. Instead, the live activation rate is MUCH HIGHER than offline (~92% vs ~25%). Why: in live, every SKIP removes a future position-close event that would have updated the deque, so the deque fills MUCH more slowly — and once it does fill, removing losers from future closes is overwhelmed by the fact that the deque now updates only on the retained (higher-WR) subset. But the threshold check `wr < 0.32` compares a STATIC threshold against a dynamic distribution. Because the algo skips OPENs when WR is *low*, the moments it submits are moments when WR has just risen above 0.32 — but each retained position resolves with a fresh win/loss outcome with the oracle's true ~45% per-trade winrate (matching the observed win_rate=0.4556), which is only narrowly above 0.32. Any short run of losses pushes the rolling-WR back below 0.32 and the filter shuts off OPENs for an extended period (positive feedback: no new positions means no new close events means the deque doesn't refresh). Effectively the algorithm enters extended "frozen" stretches where it submits almost nothing, especially on the high-volume late-window dates where most of base PTG's PnL comes from.

Both round-2 BLOCKING-class concerns the Criticizer raised (feedback-loop bias, per-date concentration) materialized — but in the opposite direction (signal got AMPLIFIED, not damped) and with much larger magnitude than acknowledged. The +4.43% offline pre-validation was structurally invalid.

**Suggested next attempt**: The position-tier-gate axis appears genuinely exhausted on the OPEN-side filtering class — 6 PC runs (r1 inert, r2 -6%, r3 -82%, r4 -3%, r5 inert, r6 -58%) plus the round-1 chop-density attempt have all failed. The robust empirical finding is that base PTG is at a local optimum on the strategy/cost-structure pair. A genuinely different mechanism class is required: e.g., a CLOSE-side intervention (early-exit at adverse intra-position price action), or modifying order construction (limit at top-of-book instead of market) to capture spread on entries — but the simulator has slippage=0 and commissions=0 so the latter is a no-op. Highest-leverage single change a future run could try: ABANDON the OPEN-side-filter class entirely and either (a) admit the experiment line is exhausted and report it, or (b) pivot to a CLOSE-side mechanism such as adaptive-hold-time CLOSE-skip (extend hold on positions whose mark-to-market is improving), which would directly modify the oracle's hold-duration distribution rather than its entry-frequency distribution.
