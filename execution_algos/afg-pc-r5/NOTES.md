# Algorithm Notes: afg-pc-r5

## Hypothesis

**Mechanism**: Time-decayed AFG with r2 chain state machine (single-variable ablation vs r2). At each open-order decision, compute weighted_flow = sum(signed_vol_i * exp(-(t_order - t_i)/tau_ns)) over all flow_deque entries with ts_event in (t_order - 10s, t_order], where tau = 5s (half-life ~= 3.47s). Skip BUY when weighted_flow <= -2.0, skip SELL when weighted_flow >= +2.0 (threshold IDENTICAL to base/r2). Directional-chain state machine preserved VERBATIM from r2: max_consecutive_skips=3, direction-change immediately force-submits and resets chain, reduce-only always submits, first-signal warm-up unconditional submit. Trade-tick subscription and deque maintenance identical to r2; only the gate evaluation function changes from raw _net_flow comparison to weighted recomputation at order time. Look-ahead-free: only prints with ts_event <= order.ts_init contribute.

**Inefficiency exploited**: The base rectangular window treats a 9.9s-old print identically to a 0.1s-old print, but adverse-selection from aggressor flow decays rapidly — what aggressors did 8 seconds ago is mostly already priced in. Recency weighting sharpens the gate to respond to currently-active flow rather than averaged stale flow, while still using older prints as context (down-weighted, not discarded).

**Why it survives costs**: Slippage is 0 in this simulator (zero fill-cost model); the only cost is foregone P&L from over-skipping. With threshold and chain held constant at r2's values, decay-weighting should reduce two failure modes: (a) false-positive skips when a stale 8s-old burst has already reversed; (b) false-negative submits when fresh adverse flow is diluted by older neutral flow in the unweighted sum. Net effect: more accurate skip targeting at approximately the same skip rate.

**Builds on**: afg-pc-r2 (the empirical winner). Sole change: rectangular weighting -> EWMA weighting at gate evaluation. All other r2 mechanics preserved verbatim: chain state machine, max_consecutive_skips=3, flow_threshold=2.0, window_seconds=10.0, reduce-only, first-signal warm-up, on_reset semantics.

**Alternatives considered**: (a) Linear/triangular decay — qualitatively similar but less smooth; exponential is the standard microstructure recency-weighting choice. (b) tau=window (10s) — too long, weights only ~37% drop at window boundary; defeats recency emphasis. (c) tau=1s — too short, effectively ignores anything older than 3s. (d) tau=window/2=5s — principled compromise: half-life ~3.5s gives strong recency emphasis while preserving meaningful context from the older half of the window. (e) Threshold rescaling — rejected per round-2 criticism to keep the ablation clean.

**Debate summary**: 3 rounds, outcome=CONVERGED. Key objections resolved: combined EWMA decay with r2's empirically-winning chain state machine (instead of stand-alone replacement), held threshold and chain knobs constant at r2's values for single-variable ablation, and chose tau=window/2=5s on principled half-life grounds.

---

## Implementation Decisions

- **Subclass approach**: Inherit r2's deque-maintenance + chain state machine; override only `_flow_is_adverse()` to recompute weighted_flow at decision time. Cleanest isolation of the changed variable.
- **Per-print weight**: `exp(-(t_order_ns - t_print_ns) / tau_ns)` with `tau_ns = 5 * 1_000_000_000`. Computed at evaluation time (not insertion) because the weight depends on the current order's timestamp.
- **O(N) eval cost**: Walking the deque per decision is O(N) where N = prints in the 10s window. For MES at typical futures cadence this is ~100-1000 prints — trivial latency, no caching needed.
- **Numerical care**: `t_order_ns - t_print_ns` is non-negative by construction (deque ordered chronologically, prune ensures all entries are within window). `exp(-x/tau)` for x in [0, 1e10 ns / 5e9 ns = 2.0] is bounded in [exp(-2), 1] ≈ [0.135, 1.0] — no overflow risk.
- **Quantity invariant**: never modify order.quantity. Only skip or submit.

**Concerns**:
- The deque could contain a print with ts_event > order.ts_init if the backtest delivers an order callback before a same-nanosecond trade tick (edge case). Pruning by `cutoff_ns = order.ts_init - window_ns` does not exclude that; we explicitly filter `t_print_ns <= order.ts_init` inside the weighted sum to be safe.
- No look-ahead: weights use only past timestamps; the deque at decision time only contains prints with ts_event <= order.ts_init (modulo the same-ns edge case handled above).

---

## Backtest Observations

**Raw numbers** (train window 2026-03-08 .. 2026-03-20, 12 dates):
- realized_pnl: 755.25 (base afg: 1255.50; r2: 1817.25 implied from r2's +600.8% vs simple=155.5)
- sharpe_ratio: 3.52 (base afg: 5.59)
- max_drawdown_pct: -0.0362 (base afg: -0.0332)
- win_rate: 0.3495 (base afg: 0.3549)
- trade_count: 97893 (base afg: 107198) — ~9k fewer fills, indicating decay-weighted gate skips MORE than r2/base
- mean_slippage: 0.0 (simulator floor)
- is_weighted_bps: 0.0553 (base afg: 0.0472) — worse implementation shortfall
- vs_base_pnl_pct: **-39.84%**
- vs_base_slippage_pct: 0.0%

**What drove improvement**: Nothing. The algorithm underperforms the base AFG on every meaningful metric.

**What underperformed**: The EWMA-weighted gate produces a different (sharper-on-recent-flow) skip distribution than r2's rectangular window. Empirically this distribution is worse: more skips overall (97.9k vs 107.2k fills, ~8.7% drop) with lower per-fill quality (is_bps 0.0553 vs 0.0472). The hypothesis assumed recency-weighting would reduce false-positive skips on stale flow; the data shows the opposite — the down-weighting of older context appears to remove useful low-frequency signal that the rectangular average captured, causing the gate to over-react to transient recent flow bursts and skip entries that would have been profitable.

**Hypothesis verdict**: CONTRADICTED. Decay-weighting along the principled tau=window/2 axis hurt rather than helped. The base/r2 rectangular window's apparent crudeness is actually doing useful smoothing — treating a 9s-old print with the same weight as a fresh print acts as a low-pass filter that suppresses overreaction to recent transient flow. This is consistent with the regime being mean-reverting at sub-10s horizons (something the base AFG's flat window implicitly assumes).

**Suggested next attempt**: Move orthogonal to the weighting-function dimension entirely. Two candidates: (a) keep r2's rectangular gate but make the threshold adaptive to recent flow volatility (sigma-normalized) — gates harder during calm periods, softer during volatile ones; (b) extend r2's chain state machine with a directional-persistence requirement (require N consecutive same-side strategy signals before allowing a force-submit on direction change) to suppress whipsaw force-submits.
