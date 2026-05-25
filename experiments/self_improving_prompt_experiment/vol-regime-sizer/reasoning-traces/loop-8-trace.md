# Loop 8 Reasoning Trace

**Note on provenance**: the original research-phase agent ran the method
end-to-end (Steps 1-7 in NOTES.md), implemented the algorithm, and
backtested 8 of 11 train dates (20260308-20260316) before exiting. A
subsequent invocation ran the remaining 3 dates (20260317, 20260318,
20260320; 20260319 skipped per the L5/L6/L7 OOM precedent),
re-aggregated, and wrote this trace. The hypothesis, audit, and
verdict content in NOTES.md was produced by the original researcher;
the backtest analysis below combines per-date metrics from both runs.

## Hypothesis generation method used
Propose-Audit-Falsify-Commit (`prompts/prompt-l5.md`). Seven steps as
in loops 6-7: name the parent's mechanism and operative horizon →
enumerate three Tier-A candidates from parent CSVs → per-train-date
heterogeneity audit → pre-commit falsification decision rules with
HOMOGENEOUS / HETEROGENEOUS branches → commit (or weakest-violation
if all FALSIFIED) → regime-coverage prediction → parameter
justifications.

## How the hypothesis emerged from the method
Step 1 named `vol-regime-sizer` as the (method-prescribed) parent and
its operative horizon as the 30s oracle window. The method requires
this even though the running best is L5; the trace below repeatedly
returns to that distinction.

Step 2 enumerated three substantively new axes — none of which
duplicate L1-L7's exhausted axes (signed-direction, time-of-day,
persistence, trendiness, wide-spread, round-number, negative-streak):
- **C1 — signed local drift (into-the-move blindness)**:
  `signed_drift_30s = side_sign × (arrival_mid − mid_30s_ago)`.
  Failure horizon: 30s pre-arrival drift.
- **C2 — price-level drift from session-open anchor**:
  `abs_drift_from_open = |arrival_mid − first_open_mid_of_session|`.
  Failure horizon: full session.
- **C3 — recent fill velocity (signal-burst regime)**:
  `recent_velocity_10s = count of own opens in [t-10s, t)`.
  Failure horizon: 10s.

Step 3 ran the per-train-date audit over 11 dates × 3 candidates.
All three came back **HETEROGENEOUS** (C1 p90 varies 2.7×; C2 median
varies 3.9×; C3 frac≥5 varies > 100× across thin vs dense dates).

Step 4 ran the pre-committed falsification under the HETEROGENEOUS
branch (need ≥ 8/11 negative-delta dates AND no positive delta beyond
2×median|delta|):
- **C1 FALSIFIED outright**: 2/11 negative, max positive delta +$0.613
  vs allowance $0.067 — **direction reversed**. Into-the-move opens are
  *more* profitable than away-from-the-move opens, opposite the
  hypothesized mechanism.
- **C2 FALSIFIED**: 5/11 negative, max positive delta +$0.082 vs
  allowance $0.054. **Smallest violation margin** of the three (3
  dates short on the count axis; 1.5× over the max-positive allowance).
- **C3 FALSIFIED outright**: 1/11 negative, max positive delta +$0.695
  vs allowance $0.070 — **direction reversed**. High-velocity bursts
  are profit-bursts, not adverse-selection bursts.

Step 5 entered the weakest-violation branch (the third consecutive
loop to do so, after L6 round-number and L7 streak). C2 won on the
"bounded violation" criterion: 1.5× over allowance vs C1/C3's ~10×.

Step 6 (regime-coverage prediction): the regime-relative gate
(`current_drift > 1.5 × running-mean drift`) is expected to fire on
≥ 5% of arrivals on 8-10 of 11 dates — neither warning band triggers.

Step 7 (parameters):
- `anchor_drift_k = 1.5` derived from the falsification's p75 bucket
  size (1.5 × running-mean ≈ 25% gating rate, matching the p75
  bucket used in step 4).
- `anchor_drift_suppress = 0.0` (hard skip) — same principled rule as
  L5/L7: zero rational participation when expected pnl in regime is
  negative.
- `session_anchor_mid = first observed mid` — natural anchor.
- `running_mean_window = session-cumulative` — matches the
  falsification statistic exactly.

