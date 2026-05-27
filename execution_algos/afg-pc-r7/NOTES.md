# Algorithm Notes: afg-pc-r7

## Hypothesis

**Mechanism**: Magnitude-Conditional Chain Extension AFG (v2, short-window anchored). Preserve r6 verbatim. Modify ONLY hard-cap behavior at chain position 3: use SHORT-WINDOW magnitude only as the intensification metric. At chain start (position 1), record first_short_mag = |short_net at first skip| computed over r6's 2s short_window. When consecutive_skips == 3 and gate would re-fire same-direction, compute current_short_mag = |short_net at would-be 4th skip|. EXTEND to position 4 (absolute cap = 4) iff (current_short_mag >= 1.5 * first_short_mag) AND (current_short_mag >= burst_threshold = 5.0). Second condition anchors intensification to an absolute acute-burst floor. Direction-change still force-submits and resets. All other r6 semantics preserved verbatim. Single new parameter (intensification_ratio = 1.5); two new state variables (first_short_mag, an extra computation at gate evaluation).

**Inefficiency exploited**: r6's Path B is the empirically validated acute-burst signal. Conditioning chain extension on short-window intensification (not long-window growth) leverages the same signal-quality logic r6 validated. Conjunction with burst_threshold floor ensures extension fires only when both signal trajectory (intensification) AND absolute level (acute burst still present) confirm an ongoing acute regime. r4's failure mode was unconditional extension; this is doubly-conditional extension, with both conditions empirically anchored to r6's validated Path B mechanism.

**Why it survives costs**: Zero simulator costs. Opportunity cost bounded by single extra deferred entry per chain; absolute cap=4 prevents r4-style runaway. Conjunction with burst_threshold floor makes extension condition STRICTLY narrower than round 2, so worst-case it fires less often than round 2 -- never more. Bounded above by r6's behavior: the extension only ADDS skips r6 would not make (it never removes r6 skips).

**Builds on**: afg-pc-r6 (empirical winner). r4 is the negative evidence; round-2 design refined per Criticizer's asymmetry objection.

**Alternatives considered**: 1) Cap=4 unconditional (criticizer round-2 alt) -- same character as r4 cap=5 just smaller; r2->r4 surface (cap=3 +600% -> cap=5 -43%) is monotonically degrading, so cap=4 likely underperforms r6. Conditional extension is structurally different, not softer r4. 2) Cool-down rule -- orthogonal but unmotivated by direct empirical evidence in prior runs. 3) Round-2 max(long,short) metric -- abandoned per asymmetry.

**Debate summary**: 3 round(s), outcome=CONVERGED. Key objections resolved: round-1's near-duplicate threshold-sweep was abandoned in favor of structural chain-extension mechanism; round-2's asymmetric magnitude metric was replaced with short-window-only intensification anchored by burst_threshold floor.

---

## Implementation Decisions

- **Subclassing approach**: Implement as a fresh ExecAlgorithm subclass (AFGPCR7Algorithm) that copies r6's structure rather than inheriting from AFGPCR6Algorithm. This avoids fragile coupling to r6's private internals.
- **Recording first_short_mag**: At the moment a chain starts (`_record_skip` is called with `_consecutive_skips` transitioning 0 -> 1), compute and store the magnitude of the short_net at that order's decision time. This requires `_gate_fires` to expose short_net to the caller; implementation stores short_net on the instance after each gate evaluation so it can be read in `on_order`.
- **`_short_net_last`**: instance state updated inside `_gate_fires` to record the short_net used at the most recent gate evaluation. When a chain starts, `first_short_mag = abs(self._short_net_last)`.
- **Extension condition computed inside gate evaluation**: When `_consecutive_skips == 3` and the chain side matches, the cap branch now consults the intensification condition rather than immediately force-submitting. Evaluate `_gate_fires` first (must re-fire to be considered), then compare magnitudes.
- **Absolute cap stays at 4**: After position-4 skip is taken, the next same-direction follow-up unconditionally falls through to force-submit (consecutive_skips >= 4 triggers force-submit branch).
- **intensification_ratio = 1.5**: Chosen as a conservative single value. Higher would essentially never fire on a 12-day train; lower would weaken the "intensification" claim.

