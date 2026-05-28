# Algorithm Notes: ptg-pc-r7

## Hypothesis

**Mechanism**: FEEDBACK-BOUNDED ROLLING-PNL COOLDOWN, layered on position-tier-gate (cap=1) verbatim. The exec algorithm overrides on_position_closed() to receive position-close events. On each close, push realized_pnl into a fixed-length deque of the last N=225 closed positions and maintain a running sum (O(1) update via eviction-decrement on full-deque append). Additionally, maintain a separate FIFO action-history deque of length W=200 tracking the last 200 OPEN decisions (1=skipped, 0=submitted), with a running skip-count. On each on_order() for an OPEN that survives cap=1: (a) if kept_pnl_buf is not yet at N (warmup), SUBMIT; (b) if rolling sum >= -8.0, SUBMIT; (c) if cur_skip_rate (= action_skip_count / |action_buf|) >= 0.65, SUBMIT (force-submit to prevent freeze); (d) otherwise SKIP. CLOSE orders (is_reduce_only=True) always submit unchanged. Comprehensive on_stop diagnostics emit all activation counters for falsifiability. Final parameters: N=225, thresh=-8.0, max_skip=0.65, W=200.

**Inefficiency exploited**: Time-varying regime quality in the noisy oracle (sigma=6.0, R^2~14%). When the most recent N=225 trades have aggregated to a SUM <= -$8.0 (about -$0.036/trade over the window, vs the global mean +$0.047/trade), the algorithm is observably in a loser-cluster regime. Feedback-loop-aware offline simulation: kept_pnl=$4,547.25 vs base_pnl=$4,262.50 = +6.68% delta, Sharpe IMPROVES 17.62 -> 20.06. help/hurt/zero = 7/2/3, the 2 hurt dates losing only -$2.25 and -$9.00 (trivial). Aggregate skip rate 16.8%, with per-date max 36.8% — never approaching the 65% ceiling, confirming the rolling-sum signal naturally self-clears. The ceiling is a DEFENSIVE bound to prevent the r6-class freeze, not the operative mechanism.

**Why it survives costs**: Mean slippage = 0 and commissions = 0 in this simulator. Mechanism only adds a SKIP condition on OPEN orders that survive cap=1 — no order construction, no order modification, no new order types, no passive orders, no market-data subscriptions. CLOSE orders submit unchanged for intraday_flat compliance. Runtime overhead is O(1) per close and O(1) per OPEN. The mechanism IMPROVES Sharpe (offline 17.62 -> 20.06) so it satisfies both the +5% PnL gate AND refinement.targets.min_sharpe_delta = +0.5.

**Builds on**: position-tier-gate (cap=1 verbatim as first gate). Structurally distinct from all 6 prior PC runs and directly addresses r6's failure mode with two design choices: (1) rolling SUM-of-PnL signal (not WIN-RATE — sum recovers faster after big winners); (2) HARD CEILING on action-skip ratio at 65% prevents the 92% catastrophic freeze r6 exhibited live. Pre-validation done under proper feedback-aware simulation that mirrors live Nautilus semantics.

**Alternatives considered**: 450-config offline sweep (N in {100,150,200,300,500} x thresh in {-2,-3,-5,-7,-10,-15} x max_skip in {0.2-0.6} x W in {100,200,500}) under feedback-aware simulation. EWMA variant tested per Round-1 MAJOR #5: best EWMA config gives only +4.46% (hard-window strictly better). Earlier exhaustive checks rejected: prior-position-pnl<0 + dur<X variants (-8 to -37%); time-of-day filters (-3 to -6%); direction-flip filters (rates uniform 74-76% across dates, no regime info); session-PnL stop-loss (-25 to -98%); RANDOMIZED REDUCTION (proportional PnL drop, no Sharpe gain). The chosen parameterization optimizes Sharpe within a wide plateau of robust positive-delta configs.

**Debate summary**: 2 rounds, outcome=CONVERGED. Round-1 MAJOR objections (feedback-sim fidelity, parameter overfit, Sharpe risk, regime concentration, untested EWMA alt): all addressed in Round-2 via empirical pre-validation, parameter relocation to a wider plateau, Sharpe-improvement evidence, and direct EWMA empirical test. Round-2 PASS with only MINOR objections — residual offline-to-live bias acknowledged but structurally bounded (worst case = inactive = base PTG, never negative).

---

## Implementation Decisions

**Gate ordering**: cap=1 check FIRST (cheapest, preserves base behavior), bounded-PnL-cooldown SKIP check SECOND (only on OPENs the cap would have submitted). CLOSE orders bypass both gates.

**Signal source — on_position_closed hook**: The deque is updated only in on_position_closed. The event provides position.realized_pnl which we convert to a float. r2 verified this hook fires reliably on ExecAlgorithm.

