# Algorithm Notes: afg-pc-r3

## Hypothesis

**Mechanism**: Magnitude-Conditional Chained Gate (MCCG v2). EDA-informed revision. Preserves base AFG primitives unchanged (single 10s rolling window of signed aggressor flow; reduce-only always submits; trade-tick subscription; look-ahead-free prune by ts_event). Three regimes based on |net_flow| magnitude observed at order.ts_init: (a) NEUTRAL: |net_flow| < weak_threshold (default 2.0) -> submit unconditionally (no signal). (b) WEAK ADVERSE: weak_threshold <= |net_flow| < strong_threshold AND adverse direction -> apply base AFG's one-shot gate semantics: skip + _position_flat=True; next open unconditional, no chaining. (c) STRONG ADVERSE: |net_flow| >= strong_threshold (default 50.0, the empirical p70 of fired magnitudes from EDA on 20260308 and 20260316) AND adverse direction -> apply r2-style directional chain with same hard cap (max_consecutive_skips=3, matching r2 for strict comparability): skip + record(consecutive_skips, last_skipped_side). On subsequent same-direction open orders during an active chain (consecutive_skips>=1): direction-change always force-submits and resets; hard-cap reached force-submits and resets; otherwise re-evaluate using the SAME STRONG threshold (>=50): if still strong-adverse, skip and increment; if has decayed below strong_threshold (regime weakened), force-submit and reset (do NOT fall back to weak gate during chain re-eval -- the chain only persists while the magnitude justifies it).

**Inefficiency exploited**: EDA on 20260308 (calm) and 20260316 (heavy-loss) reveals that base AFG's gate fires on ~96% of 1s samples (|net_flow|>=2) -- the 2.0 threshold is essentially "any non-trivial flow", not a selectivity filter. Among fired moments, the magnitude distribution is heavy-tailed: median ~26 contracts, p70 ~50, p90 ~110-140. r2's success ($1093 vs simple $156, but ~$162 BELOW base AFG $1255) suggests chaining helps on the heavy tail (high-magnitude bursts genuinely persist) but slightly hurts on the bulk (medium-magnitude bursts are noisy and the chain extension on those is over-suppression). MCCG v2 chains ONLY on the top ~30% of magnitudes (>=50), preserving base AFG's exact one-shot behavior on the bulk middle (where AFG already extracts the dominant edge: $1255 vs $156 = +704%) while adding r2-style chain on the extreme right tail (where chaining is precision-positive).

**Why it survives costs**: Zero-cost simulator (verified: mean_slippage=0.0, total_commissions=0.0). Edge is realized_pnl. Bar to beat: base AFG $1255.5. Strictly NEVER skips less than base AFG (every base AFG skip happens here; chain only adds same-direction extensions on strong-tier originals). Falsifiable predictions: (i) PRIMARY: realized_pnl on the 12-day train window exceeds base AFG's $1255.5 by at least 5% (>= $1318). (ii) DIAGNOSTIC: skip rate is between base AFG's 21.6% and r2's 32.7% (because chain only engages on strong tier ~30% of AFG's skips, so additional skips beyond base AFG are bounded above by ~30% x 21.6% x avg_chain_length ~= 4-7pp on top of 21.6% -> total ~26-29%). If skip rate matches r2's 32.7% exactly, the strong-threshold is too low (chain fires too often -- behaving like r2); if skip rate is ~21.6% (= base AFG), the chain never fires (strong-threshold too high or no qualifying signals on this dataset). The 21-30% band is the meaningful-signal zone.