## Where the method helped
- **The HETEROGENEOUS audit caught C1 and C3 before falsification
  consumed effort on them.** Both had reversed-direction violations of
  enormous magnitude (+$0.61, +$0.69 vs ~$0.07 allowances). The audit
  surfaced the heterogeneity that produced the reversal.
- **The pre-committed `max_positive_delta` rule (2×median|delta|) was
  what failed C1 and C3 outright** — without that rule a researcher
  could have hand-waved past the reversal as "two outlier dates." The
  rule made it mechanical.
- **The smallest-violation tie-breaker (Step 5 #3) is at least
  partially principled**: C2's 1.5× violation is qualitatively
  different from C1/C3's 10× violations. The trace's "honesty flag"
  in NOTES.md explicitly recorded the expectation of a revert,
  preventing post-hoc narrative inflation if the backtest disappoints.

## Where the method felt limiting or unnecessary
- **The method has now sent three consecutive loops down the
  weakest-violation path** (L6 round-number, L7 streak, L8 anchor-drift).
  Each time, the chosen candidate failed its own pre-committed
  thresholds and the resulting algorithm lost the gate. The method has
  no escape valve: no raw-DBN escalation (the L6 reverted proposal),
  no champion-anchored selection (the L3 reverted proposal), no
  refuse-to-commit branch. The researcher is forced to ship a
  hypothesis they themselves flag as a likely revert.
- **Parent-anchored, not champion-anchored.** The method's Step 1
  requires reading `<base_algo>` (`vol-regime-sizer`) artifacts and
  targeting *its* mechanism. The L5 wide-spread skip is not in the
  L8 algorithm because L5 is the champion, not the parent. The
  consequence: even if C2's regime-relative gate captures some real
  signal vs parent, it is testing the wrong reference. As NOTES.md
  flags: "even if the C2 anchor-drift gate has real signal vs the
  parent, it may overlap heavily with the L5 wide-spread gate."
  This is the loop-7 critic's targeted failure mode, re-manifesting.
- **The "honesty flag" output is structurally inert.** NOTES.md
  reports "I do not expect this candidate to beat L5 ... I am
  implementing C2 as the method's honest output, knowing the loop
  will likely revert." A method that pre-acknowledges a likely revert
  but still ships should probably have a refuse-to-commit branch
  that triggers a different selection process instead.

## What a different method might have produced
A **refuse-to-commit branch** that triggers when no Tier-A candidate
passes thresholds *and* the smallest-violation margin exceeds some
bar (say, > 1.0× the allowance) would produce one of three outputs
instead of the current "ship-the-weakest":
1. Re-enumerate three candidates with new axes — pay the audit cost
   again, accept the loop overhead.
2. Escalate to richer evidence (raw DBN, multi-day stratified
   sampling, parent + champion overlap analysis).
3. Explicitly accept "no improvement available under current
   evidence base; revert to champion" — write the trace, exit the
   loop without an algorithm change.

Loop 7 already produced (3) in spirit (zero-effect gate, identical
to champion). Loop 8 might have produced (3) honestly instead of
implementing C2.

## What the backtest showed
Train-window aggregate, **11/12 dates** (20260319 OOM precedent),
sip-vrs-l8 vs parent `vol-regime-sizer` and vs champion `sip-vrs-l5`:

| Metric | sip-vrs-l8 | parent vrs (12d official) | Δ vs base | sip-vrs-l5 (champ, 11d) | Δ vs champion |
|---|---|---|---|---|---|
| realized_pnl | 377.25 | 753.75 | **−49.95%** | 1471.75 | **−74.36%** |
| sharpe_ratio (cross-day) | 2.788 | 3.065 | −0.277 | 13.718 | −10.930 |
| max_drawdown_pct | -0.0270 | -0.0460 | +0.0190 (less DD) | -0.0164 | -0.0106 (worse) |
| win_rate | 0.3504 | 0.3529 | -0.0024 | 0.3547 | -0.0042 |
| trade_count | 61,816 | 127,991 | -66,175 | 90,582 | -28,766 |
| mean_slippage | 0.0 | 0.0 | 0 | 0.0 | 0 |

Per-date pnl (l8 vs parent vs champion l5):

| date | parent | l5 (champ) | l8 | l8-l5 | l8-parent |
|---|---|---|---|---|---|
| 20260308 | +108.50 | +41.25 | +106.00 | +64.75 | -2.50 |
| 20260309 | +653.00 | +152.00 | +202.50 | +50.50 | -450.50 |
| 20260310 | +413.25 | +147.00 | +346.25 | +199.25 | -67.00 |
| 20260311 | +217.50 | +180.50 | +247.50 | +67.00 | +30.00 |
| 20260312 | -198.25 | +286.50 | -44.00 | -330.50 | +154.25 |
| 20260313 | -455.00 | +56.25 | -258.50 | -314.75 | +196.50 |
| 20260315 | -34.25 | -8.50 | -20.75 | -12.25 | +13.50 |
| 20260316 | -392.75 | -61.25 | -238.50 | -177.25 | +154.25 |
| 20260317 | -167.25 | -41.50 | -138.25 | -96.75 | +29.00 |
| 20260318 | +196.25 | +296.50 | +100.50 | -196.00 | -95.75 |
| 20260320 | +238.50 | +423.00 | +74.50 | -348.50 | -164.00 |

What surprised me: **L8 actually wins the per-date competition vs
parent on the parent's worst dates** (20260312 +$154, 20260313 +$197,
20260316 +$154, 20260317 +$29). It loses on the parent's best dates
(20260309 -$451, 20260310 -$67, 20260318 -$96, 20260320 -$164). The
anchor-drift gate's effect is **directionally consistent with the
audit**: it removes orders late in dates with large session-drift,
which on parent-loss days happens to skip losers (helping) but on
parent-win days skips winners (hurting). The volume-weighting
(NOTES.md honesty note) materializes exactly as predicted: dense
dates with positive deltas dominate, so net pnl regresses.