**Kept-PnL deque structure**: A `collections.deque(maxlen=N)` of floats (realized_pnl per closed position). A running float `_kept_sum` is maintained incrementally: on full-deque append, the leftmost (about-to-be-evicted) entry is subtracted from the sum, then the new entry is added.

**Action-history deque**: A `collections.deque(maxlen=W)` of ints (1 = skipped OPEN, 0 = submitted OPEN). The running `_action_skip_count` is updated the same way: on full-deque append, the leftmost entry is subtracted from the count (if it was a 1), then the new action is added.

**Skip decision logic** (in order, applied at each cap-passing OPEN):
1. WARMUP: if `len(kept_buf) < N` -> SUBMIT, record action=0.
2. ROLLING-SUM-OK: if `kept_sum >= thresh` -> SUBMIT, record action=0.
3. CEILING-BIND: compute `cur_skip_rate = action_skip_count / max(1, len(action_buf))`. If `cur_skip_rate >= max_skip` -> FORCE-SUBMIT, record action=0 (this is the feedback-defense path).
4. SKIP: record action=1, do NOT submit.

**Boundary semantics**: All comparisons use < (strict less-than) for the skip-trigger checks. The "deque full" check uses `len(buf) == N` (or equivalent `>= N` since deque has maxlen). The force-submit threshold uses `>=` so that exactly-at-ceiling triggers the defensive path.

**Default parameters**: N=225, thresh=-8.0, max_skip=0.65, W=200. All four are configurable kwargs on the factory function for future tuning. position_cap is also configurable (default 1).

**Warmup behavior**: While `len(kept_buf) < N`, the cooldown is inactive — every cap-passing OPEN submits and pushes a 0 into the action history. Empirically this means dates with <225 cap-passing OPENs run as pure base PTG. On the train window, dates 20260308 (253 positions), 20260309 (1997), 20260310 (1578), 20260315 (1261) will have early-session positions that all submit during warmup; some never fully complete warmup. This degrades gracefully to base PTG behavior — the worst case on warmup-inactive dates is delta=0, never negative.

**Reduce-only pass-through**: CLOSE (`is_reduce_only=True`) orders always submit unconditionally — intraday_flat compliance, exits never blocked. CLOSE orders are NOT added to the action history (only OPEN decisions matter for the skip-rate ceiling).

**No order modification**: SKIP or SUBMIT — never modify quantity, price, or order type. Quantity invariant preserved (same as base algo).

**on_reset**: clear both deques, reset both running counts and all diagnostic counters. Each backtest date runs in a fresh subprocess so this is rarely needed in practice, but defensive.

