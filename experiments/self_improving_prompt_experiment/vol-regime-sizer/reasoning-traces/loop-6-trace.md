# Loop 6 Reasoning Trace

## Hypothesis generation method used
Propose-Audit-Falsify-Commit (`prompt-l5.md`, kept after the loop-5
critique). Steps: read parent + train dates → enumerate three
substantively different candidate weaknesses with explicit binding
features → audit each binding feature's distribution across **every**
train date (HOMOGENEOUS/HETEROGENEOUS verdict before falsification) →
state a falsification decision rule per candidate (rule branches on
heterogeneity verdict) → run falsification → commit (with priority
rules including "weakest violation" when zero candidates survive) →
parameter justifications (regime-relative if heterogeneous).

## How the hypothesis emerged from the method
The method's step 1 ("list every prior loop's modification") prevented
re-treading direction (L1), time-of-day (L2), regime persistence (L3),
trendiness (L4), or spread (L5). I enumerated three new axes whose
binding features are derivable from on-disk parent CSVs: order side
(C1), entry-mid range position (C2), and round-number distance from a
5-point grid (C3).

Step 3's regime audit (the new component over loop 1's method) ran one
pandas aggregation per train date per candidate. For all three
candidates, the binding-feature *distribution* came back HOMOGENEOUS
(side: buy_share ratio 1.01; range-position: frac>0.80 ratio 1.25;
round-distance: frac<1tick ratio 2.13). Per the method, this means
each falsification test uses the **aggregate** (HOMOGENEOUS) rule
across all 11 available train dates (20260319 OOM'd in the parent
re-run, same as loop 5).

Step 4's falsification then asked the actionable question — does the
pnl-by-bucket gap support a gate? — and all three came back
**FALSIFIED**:
- C1: mean pnl_gap_buy_minus_sell = -0.031 USD/position (need ≥ 0.03),
  signed 5+/6- across dates.
- C2: mean(pnl_low - pnl_high) = -0.039 USD/position (need ≥ 0.04),
  signed 5+/6-.
- C3: mean(pnl_far - pnl_near) = +0.013 USD/position (need ≥ 0.04),
  signed 7+/4-.

Per step 5 #3 (zero survived, pick smallest violation), C3 had the
smallest violation margin (mean only 0.027 short of threshold,
n_pos 2 short of the 9/11 requirement) and was selected as the
"weakest-falsification" implementation. Honesty flag in NOTES.md
states this is not a SURVIVED hypothesis.

## Where the method helped
- **The step-3 regime audit caught the right thing for the wrong axes.**
  Loop 5's failure mode (calibration on hand-picked dates) doesn't apply
  here because the audit ran on every available train date. The audit
  *would* have caught a regime artifact if there had been one — for all
  three candidates the binding-feature distribution was stable across
  dates. The method works as intended on that axis.
- **Stating decision rules before running data prevented re-fitting.**
  C3 was directionally positive (+0.013 mean) but well below the 0.04
  threshold. Without the pre-stated rule I'd have been tempted to
  recategorize C3 as SURVIVED with a smaller threshold; the method
  forced an honest FALSIFIED verdict.
- **Listing prior loops' axes forced new candidates.** Loops 1-5 had
  already exercised direction, time-of-day, regime persistence,
  trendiness, and spread. The three new candidates (side asymmetry,
  range-position, round-number) are substantively orthogonal to all
  prior axes. The method's step 1 instruction makes this discipline
  explicit.

## Where the method felt limiting or unnecessary
- **Restriction to on-disk parent CSVs prevented testing the most
  promising raw-microstructure candidates.** The most natural "what
  hasn't the parent seen yet?" candidates after loops 1-5 are
  order-book imbalance (bid_size vs ask_size at top of book) and
  signed aggressor flow on recent trades. Both require raw DBN data;
  the method explicitly forbids that in step 3 ("No raw-DBN here").
  This pushed me toward weaker candidates (range-position from
  arrival_mid; round-number from arrival_mid) that the parent CSVs
  *can* expose but which carry less signal. If raw DBN had been
  permitted at step 4 for the SURVIVED candidate only (not the audit),
  the candidate set would have been richer.