What confirmed expectations: trade_count ↓ (-12% vs parent, -32% vs
L5), mean_slippage tied, sign of the effect on positive-delta dense
dates negative. NOTES.md's "honest baseline: pnl roughly equal to or
slightly worse than parent's $753.75 → far below L5's $1471.75"
was too generous — actual is **half** of parent. The C2 gate not
only failed to add edge, it removed parent edge on dense dates that
the falsification's volume weighting did not adequately surface.

**Gate result vs champion L5 (the gate's comparator)**: 0/5 strict
improvements. pnl 377 < 1472, sharpe 2.8 < 13.7, max_dd -0.027 <
-0.016 (worse), win_rate 0.3504 < 0.3547, mean_slippage tied. The
expected revert materialized.

## Where I felt uncertain
- **The weakest-violation pick chain (L6 → L7 → L8) is now three
  losses deep with the same structural cause: the method admits a
  candidate that fails its own thresholds because there is no
  alternative output.** Each loop's NOTES.md flags the issue; each
  loop's critic targets a different surface aspect (raw-DBN tier;
  champion-anchoring; feasibility gate). None of the proposals stuck.
  By loop 8 it is clear the method's main remaining failure mode is
  not in any single step — it is the architectural absence of a
  "refuse-to-commit" output.
- **The anchor-drift gate has documentable signal but is mis-weighted
  across dates.** The dates where it helps (parent-loss dense + thin)
  are the dates with smaller order counts; the dates where it hurts
  (parent-win dense) carry the volume. A volume-aware falsification
  rule (e.g., "weight the per-date deltas by trade count before
  computing direction-consistency") would have surfaced this in
  advance. The current method weighs each date equally.
- **20260319 OOM unchanged.** Same precedent as L5/L6/L7 — aggregate
  is over 11 of 12 dates.
- **Champion-redundancy was again documented up front and again
  realized at backtest.** NOTES.md predicted that even if C2 helps vs
  parent, "it may overlap heavily with the L5 wide-spread gate (both
  fire more on volatile/drifted late-session windows)". The L8
  algorithm does *not* layer the L5 wide-spread skip on top — it
  modifies the parent, which is structurally the wrong reference for
  beating the champion. This is the L7 critic's exact failure mode
  rendered concrete: the method does not anchor candidate selection
  to the current champion.
- **The "honest baseline" prediction in NOTES.md was too generous.**
  It said "roughly equal to or slightly worse than parent's $753.75".
  Actual: $377.25 — *half* of parent. The gate is more destructive
  than the method allowed me to anticipate, because the dense
  positive-delta dates are doing most of the per-order pnl-reducing
  work in the aggregate while only 5 of 11 dates pulled the per-date
  delta below zero.
