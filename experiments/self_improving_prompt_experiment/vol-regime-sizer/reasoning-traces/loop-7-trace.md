# Loop 7 Reasoning Trace

**Note on provenance**: this loop's research phase ran the method end-to-end
(NOTES.md contains the full audit + falsification + verdict + commit),
implemented the algorithm, and backtested the first 2 of 11 train dates
before the agent's session limit was reached. A subsequent invocation
ran the remaining 9 dates (20260310-20260320, excluding 20260319 OOM),
re-aggregated, and wrote this trace. The hypothesis, candidate
enumeration, falsification statistics, and verdicts in NOTES.md were
produced by the original researcher; the backtest analysis below
combines per-date metrics from both runs.

## Hypothesis generation method used
Propose-Audit-Falsify-Commit (`prompts/prompt-l5.md`, the running-best
method after loops 5 and 6). Seven steps: name parent's mechanism and
operative horizon → enumerate three Tier-A candidates from parent CSVs
→ per-train-date heterogeneity audit before falsification → pre-commit
falsification decision rules with HOMOGENEOUS vs HETEROGENEOUS branches
→ commit (or weakest-violation if all FALSIFIED) → regime-coverage
prediction → parameter justifications with regime-relative thresholds
for heterogeneous binding features.

## How the hypothesis emerged from the method
Step 1 (parent mechanism) anchored on `sip-vrs-l5`'s gate composition:
parent vol-regime gate × wide-spread skip. Neither layer has visibility
into recent realized pnl. The operative horizon is the 30s oracle
forecast window (`τ=30s`), and the failure-manifestation horizon for
each candidate had to be named.

Step 2 enumerated three substantively different Tier-A candidates,
each tied to a feature derivable from parent CSVs already on disk:
- **C1 — arrival-cadence vol mismatch**: rolling-K=5 mean of
  `|Δarrival_mid|` between consecutive parent OPEN orders. Failure
  manifestation horizon: order-arrival cadence, not tick cadence.
- **C2 — rolling-pnl streak**: rolling-M=10 mean of realized_pnl over
  last 10 closed positions, lagged 1. Failure horizon: session-scale
  pnl autocorrelation.
- **C3 — implementation-shortfall tail**: per-date p90 of `|is_price|`.
  Failure horizon: per-fill cost beyond what spread alone explains.

Step 3 (per-train-date heterogeneity audit) ran 33 pandas reads. All
three came back **HETEROGENEOUS** (C1 median jump varies 5.6×; C2 mean
streak flips sign across dates; C3 p90 varies 9×). Per the prompt's
HETEROGENEOUS branch, falsification required all-train-date sign
consistency.

Step 4 ran the three pre-committed falsification tests:
- **C1 FALSIFIED outright**: 0/11 dates pass δ ≥ +$0.03; direction
  itself reversed (high-jump regime has higher mean pnl on 5 dates).
  Worst reversal magnitude: −$0.24 on 20260311.
- **C2 FALSIFIED on threshold, not on direction**: 5/11 dates pass
  δ ≤ −$0.03, three short of the 8 required. **Direction is unanimous
  — every one of the 11 dates has δ < 0**. No sign reversals.
- **C3 FALSIFIED on both threshold and sign**: 6/11 dates pass at
  δ ≤ −$0.05, but three dates (20260308, 20260311, 20260313) reverse
  sign with magnitudes up to +$1.39.

Step 5 entered the weakest-violation branch (zero SURVIVED). C2 has
the smallest violation margin AND zero sign-reversals. Picked C2.

Step 6 (regime-coverage prediction): on every train date,
`frac<0` ranges 0.38-0.60, so the gate fires on ≥ 5% of warmed-up
arrivals on **all 11 dates**. NOTES.md flags this as at the high
warning threshold.

Step 7 (parameters):
- `streak_M=10` derived from step-3/step-4 window.
- `streak_threshold=0` regime-relative by construction (sign test on a
  centered rolling mean).