- **The HOMOGENEOUS aggregate rule is appropriate for distribution
  stability but doesn't distinguish "stable but noisy" from "stable
  with real signal."** C3's per-date gap is dominated by 5 dates with
  n_near < 200 (where sample noise drives the magnitude) and 6 dates
  with n_near > 700 where the gap is essentially zero. The method's
  aggregate mean is a sample-size-weighted statistic in spirit but
  unweighted in practice; that hid the fact that the "effect" lives
  entirely in low-sample dates.
- **The step-5 "weakest falsification" branch is undertested.** This is
  the first loop in this arm to hit "zero survived." The branch's rule
  ("smallest violation margin") gave a defensible choice (C3) but the
  expected lift is honestly near-zero. The branch arguably should say
  "if every candidate's mean is < threshold/2, write a method-failure
  paragraph and pick by prior reasoning instead." That would have been
  fairer here.

## What a different method might have produced
A two-tier candidate-generation method:
- **Tier-A (cheap-data)**: any feature derivable from parent CSVs.
  Run audit + falsification as in prompt-l5.
- **Tier-B (raw-data only when Tier-A all-falsified)**: if zero
  Tier-A candidates SURVIVE, the method authorises a single one-pandas
  read from one cached DBN partition for one feature, then re-runs
  falsification on the new feature across all dates. Total raw-DBN
  cost is bounded (one feature, all dates, computed once).

With Tier-B I would likely have picked top-of-book size imbalance
(bid_size − ask_size signed by order side). Prior literature on equity
microstructure (Cont 2014, Hasbrouck 2007) places size imbalance as
the dominant single-feature predictor of next-tick price change at
the millisecond scale. The oracle's noisy signal would be expected to
correlate with size imbalance in the same way wide spreads correlated
in loop 5 — and the falsification would have a real chance of
SURVIVING.

## What the backtest showed

**Aggregate (sip-vrs-l6, 11 train dates — 20260319 OOM'd in the
runner, same as loop 5)**:

| Metric | sip-vrs-l6 | parent vol-regime-sizer (12d official) | running-best sip-vrs-l5 (11d) |
|---|---:|---:|---:|
| realized_pnl | **$780.50** | $753.75 | $1,471.75 |
| sharpe_ratio | 3.39 (11d) | 3.06 (12d) | 13.72 (11d) |
| max_drawdown_pct | -0.0386 | -0.0460 | -0.0164 |
| win_rate | 0.3543 | 0.3529 | 0.3547 |
| trade_count | 97,186 | 127,991 | 90,582 |
| mean_slippage | 0.0 | 0.0 | 0.0 |
| `vs_base_pnl_pct` (official) | +3.55% | — | +95.26% |
| `vs_base_slippage_pct` | 0 | — | 0 |

**Apples-to-apples (same 11 dates as l6, recomputed parent on common
dates)**:
- sip-vrs-l6 = $780.50
- parent (11d common) = $579.50
- delta_pnl_pct = +34.69%

**Per-date breakdown (l6 vs parent, realized_pnl)**:

| date | l6 | parent | delta | l6_trades | parent_trades | round-gate trades skipped (approx) |
|---|---:|---:|---:|---:|---:|---:|
| 20260308 | +118.75 | +108.50 | +10.25 | 350 | 367 | ~17 (~5%) |
| 20260309 | +709.25 | +653.00 | +56.25 | 2,750 | 2,878 | ~128 (~4%) |
| 20260310 | +437.25 | +413.25 | +24.00 | 2,190 | 2,290 | ~100 (~4%) |
| 20260311 | +197.25 | +217.50 | -20.25 | 2,342 | 2,416 | ~74 (~3%) |
| 20260312 | -145.50 | -198.25 | +52.75 | 5,156 | 5,447 | ~291 (~5%) |
| 20260313 | -380.50 | -455.00 | +74.50 | 7,580 | 8,026 | ~446 (~6%) |
| 20260315 | -31.50 | -34.25 | +2.75 | 1,687 | 1,832 | ~145 (~8%) |
| 20260316 | -378.25 | -392.75 | +14.50 | 17,772 | 19,209 | ~1,437 (~7%) |
| 20260317 | -149.00 | -167.25 | +18.25 | 18,336 | 19,962 | ~1,626 (~8%) |
| 20260318 | +172.00 | +196.25 | -24.25 | 19,369 | 20,913 | ~1,544 (~7%) |
| 20260320 | +230.75 | +238.50 | -7.75 | 19,654 | 21,032 | ~1,378 (~7%) |