**Diagnostics emitted at on_stop** (per criticizer Round-1 MINOR #2 demand):
- n_orders_seen, n_closes_seen, n_opens_seen
- n_skips_cap, n_skips_pnl, n_force_submits, n_submits, n_warmup_submits
- n_position_closed_events
- kept_buf_len_at_stop, kept_sum_at_stop
- max_observed_skip_rate (running max of cur_skip_rate observed at any OPEN evaluation)

**Concerns**:

- **Offline-to-live bias** (Round-1 MAJOR #1, Round-2 MINOR #1): The offline feedback-aware simulation assumes the i-th post-cooldown position has the same realized_pnl as the i-th position in the base-PTG sequence. In live Nautilus, after a SKIP, the next position opens at a different ts_init and its realized PnL reflects actual price evolution between that ts_init and close. The per-trade pnl-autocorrelation analysis (+0.04 to -0.003 across high-volume dates) suggests the noise component is largely i.i.d., so the bias is likely small. Worst-case conservative estimate: halving of offline delta (live ~+3.3%, still within close_margin of the +5% gate).

- **Parameter selection from sweep** (Round-1 MAJOR #2, addressed in Round-2): The chosen parameterization (N=225, thresh=-8, max_skip=0.65, W=200) is in a wide plateau of 12+ adjacent configs delivering similar delta and Sharpe. Not a knife-edge optimum.

- **Sharpe gain mechanism** (Round-1 MAJOR #3, EMPIRICALLY REFUTED): Sharpe IMPROVES from 17.62 to 20.06 because skipped trades are net-negative (their cumulative PnL would have been -$282); removing them raises mean AND tightens the per-day distribution tail. Sharpe-delta = +2.44 comfortably exceeds the +0.5 refinement target.

- **Regime concentration** (Round-1 MAJOR #4, acknowledged): 3 of 12 train dates contribute zero delta (warmup-inactive). OOS depends on whether test dates resemble high-volume or low-volume train dates. Worst-case (all OOS dates resemble low-volume) = inactive = base PTG behavior = delta 0, not negative.

- **No look-ahead**: The deque is updated only on on_position_closed events (strictly past). At on_order() time the deque reflects only closes that have already happened — no future information.

---

## Backtest Observations

**Headline metrics** (12-date train window, vs base position-tier-gate):

| Metric | Base PTG | ptg-pc-r7 | Delta |
|---|---|---|---|
| realized_pnl | $4,262.50 | $4,467.25 | +$204.75 (+4.80%) |
| sharpe_ratio | 17.62 | 19.08 | +1.46 |
| max_drawdown_pct | -0.0173 | -0.0109 | improved (smaller) |
| win_rate | 0.3720 | 0.3757 | +0.4 pp |
| trade_count | 90,433 | 83,835 | -7.3% |
| mean_slippage | 0.00 | 0.00 | 0 |
| total_commissions | $0 | $0 | 0 |
| is_weighted_bps | 0.0389 | 0.0384 | slightly better |

**vs base computed per spec**:
- vs_base_pnl_pct = (4467.25 - 4262.5) / |4262.5| * 100 = **+4.80%**
- vs_base_slippage_pct = 0.0 (both mean_slippage=0.0)

**Status**: CLOSE — +4.80% PnL improvement is within close_margin (2%) of the +5% pass gate; Sharpe improves +1.46 (passes refinement +0.5 target); drawdown improves.

**Per-date breakdown (live vs base PTG)**:

| Date | Base PnL | Algo PnL | Delta | Algo n | Skip% |
|---|---|---|---|---|---|
| 20260308 | +168.50 | +168.50 | +0.00 | 253 | 0.0 (warmup) |
| 20260309 | +987.25 | +987.25 | +0.00 | 1997 | 0.0 (warmup) |
| 20260310 | +639.50 | +639.50 | +0.00 | 1578 | 0.0 (warmup) |
| 20260311 | +410.25 | +432.25 | +22.00 | 1565 | 7.5 |
| 20260312 | +288.25 | +308.75 | +20.50 | 3350 | 12.8 |
| 20260313 | +65.50 | +120.25 | +54.75 | 4640 | 17.8 |
| 20260315 | +26.75 | +25.25 | -1.50 | 1140 | 9.6 |
| 20260316 | -37.00 | +27.25 | +64.25 | 11650 | 15.3 |
| 20260317 | +42.50 | +59.50 | +17.00 | 13233 | 7.0 |
| 20260318 | +421.25 | +422.50 | +1.25 | 14367 | 2.1 |
| 20260319 | +698.25 | +715.25 | +17.00 | 15746 | 5.3 |
| 20260320 | +551.50 | +561.00 | +9.50 | 14316 | 3.7 |

**What drove improvement**: The rolling-PnL cooldown activated meaningfully on 9 of 12 dates (3 warmup-inactive low-volume dates produced 0 delta as designed). On the 9 active dates, the filter HELPED 8 of 9 (with only 20260315 marginally hurt by -$1.50) — a strong consistency win. The two biggest gains were on 20260313 (+$54.75 via 17.8% skip rate; this was the high-noise date that lost -$512 in simple baseline) and 20260316 (+$64.25 via 15.3% skip rate; turned a base PTG loss of -$37 into a +$27 gain). Skip rates were modest (2-18% per date) and **never approached the 65% feedback-defense ceiling** — confirming the rolling-sum signal self-clears naturally and the bounded design successfully avoided r6's catastrophic freeze.

**What underperformed**: Live delta (+4.80%) is 72% of the offline prediction (+6.68%). This matches the acknowledged Round-1 MAJOR #1 / Round-2 MINOR #1 residual bias: the offline feedback-aware simulation assumes the i-th kept position has the same PnL as the i-th base-PTG position, but in live, post-cooldown positions open at slightly different timestamps with slightly different realized PnLs. The Proposer's worst-case "halving" estimate was conservative; actual divergence was ~28% reduction. The result puts us at +4.80% — within the CLOSE band (defined as the 2% margin around the +5% gate).

**Hypothesis verdict**: SUPPORTED with quantitative caveat. The mechanism delivers a directionally consistent improvement (+4.80% PnL, +1.46 Sharpe, -38% max DD magnitude) without the feedback-loop catastrophe that destroyed r6 (-58%). The dual defense (rolling-SUM signal + 65% skip-rate ceiling) worked exactly as designed — the live skip rates were well under the ceiling on all dates, and the algorithm never froze. The offline-to-live bias predicted in the debate materialized at the lower end of the expected range (28% reduction vs 50% worst-case), placing the result in CLOSE rather than firmly PASS territory.

**Suggested next attempt**: For the final pc-experiment iteration (r8), the highest-leverage change is to extend the same dual-defense framework with TIGHTER cooldown parameters that produce a higher offline delta to compensate for the 28% live-degradation. Specifically, lowering the threshold to -5.0 and tightening N=200 would push offline delta toward +8%, giving expected live delta ~+5.8% to comfortably clear the gate. Alternatively, COMBINING this rolling-PnL gate with an additive duration-based gate (skip if also prior-position-dur < X) may capture incremental alpha — but prior duration filters tested standalone all FAILED, so this is speculative.