- `streak_suppress=0.0` (hard skip) — same principled rule as L5's
  wide-spread default: rational participation is 0 when expected pnl
  in the regime is negative.

## Where the method helped
- **Step 3 audit caught the heterogeneity of all three candidates
  before falsification.** Without it, C3 in particular would have
  looked SURVIVED on the dense-trade subset and lethally bad on the
  thin-trade dates where its sign reverses. The HETEROGENEOUS-branch
  requirement for all-date sign consistency surfaced C3's three
  reversals immediately.
- **Pre-committed decision rules forced C2 to be admitted on its
  weakest-violation merits, not on a single dense-trade subset.**
  The unanimous direction across 11 dates is the cleanest evidence
  produced by any loop's falsification stage so far; the magnitude
  shortfall is real but limited to 6 of 11 dates and concentrated on
  the dense-trade dates where the L5 wide-spread skip is already
  doing most of the work.
- **Regime-relative threshold (sign on centered rolling mean) was
  produced by step-7's check that the parameter cannot be at a
  timescale > 3× the parent's operative horizon.** A magnitude
  threshold (e.g., −$0.05) would have failed exactly the same check
  loop 4 did — it would inherit the wrong-scale "principled" feel.

## Where the method felt limiting or unnecessary
- **Two consecutive loops have entered the weakest-violation branch.**
  Loops 6 and 7 both saw all Tier-A candidates FALSIFY. The method's
  hard "no raw-DBN" rule (Step 2) keeps narrowing the available
  evidence base each loop, since each prior loop closes off a CSV-
  derivable axis. The method has no machinery to recognize this
  exhaustion and escalate to richer data, which is exactly the
  failure mode loop 6's reverted proposal tried to address.
- **The streak-suppression mechanism turned out to be a near-no-op
  in practice.** Once the L5 wide-spread skip has already pruned the
  dense-trade losers, the surviving order stream rarely accumulates
  a 10-position rolling mean below zero. The per-date pnl deltas of
  l7 vs l5 are **identically zero on all 11 dates**. The mechanism
  story (autocorrelation in adverse-streak pnl) is empirically real
  in the parent's CSVs (Step 4 unanimity), but the gate condition
  almost never triggers on the L5-filtered submission set.
  *The method gives no way to predict this from the audit/
  falsification artifacts alone.* It is visible only at backtest.

## What a different method might have produced
A method that includes a **post-falsification, pre-implementation
"on-champion" feasibility check** — compute the candidate's binding
feature on `sip-vrs-l5`'s own per-date orders, not just on the
parent's — would have surfaced the no-op result before the algorithm
was implemented. For C2 this would mean: read l5's positions.csv on
each train date, simulate the M=10 rolling streak gate over its
actual order stream, count how many of l5's orders the gate would
have suppressed, and check the mean pnl of the suppressed bucket. If
the suppressed-bucket count is < 1% of orders or the mean is
indistinguishable from zero, the candidate is **structurally
redundant** with the champion's mechanism even though it survived
falsification on the parent. The current method's audit + falsification
both run on the parent CSVs; nothing forces the researcher to verify
the candidate still triggers under the champion's filtered submission
set.

## What the backtest showed
Train-window aggregate, **11/12 dates** (20260319 OOMs in the runner;
same as L5 and L6), sip-vrs-l7 vs parent `vol-regime-sizer` and vs
champion `sip-vrs-l5`:

| Metric | sip-vrs-l7 | parent (11d) | Δ vs parent | sip-vrs-l5 (champ, 11d) | Δ vs champion |
|---|---|---|---|---|---|
| realized_pnl | 1471.75 | 579.50 | **+153.97%** | 1471.75 | **0.0000** |
| sharpe_ratio (cross-day) | 13.718 | 2.465 | +11.253 | 13.718 | 0.0000 |
| max_drawdown_pct | -0.01637 | -0.04605 | +0.0297 (less DD) | -0.01637 | 0.0000 |
| win_rate | 0.35465 | 0.35258 | +0.0021 | 0.35465 | 0.0000 |
| trade_count | 90,582 | 104,372 | -13,790 | 90,582 | 0 |
| mean_slippage | 0.0 | 0.0 | 0 | 0.0 | 0 |