**l6 vs running-best l5 (same 11 dates)**:
- l5 = $1,471.75; l6 = $780.50; delta = -$691.25.

L5 beats L6 by a wide margin. On every single date except 20260308 and
20260309 (where l6 narrowly wins on raw pnl by skipping the wide-spread
regime less aggressively), l5 either wins outright or ties. On the 4
dense-trade dates (20260316, 20260317, 20260318, 20260320) l5 cut the
parent's tail much more than l6 because the wide-spread skip captured
the real adverse-selection cluster; the round-number skip removes 7-8%
of orders without a coherent pnl signal.

What surprised me:
- **L6 actually beats the parent by +34.7% apples-to-apples** —
  unexpected given the FALSIFIED verdict. The round-number gate's
  ~7% skip rate happens to remove a near-zero-mean-pnl bucket on
  every date (rather than a sharply negative one), so by Jensen-like
  arithmetic the net effect is a small positive on the dense-trade
  days where the skipped fills had slightly-negative mean pnl. This
  is a "lottery-ticket" kind of win, not a mechanism: the gate
  doesn't know *why* it's skipping, and on a different OOS window
  it could easily flip negative.
- **L6 sharpe_ratio (3.39) beat the parent (3.06)** but lost badly
  to L5 (13.72) — the per-date pnl variance is barely tighter than
  the parent and nothing like L5's tight distribution.

What confirmed expectations:
- realized_pnl: small positive vs parent (predicted "small to
  ~neutral"; observed +$27 vs official 12d parent, +$201 apples-to-
  apples).
- mean_slippage: 0 (zero-slippage fill model).
- trade_count: down ~7% vs parent (predicted ~7-10%).
- win_rate: essentially identical to parent (+0.14pp).
- sharpe_ratio: small positive vs parent.

## Where I felt uncertain
- **Choosing C3 as "weakest violation" was defensible but the result
  is largely noise.** The +34.7% apples-to-apples vs parent does not
  reflect a discovered mechanism — it reflects that ~7% of orders
  happen to have slightly-negative mean pnl on average, and skipping
  them avoids that drag. A small different parameter (`round_threshold
  = 0.5 tick` or `1.5 ticks`) would likely give different (potentially
  worse) results, and I have no way to validate this from the existing
  step-4 falsification. The win is real on the train window but the
  *mechanism* is not.
- **The 20260319 OOM persists.** Both the original parent and the new
  parent re-run failed on 20260319 with the same Rust allocator 4 GiB
  cap. L6 also OOM'd on 20260319. This is the same runner-level issue
  documented in loop 5 and unchanged by anything in this loop. The
  aggregate is over 11/12 train dates; the cross-date Sharpe is
  computed on 11 days.
- **Apples-to-apples vs parent (12d official aggregate) is muddled by
  the missing 20260319.** Parent's 20260319 was +$174.25; if l6 had
  reached 20260319 and tracked parent at ~95% (the typical trade-count
  ratio implies a ~95% pnl retention), l6's 12-day total would be
  ~$780 + (174.25 × 0.93) ≈ $942 vs parent $753.75 — still positive
  but the official `vs_base_pnl_pct = +3.55%` understates the
  apples-to-apples lift.
- **The keep/discard gate verdict is unambiguous.** Comparing l6 to
  running-best l5:
    realized_pnl 780.50 vs 1471.75 → l6 WORSE
    mean_slippage 0 vs 0 → tied (no improvement)
    sharpe_ratio 3.39 vs 13.72 → l6 WORSE
    max_drawdown_pct -0.0386 vs -0.0164 → l6 WORSE
    win_rate 0.3543 vs 0.3547 → l6 WORSE (essentially tied)
  Zero of five metrics improved; the next critique will revert.
- **The method generated a defensibly-honest hypothesis from
  disappointing data.** The hypothesis is small, has known weaknesses,
  comes with a regime-coverage prediction (9-10 of 12 dates fire on
  ≥ 5% — matches actual ~7% across observed dates), and is documented
  as a "weakest violation" pick rather than a SURVIVED candidate. The
  method's failure mode here isn't process — it's the on-disk-CSV
  restriction limiting candidate quality when all easy CSV-derivable
  axes have been exhausted across prior loops.