**Builds on**: aggressor-flow-gate (base) and afg-pc-r2 (persistent-flow chain). Empirically informed by EDA on training dates 20260308 and 20260316. Pins strong_threshold at the empirical p70 of fired |net_flow| values from those two dates (50 contracts), giving the chain ~30% engagement rate (vs r2's 100%). Pins max_consecutive_skips=3 for strict comparability with r2, isolating magnitude-conditioning as the only changed variable.

**Alternatives considered**: (1) strong_threshold lower (e.g. 5 contracts): rejected based on EDA -- ~92% of fired moments exceed 5, so chain-on-strong becomes chain-on-everything (~equivalent to r2). (2) strong_threshold even higher (e.g. p90 ~120): defensible but would suppress chain to ~10% engagement -- algo would approach base AFG too closely to show a clean differentiation. p70 is the cleanest empirical inflection from the heavy-tailed distribution. (3) Use p70 estimated daily on rolling basis (adaptive): rejected -- introduces a second time-varying parameter, more variance, less interpretable. The two EDA dates show p70 ~49 and ~52 -- highly stable -- so a constant 50 is justified. (4) Chain re-eval falls back to weak threshold: rejected -- would extend chain on decayed signals, defeating the magnitude-condition's purpose. (5) Different cap for strong vs weak tier: rejected -- weak tier doesn't chain at all, so no cap interaction. (6) Sub-window confirmation overlay: deferred -- orthogonal and could compose later.

**Debate summary**: 2 round(s), outcome=CONVERGED. Key objections resolved: strong_threshold pinned at EDA-derived p70=50 contracts (round 1 MAJOR empirical-grounding objection); chain hard cap adopts r2's empirically-validated value of 3 for strict comparability (round 1 MAJOR unjustified-cap objection); tier-ordering during chain re-evaluation made explicit (chain re-eval uses STRONG threshold; decay below strong = force-submit-and-reset).

---

## Implementation Decisions

- **Tier dispatch at decision time**: For each open order, compute net_flow with base AFG's prune logic. If |net_flow| < weak_threshold or direction not adverse: submit. Else if |net_flow| < strong_threshold: behave like base AFG one-shot (skip, set _position_flat=True). Else (|net_flow| >= strong_threshold and adverse): chain logic.
- **Chain state**: `_consecutive_skips: int = 0`, `_last_skipped_side: OrderSide | None = None`. Reset on (a) any non-chain submit, (b) direction change during chain, (c) hard cap reached, (d) on_reset (per-session via Nautilus subprocess isolation).
- **First-signal handling**: Preserves base AFG's "first open after a flat state is unconditional" via `_position_flat=True` initial value. Chain only engages once at least one signal has been processed.
- **Reduce-only**: Always submit, never modify any state (matches base AFG and r2).
- **Subscription**: subscribe_trade_ticks on first order observed (identical pattern to base AFG and r2). Also subscribe_quote_ticks to keep quote cache warm (matches base AFG / r2 hygiene).
- **Quantity invariant**: never modify order.quantity. Only submit or skip.
- **strong_threshold default = 50.0**: empirical p70 of fired |net_flow| values from EDA on 20260308 (49.0) and 20260316 (52.0). The two EDA dates were chosen to bracket the volume regime (calm and heavy-loss). p70 stability across the two dates supports a constant value.
- **max_consecutive_skips default = 3**: identical to r2 for strict comparability. Any pnl delta vs r2 is attributable to magnitude-conditioning rather than cap-length tuning.
- **Logging**: emit INFO log on every skip with net_flow magnitude and tier so post-hoc per-tier skip analysis is possible from per-date order CSVs.
- **No look-ahead**: deque pruned by ts_event <= order.ts_init; chain state is purely backward-looking.

**Concerns**:
- EDA on 2 of 12 dates. p70 values are very stable (49, 52) but a third spot-check would harden the choice. Defer to post-hoc analysis if the backtest result is ambiguous.
- Given 1Hz oracle cadence + 10s rolling window, a strong-adverse signal at T very likely remains strong-adverse at T+1 (window shifts only 10%). Expected chain behavior: most engagements hit hard cap=3, behaving like a "skip next 3 same-direction signals after a strong adverse reading" cooldown. Mean chain length is a useful diagnostic.
- Central premise ("chaining hurts on weak, helps on strong") is qualitatively supported by r2's per-day breakdown (heavy-loss days drive r2's edge; those days have more strong-tier signals) but not directly proven without per-tier instrumentation in r2.

---

## Backtest Observations

<filled after backtest>