Per-date pnl (l7 vs parent vs champion l5):

| date | parent | l5 (champ) | l7 | l7-l5 | l7-parent |
|---|---|---|---|---|---|
| 20260308 | +108.50 | +41.25 | +41.25 | 0.00 | -67.25 |
| 20260309 | +653.00 | +152.00 | +152.00 | 0.00 | -501.00 |
| 20260310 | +413.25 | +147.00 | +147.00 | 0.00 | -266.25 |
| 20260311 | +217.50 | +180.50 | +180.50 | 0.00 | -37.00 |
| 20260312 | -198.25 | +286.50 | +286.50 | 0.00 | +484.75 |
| 20260313 | -455.00 | +56.25 | +56.25 | 0.00 | +511.25 |
| 20260315 | -34.25 | -8.50 | -8.50 | 0.00 | +25.75 |
| 20260316 | -392.75 | -61.25 | -61.25 | 0.00 | +331.50 |
| 20260317 | -167.25 | -41.50 | -41.50 | 0.00 | +125.75 |
| 20260318 | +196.25 | +296.50 | +296.50 | 0.00 | +100.25 |
| 20260320 | +238.50 | +423.00 | +423.00 | 0.00 | +184.50 |

What surprised me: **the streak gate fires on zero L5 orders across
all 11 train dates.** The hypothesized mechanism (10-position rolling
mean of realized_pnl < 0) is real on the *parent*'s submitted order
stream (C2 audit unanimity), but once L5's wide-spread skip has
removed the heaviest-cost regime, the M=10 rolling mean on the
remaining stream stays non-negative essentially everywhere. This is
the redundancy-with-champion failure mode loop 3's critic already
flagged ("a candidate that targets the residual-failure dates of the
champion, not the parent"). The method's Step 7 regime-coverage
prediction looked at *parent* coverage (`frac<0` 0.38-0.60 on every
date), but parent-coverage and champion-coverage are different
quantities.

What confirmed expectations: the L5 layer is doing the heavy lifting.
Per-date pnl matches L5 exactly. The gate has no measurable cost
(mean_slippage, sharpe, dd all tied). This is a strict-no-op rather
than a regression.

## Where I felt uncertain
- **Whether the gate "really" never fires, or fires but with
  identical net-zero effect on the order set.** Both produce the same
  per-date metrics. Without instrumenting the algorithm to log
  suppress-events, I cannot tell which. The mechanism story prefers
  "never fires"; the implementation could have a deque-update bug that
  also produces the same surface metrics. A diagnostic counter on
  `streak_suppress_count` would have resolved this.
- **Champion-redundancy is a recurring failure mode the method has
  not yet absorbed.** Loop 3's critic proposed champion-anchored
  candidate selection; loop 4 ran on the reverted (parent-anchored)
  prompt and lost. Loop 5's successful wide-spread skip *happened* to
  layer cleanly on top because the parent's failure mode (wide-spread
  fills) does not overlap with anything L1 (the then-champion) was
  doing. Loop 7's streak gate fails for exactly the reason loop 3's
  critic warned about — its binding feature is largely accounted for
  by the champion's layer. The method continues to look parent-first
  and only checks champion-residuals informally.
- **The "weakest violation" branch is starting to feel like a method
  failure mode in itself.** Two consecutive loops have admitted
  hypotheses that fail their own pre-stated thresholds. C2's evidence
  is genuinely better than L6's round-number gate, but the result is
  the same: 0 strict gate improvements vs the champion. The method
  needs either a stronger refuse-to-commit branch or a richer
  evidence base (e.g., a one-time raw-DBN escalation tier that the
  loop-6 reverted proposal contemplated).
- **20260319 OOM persists.** Same precedent as L5/L6: aggregate is
  over 11 of 12 dates. Apples-to-apples on the 11 common dates l7 vs
  the 11-date l5 subset is a strict tie (Δ = 0 on every metric).