**Concerns**: 
- No look-ahead: `_short_net_last` only ever holds the short_net computed at the most recent order's `ts_init`, which uses only deque entries with `ts_event <= ts_init`.
- The extra rule fires only on chain position 3 with re-fire intent; expected fire count on 12-day train may be modest.
- Quantity invariant preserved: every code path either calls `submit_order` or skips; no path modifies quantity.

---

## Backtest Observations

Results (12-day train window):
- afg-pc-r7: realized_pnl=$1320.50, trade_count=89744, sharpe=6.38, mdd=-2.77%, win=35.35%
- base AFG:  realized_pnl=$1255.50, trade_count=107198, sharpe=5.59, mdd=-3.32%, win=35.49%
- afg-pc-r6: realized_pnl=$1383.25, trade_count=90287, sharpe=6.68, mdd=-2.71%, win=35.42%
- vs base AFG: pnl +5.18%, sharpe +0.79, mdd improved 16.6%, win essentially flat
- vs r6:       pnl -4.5%,  sharpe -0.30, mdd slightly worse, trade_count 543 fewer
- Slippage 0 in all (zero-cost simulator)

**What drove improvement**: vs base AFG, r7 inherits r6's Two-Path Additive gate + r2 chain machine, which together account for the +5.18% improvement over base AFG. The magnitude-conditional extension to position-4 fires very selectively (one extra skip per chain only when short-window magnitude has intensified 1.5x AND remains above burst_threshold).

**What underperformed**: vs r6, r7 is slightly worse on pnl (-4.5%) and sharpe (-0.30). The trade count is 543 lower than r6 (89744 vs 90287), confirming the extension rule does fire on some chains; but the net pnl effect of those extra deferred entries is mildly negative on this train window. Interpretation: among the chains that reach position 3 with re-fire intent and intensifying short magnitude, the marginal 4th deferral on average misses a price that mean-reverts before the 5th signal -- the regime is intensifying but the oracle's 30s horizon outlives the burst. The extension trades a small amount of net pnl for a modest mdd improvement (-2.77% vs r6's -2.71%, slight noise) -- so the rule is doing what it was designed to do (suppress entries during intensifying acute regimes) but those entries were on average better taken than skipped on this window.

**Hypothesis verdict**: PARTIALLY CONFIRMED but not strictly improving on r6. The mechanism is structurally sound (no look-ahead, bounded extension, strictly narrower than r6 by construction), and r7 STILL beats base AFG by +5.18% (just clearing the +5% pass gate). However, the conditional extension rule did not extract additional edge beyond r6 on this train window; it produced a mild regression. This is consistent with the broader pattern across the pc experiment: r6's "Two-Path Additive + cap=3" configuration appears to sit at a local optimum, and further chain modifications (r4 cap=5, r7 magnitude-conditional cap=4) trade off net pnl.

**Suggested next attempt**: Three options in order of expected leverage:
1. **Lower intensification_ratio to 1.3** (more lenient) AND/OR drop the burst_threshold floor condition -- test whether the extension is too narrow to capture genuine cases. The current rule appears too strict, firing too few extensions and selecting ones that don't add edge.
2. **Reverse direction**: keep r6 verbatim but ADD a magnitude-conditional EARLY-FORCE-SUBMIT at chain position 2 -- if the chain at position 2 has NOT intensified (current_short_mag < first_short_mag), force-submit immediately rather than waiting for position-3 force-submit. Targets the dual hypothesis: the chain mechanism is most useful only on intensifying regimes; non-intensifying chains should be aborted early.
3. **Move orthogonal**: combine r6 with spread-conditional submission (don't gate on flow when spread is wide; the wide-spread regime has different microstructure). r1-r6 have exhausted gate-and-chain modifications; an orthogonal feature axis may yield more.
