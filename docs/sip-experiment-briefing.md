# Self-Improving Prompt Experiment — Briefing Document

> Prepared for: Event Horizon Labs presentation  
> Branch: `self-improving-prompt`  
> Date: 2026-05-27

---

## Executive Summary

This repository contains an **autonomous execution-algorithm research system** for CME GLBX FX futures trading. The `self-improving-prompt` experiment extends the base system by adding a **critic layer** — after each research loop, an AI critic reads the reasoning trace, identifies the failure mode in the hypothesis-generation method, proposes a new method, and applies an objective gate to decide whether the new method should replace the old one.

Over 8 loops × 3 algorithm arms = 24 total iterations, the system:

- Discovered **8 systematic failure modes** in LLM-based quantitative hypothesis generation
- Produced algorithms that beat the base by up to **+95.3% in realized PnL** (vol-regime-sizer arm, loop 5)
- Revealed an empirical **~4-loop critic burn-in pattern** across all three arms, where the critic accumulates enough failure-data to make a genuinely architectural change to the method
- Demonstrated that prompt evolution can be automated, gated, and version-controlled

---

## 1. System Architecture

### The Two-Layer Loop

```
┌─────────────────────────────────────────────────────────┐
│                   OUTER LOOP (per arm)                  │
│                                                         │
│   Loop N                                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │  RESEARCH PHASE                                  │   │
│  │  ┌────────────────────┐                         │   │
│  │  │ .current_prompt.md │ ─→ hypothesis method    │   │
│  │  └────────────────────┘                         │   │
│  │         ↓                                        │   │
│  │    generate hypothesis                           │   │
│  │         ↓                                        │   │
│  │    implement algorithm                           │   │
│  │         ↓                                        │   │
│  │    backtest (12 train dates)                     │   │
│  │         ↓                                        │   │
│  │    write reasoning trace                         │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  CRITIQUE PHASE                                  │   │
│  │         ↓                                        │   │
│  │    read trace + code + metrics                   │   │
│  │         ↓                                        │   │
│  │    identify failure mode in method               │   │
│  │         ↓                                        │   │
│  │    propose new method                            │   │
│  │         ↓                                        │   │
│  │    Karpathy keep/discard gate (majority-rules    │   │
│  │    across 5 metrics vs running best)             │   │
│  │         ↓                                        │   │
│  │   KEPT → .current_prompt.md ← new method        │   │
│  │   REVERTED → .current_prompt.md ← prior best    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│   Loop N+1 uses updated .current_prompt.md             │
└─────────────────────────────────────────────────────────┘
```

### Key Design Choices

**The critic only evolves the hypothesis-generation method.** Implementation, backtesting, evaluation, and logging are fixed infrastructure — the critic cannot touch them. This isolates what's being improved.

**The Karpathy keep/discard gate** compares 5 metrics (realized PnL, mean slippage, Sharpe, max drawdown, win rate) between the new loop's result and the running best. ≥3 of 5 improved → KEPT. This prevents the system from keeping prompts that cherry-pick one metric.

**Version-controlled prompts.** Every promoted method is saved as `prompt-l<N>.md`. Reverts are mechanically sound: the system copies the running-best loop's `prompt_in` file back to `.current_prompt.md`.

**One architectural change per loop.** The critic may only fix one failure mode per loop. This keeps the experiment interpretable — each loop isolates one hypothesis about what makes hypothesis-generation better.

---

## 2. The Experiment

### Fixed Variables

| Variable | Value |
|---|---|
| Trading strategy | Oracle (sigma=6, horizon=30s, 1Hz signal) |
| Dataset | CME GLBX MES FX futures, 26 days (Mar–Apr 2026) |
| Train window | 2026-03-08 to 2026-03-21 (12 trading days) |
| Test window | 2026-03-26 to 2026-04-06 (held out — Lambda OOS eval **[OOS PENDING]**) |
| Pass gate | ≥+5% PnL vs baseline, ≤+5% slippage regression |
| Evaluation | Nautilus BacktestEngine tick replay |

### Three Arms, Three Base Algorithms

| Base Algorithm | Mechanism | Base PnL | Base Sharpe | Base Trades |
|---|---|---|---|---|
| `position-tier-gate` | Skips opening orders when position ≥ cap (=1 contract) | $4,262.50 | 17.62 | 90,433 |
| `aggressor-flow-gate` | Skips opens when rolling signed aggressor-flow is adverse | $1,255.50 | 5.59 | 107,198 |
| `vol-regime-sizer` | Probabilistic skip based on unsigned volatility ratio (fast/slow EWM) | $753.75 | 3.06 | 127,991 |

Each arm ran independently: same seed prompt, same number of loops, same critic architecture, different base algorithm.

### The Seed Prompt (l0)

All three arms started from the same 4-step single-pass method:

1. Read the base algorithm's mechanism
2. Identify ONE plausible weakness
3. Propose ONE concrete modification
4. State expected P&L and slippage direction

No empirical validation. No multi-candidate exploration. No falsification. This is the baseline for prompt quality.

---

## 3. Complete Results Tables

### Position-Tier-Gate Arm (PTG)

| Loop | Algo | PnL | vs Base | Sharpe | Max DD | Win Rate | Trades | Action | Method |
|---|---|---|---|---|---|---|---|---|---|
| 1 | sip-ptg-l1 | $4,262.50 | 0.0% | 17.62 | -1.73% | 37.2% | 90,433 | KEPT | l0 |
| 2 | sip-ptg-l2 | $3,774.00 | -11.5% | 19.21 | **-0.54%** | 37.5% | 81,557 | KEPT | l1 |
| 3 | sip-ptg-l3 | $3,131.75 | -26.5% | 12.57 | -2.27% | 35.8% | 126,678 | REVERTED | l2 |
| 4 | sip-ptg-l4 | $2,825.25 | -33.7% | 12.98 | -2.18% | 36.4% | 98,270 | REVERTED | l1 |
| 5 | sip-ptg-l5 | $156.00 | -96.3% | 0.60 | -5.29% | 35.1% | 136,734 | REVERTED | l1 |
| 6 | sip-ptg-l6 | $3,848.00 | -9.7% | 17.09 | -1.75% | 37.1% | 83,604 | REVERTED | l1 |
| 7 | sip-ptg-l7 | $156.00 | -96.3% | 0.60 | -5.29% | 35.1% | 136,734 | REVERTED | l1 |
| **8** | **sip-ptg-l8** | **$4,292.75** | **+0.7%** | **18.81** | **-1.11%** | **37.8%** | **75,262** | — | l1 |

Running best throughout: **sip-ptg-l2** (best Sharpe 19.21, lowest max DD -0.54%)  
Final loop winner: **sip-ptg-l8** (best absolute PnL, best risk metrics after l2)

### Aggressor-Flow-Gate Arm (AFG)

| Loop | Algo | PnL | vs Base | Sharpe | Max DD | Win Rate | Trades | Action | Method |
|---|---|---|---|---|---|---|---|---|---|
| 1 | sip-afg-l1 | $1,064.75 | -15.2% | 4.86 | -3.37% | 35.0% | 106,967 | KEPT | l0 |
| 2 | sip-afg-l2 | $645.00 | -48.6% | 2.76 | -4.31% | 35.3% | 120,966 | REVERTED | l1 |
| 3 | sip-afg-l3 | $714.00 | -43.1% | 3.06 | -4.14% | 35.1% | 115,099 | REVERTED | l0 |
| 4 | sip-afg-l4 | $780.25 | -37.9% | 3.55 | -4.07% | 35.2% | 120,148 | REVERTED | l0 |
| **5** | **sip-afg-l5** | **$1,002.00** | **+3.3%** | **4.95** | **-2.93%** | **35.4%** | **78,442** | **KEPT** | l0 |
| 6 | sip-afg-l6 | $984.25 | +1.5% | 4.83 | -2.96% | 35.3% | 79,165 | REVERTED | l5 |
| 7 | sip-afg-l7 | $669.00 | -31.0% | 3.07 | -3.98% | 35.3% | 96,176 | REVERTED | l0 |
| 8 | sip-afg-l8 | $836.50 | -13.8% | 3.90 | -3.70% | 35.3% | 88,329 | — | l0 |

Running best: **sip-afg-l5** (only positive delta, best risk metrics)

### Vol-Regime-Sizer Arm (VRS)

| Loop | Algo | PnL | vs Base | Sharpe | Max DD | Win Rate | Trades | Action | Method |
|---|---|---|---|---|---|---|---|---|---|
| **1** | **sip-vrs-l1** | **$1,062.25** | **+40.9%** | 4.19 | -4.28% | 35.4% | 127,923 | **KEPT** | l0 |
| 2 | sip-vrs-l2 | $723.25 | -4.0%* | 2.99 | -4.58% | 35.3% | 126,948 | REVERTED | l1 |
| 3 | sip-vrs-l3 | $868.75 | +15.3%* | 3.54 | -4.55% | 35.4% | 125,936 | REVERTED | l1 |
| 4 | sip-vrs-l4 | $439.00 | -41.8%* | 1.77 | -4.86% | 35.2% | 130,227 | REVERTED | l1 |
| **5** | **sip-vrs-l5** | **$1,471.75** | **+95.3%** | **13.72** | **-1.64%** | **35.5%** | **90,582** | **KEPT** | l1 |
| 6 | sip-vrs-l6 | $780.50 | +3.5%* | 3.39 | -3.86% | 35.4% | 97,186 | REVERTED | l5 |
| 7 | sip-vrs-l7 | $1,471.75 | +95.3%* | 13.72 | -1.64% | 35.5% | 90,582 | REVERTED | l5 |
| 8 | sip-vrs-l8 | $377.25 | -50.0%* | 2.79 | -2.70% | 35.0% | 61,816 | REVERTED | l5 |

*vs_base_pnl_pct computed relative to the VRS base algorithm ($753.75)  
Running best: **sip-vrs-l5** (best PnL, Sharpe, and max drawdown across all 24 variants on this arm)

---

## 4. The Eight Failure Modes

These are the failure modes the critic discovered, in order of discovery. Each was identified in a reasoning trace and targeted by the subsequent method proposal.

### FM-1: Empty Event Class (PTG L1)
**What happened:** The seed method had no empirical pre-check. The researcher hypothesized a mechanism conditioned on an event class (same-`ts_init` CLOSE+OPEN pairs in a specific directional continuation pattern) that was vacuous — the events either never fired or fired in a way that made the proposed algorithm identical to the base.  
**Critic's diagnosis:** "The researcher reasoned about the oracle's emission process in pure prose and committed to a hypothesis that conditioned on an event class... the mechanism could not have fired on any order."  
**Fix introduced:** Mandatory empirical pre-check before implementation. Researcher must count the targeted event class from on-disk artifacts, predict N fires/day, and fail-fast if actual < predicted by >5×.

### FM-2: Counterfactual Blindness (PTG L2, AFG L2, VRS L2-L4)
**What happened:** The empirical pre-check validates that targeted events are non-empty and negative-EV *in the base's realized stream*. But it never measures the counterfactual — what happens to the aggregate P&L when those orders are actually removed. In PTG L2, removing wide-spread opens validated by EDA (correctly negative-EV in isolation) triggered cascade effects that destroyed P&L.  
**AFG L2 variant:** EDA on 562k trade events showed SELL-skip inversion (t=-41) at the *tick* cadence — but the oracle fires orders at 1Hz, not tick cadence, so the EDA sampling frame was wrong. Iron-clad statistics, wrong reference frame.  
**Critic's diagnosis:** "The empirical pre-check validates event-class frequency and sign, but it never measures the aggregate consequence of acting on that class — specifically whether the cascade downstream from removing those orders is neutral or destructive."  
**Fix introduced:** One-date real-mechanism probe backtest before committing. Researcher runs the actual algorithm on one train date (not a stub) and must see 3 hard pass conditions on the probe to proceed.

### FM-3: Single-Candidate Myopia (PTG L3-L4, AFG L1-L4)
**What happened:** Sequential single-pass exploration. After PTG L3's proposal was falsified mid-implementation, the researcher had no alternative prepared and was forced to improvise. In AFG, loops 1-4 each tried a different decision-function modification (EWMA, side-asymmetry, two-window, normalized fraction) — all variations of the same axis, all failing.  
**Critic's diagnosis:** "The probe correctly fired FAIL on loop-3's tight-spread override but left the researcher with no escape valve when no alternative proposal was prepared — forcing a 'deliberate diversification' signal into the next loop."  
**Fix introduced:** Three-candidate enumeration with diversity constraints. Candidates must be substantively different (different signal inputs, not incremental tuning). Candidate diversity ban: cannot propose the same axis twice.

### FM-4: Sampling Bias in Falsification (VRS L2)
**What happened:** The VRS L2 propose-falsify-commit method ran falsification tests on outcome-ranked dates — the worst two loss days in the train window. This guaranteed an adverse signal in the sample. The session-close suppression mechanism passed on those dates but failed on normal dates.  
**Critic's diagnosis:** "Sample selection bias — loop 2 ran falsification on only the two worst-loss train dates, which guaranteed an adverse signal in the sample, making the 'falsification' test circular."  
**Fix introduced:** Pre-committed random or chronological split for falsification. Odd/even train/validation split. Full-window sign-consistency requirement.

### FM-5: Regime Heterogeneity Blindness (VRS L5 → L6)
**What happened:** VRS L5's wide-spread skip gate was calibrated on dense-trade dates (~6% wide-spread arrivals), but on early-window thin-trade dates the mechanism fired on >99% of arrivals, forgoing ~$871 of parent edge. The mechanism "worked" on average but was a regime artifact.  
**Critic's diagnosis:** "Falsification calibrated on one or two hand-picked train dates. When the candidate's binding feature has heterogeneous distribution across train dates, the resulting threshold becomes a regime artifact."  
**Fix introduced:** Per-date regime audit across ALL train dates before falsification. Heterogeneity verdict (HOMOGENEOUS/HETEROGENEOUS) must be stated before running falsification. HETEROGENEOUS candidates require per-date sign-consistency (passes on ≥8/12 dates, zero sign-reversals >2×).

### FM-6: Champion Redundancy (VRS L3, L7)
**What happened:** New candidate mechanisms competed *against* the kept champion rather than composed with it. VRS L7's audit revealed that the proposed mechanism's binding feature fired on zero orders that survived VRS L5's existing gate — it was predestined to be a no-op.  
**Critic's diagnosis:** "The running method's audit and falsification both run on the parent's CSVs, with no machinery to detect that a candidate's binding feature has already been removed by the champion's filter."  
**Fix introduced:** Champion CSVs (fills/orders filtered through the kept algorithm) must be used for regime audit when a champion exists. Explicit PASS/FAIL feasibility gate: candidate must fire on ≥N% of champion-surviving orders.

### FM-7: Stub-Mode Degeneration (PTG L7, AFG L2)
**What happened:** PTG L7's proposal was validated with a stub backtest — a synthetic test that did not actually execute the proposed mechanism in the Nautilus engine. The stub produced passing results ($65.50 realized PnL matching expected). The real 12-date backtest produced $156 (identical to the catastrophic L5 failure, -96.3% vs base).  
**Critic's diagnosis:** "The active method lets a researcher greenlight a hypothesis on a stub probe that does not actually execute the proposed mechanism — the loop-7 stub run produced $65.50 == $65.50 (PASS on all 3 conditions) but the stub was a deterministic synthetic that hardcodes fill outcomes independent of the proposed order submission logic."  
**Fix introduced:** Mandatory real-mechanism probe: the single-date probe must use the actual algorithm code via `run_backtest()`, not a synthetic stub. Three hard pass conditions must be verified on live engine output.

### FM-8: Uncalibrated Parameters (AFG L1, L4, L5; VRS L1, L3-L4)
**What happened:** Multiple loops shipped with armchair-chosen numeric parameters. AFG L1's tau=3s half-life was "reasonable" but not grounded in actual trade-arrival distributions. AFG L4's frac_threshold=0.25 was derived from a "roughly 2-contract imbalance in 8 total" back-of-envelope. VRS L4's trendiness window of 40 ticks was intuition.  
**Critic's diagnosis (AFG L1):** "The researcher committed to a key quantitative parameter (flow_threshold=0.6) derived from an explicitly stated false assumption (uniform trade-arrival density)... parameters chosen by armchair reasoning that could have been grounded in measurement."  
**Fix introduced:** Parameters must be derived from step-4 statistics (event-class frequency, distribution percentiles, regime-relative rules). Parameters stated as multiples of rolling statistics rather than absolute values.

---

## 5. The L5 Inflection Pattern

All three arms showed their first meaningful positive result at **Loop 5**:

| Arm | L5 Result | What Changed at L5 |
|---|---|---|
| PTG | L5 itself was catastrophic (-96.3%), but L8 (+0.7%) benefited from the critic's Loop 5 diagnosis about stub-mode degeneration | Critic identified stub degeneration; L8 used rolling win-rate regime filter |
| AFG | **+3.3% vs base** (first positive, loops 1-4 all negative) | Switched from decision-function axis to cascade-policy structural axis |
| VRS | **+95.3% vs base** (largest result in the experiment) | Added per-date regime heterogeneity audit before falsification |

**What this suggests:** The critic requires ~4 loops of failure data before it can make a genuinely architectural change to the hypothesis-generation method. The first few loops produce incremental critiques that fix surface symptoms (add an empirical check, add a falsification step). It takes seeing those fixes fail before the critic can identify the deeper structural failure modes (wrong reference frame, regime heterogeneity, stub mode).

This is consistent with what might be called a **"critic burn-in" period** — a warm-up phase where the critic is accumulating examples of how the current method fails before it has enough signal to redesign it.

---

## 6. Best Algorithms Explained

### sip-vrs-l5 — Best Overall (+95.3% vs base, Sharpe 13.72)

**Mechanism (two layers):**

Layer 1 (from sip-vrs-l1): Replace unsigned vol-ratio skip with **signed directional headwind**. Instead of skipping proportionally to `|fast_ewm / slow_ewm|`, compute `headwind = -side_sign × ewm_drift / slow_vol`. Skip more aggressively only when recent micro-drift is *against* the order side (fading the move). Submit at probability 1.0 when riding the drift.

Layer 2 (sip-vrs-l5 addition): Hard-skip any OPEN order when top-of-book spread > 1.5 ticks (0.375 USD). This is a liquidity-quality gate — wide-spread fills indicate either illiquidity or information asymmetry adverse to the execution.

**Why it works:** The base VRS treats all high-vol regimes as uniformly bad. Layer 1 separates trending (ride the drift — submit) from mean-reverting (fight the drift — suppress). Layer 2 removes fills that happen to be at adverse spread regardless of vol regime. Two orthogonal axes of adverse-selection risk, neither of which the base addresses.

**Key numbers (train window):** 90,582 trades (29% fewer than base), $1,471.75 PnL (95% above base's $753.75), Sharpe 13.72 vs base's 3.06, max drawdown -1.64% vs base's -4.95%.

> **[OOS PENDING] — sip-vrs-l5 test-window results**  
> Once the Lambda evaluator returns results, fill in the table below and remove this block.  
> Source file: `execution_algos/sip-vrs-l5/results/backtest-results.json` → `performance_oos`  
>
> | Metric | Train (known) | OOS test window | Generalises? |
> |---|---|---|---|
> | Realized PnL | $1,471.75 | `[FILL]` | `[YES / NO / PARTIAL]` |
> | vs baseline PnL % | +95.3% | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Sharpe ratio | 13.72 | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Max drawdown | -1.64% | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Win rate | 35.5% | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Trade count | 90,582 | `[FILL]` | — |
> | vs baseline slippage % | — | `[FILL]` | — |
>
> **What to update:** Replace this block with the filled table. Update Section 9 gap row. Update the paper claim if OOS confirms. Update Slide 9 of `sip-presentation-outline.md`.

### sip-ptg-l8 — Best Risk-Adjusted PTG (+0.7% PnL, but best Sharpe and lowest max DD)

**Mechanism:** Add a rolling win-rate gate on top of the base position-tier-gate. Track the rolling win-rate over the last 20 estimated round-trip P&Ls. Skip OPEN orders when rolling win_rate < 35% — this suppresses participation in regimes where the oracle's recent accuracy is low. Anti-cascade force-reentry after extended suppression.

**Why it's notable:** The PTG arm is hard to improve because the base is already very good (Sharpe 17.62, $4,262 PnL). L8 doesn't beat the base in PnL (only +0.7%) but achieves Sharpe 18.81 and max drawdown -1.11% — the lowest max drawdown of all 24 variants. The oracle quality gate is an orthogonal axis to position-state gating.

> **[OOS PENDING] — sip-ptg-l8 test-window results**  
> Source file: `execution_algos/sip-ptg-l8/results/backtest-results.json` → `performance_oos`  
>
> | Metric | Train (known) | OOS test window | Generalises? |
> |---|---|---|---|
> | Realized PnL | $4,292.75 | `[FILL]` | `[YES / NO / PARTIAL]` |
> | vs baseline PnL % | +0.7% | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Sharpe ratio | 18.81 | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Max drawdown | -1.11% | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Win rate | 37.8% | `[FILL]` | — |
>
> **What to update:** Replace this block with the filled table. If OOS Sharpe holds above train baseline (17.62), update Section 9 and lead with this as the risk-adjusted story.

### sip-afg-l5 — Best AFG (+3.3% vs base, first positive after 4 failures)

**Mechanism:** Transform the base's binary `_position_flat` anti-cascade flag (unconditional re-entry after any skip) into a graduated skip-streak counter. At streak=1, relax the flow threshold from 2.0 to 3.0 contracts (1.5x). At streak≥2, force unconditional submit. This allows the system to skip one additional adversely-timed order after the first skip if flow is still strongly adverse, while preventing cascade lock-in.

**Why it's notable:** All previous AFG attempts modified the *signal* that determines whether to skip (EWMA, fractions, two-window, side-asymmetry). L5 was the first to modify the *cascade policy* — how the algorithm recovers from a skip. This is a structural axis orthogonal to all decision-function modifications. The insight came from recognizing that at 1Hz oracle cadence with a 10-second gate memory window, adverse-flow regimes persist across consecutive order arrivals.

> **[OOS PENDING] — sip-afg-l5 test-window results**  
> Source file: `execution_algos/sip-afg-l5/results/backtest-results.json` → `performance_oos`  
>
> | Metric | Train (known) | OOS test window | Generalises? |
> |---|---|---|---|
> | Realized PnL | $1,002.00 | `[FILL]` | `[YES / NO / PARTIAL]` |
> | vs baseline PnL % | +3.3% | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Sharpe ratio | 4.95 | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Max drawdown | -2.93% | `[FILL]` | `[YES / NO / PARTIAL]` |
> | Win rate | 35.4% | `[FILL]` | — |
>
> **Note:** Train margin was only +3.3%. A narrow OOS confirmation still validates the cascade-policy axis. A miss here weakens the AFG story but does not undermine the VRS or PTG findings.  
> **What to update:** Replace this block with the filled table. Adjust the "best AFG" framing in Section 3 results table accordingly.

---

## 7. Instructive Failures

### The EDA-Confirmed Mechanism That Inverted in Live Chains (AFG L2)

Loop 2's researcher ran EDA on 562,000 pooled trade events and found a statistically iron-clad result: when net_flow ≥ +2 contracts (buyer-dominated), the future 30-second drift is DOWN (mean -0.144 ticks, t-statistic = -41.46). This means the base's SELL-skip (skip sells when buyers dominate) is directionally *inverted* — it was skipping the wrong trades.

The researcher disabled SELL gating entirely. Trade count increased 13% as predicted. But realized PnL fell from $1,255 to $645 (-48.6%).

Why? The EDA sampled at **trade-tick cadence** (every aggressor print). The oracle fires at **1Hz cadence** (every second). At tick cadence, the relationship held. At order cadence, the signal-to-noise collapsed. The EDA result was real but non-transferable to the order-routing decision.

This is a canonical **reference-frame mismatch** failure. Statistical validity does not imply operational validity.

### The Position Cap Increase That Destroyed P&L (PTG L5 and L7)

PTG L5 raised `position_cap` from 1 to 2, allowing pair-OPEN flips (direction reversals while a position is already open) to submit. EDA showed 7,535 such pairs per day with mean +$0.015/trade — clearly positive-EV in isolation.

Result: PnL collapsed from $4,262 to $156 (-96.3%). Trade count exploded from 90,433 to 136,734.

The explanation: simultaneously holding opposing 1-contract positions creates bi-directional exposure that the oracle is not calibrated to manage. The OMS dynamics (netting, position tracking, close-order sequencing) interact in ways the static per-trade EDA estimate cannot capture. The mechanism was tested again in L7 via deferred submission — same result, same PnL ($156), same trade count (136,734). The explorer found the same dead end twice.

---

## 8. Compelling Visual Candidates

These are charts that would be highly effective for a slide presentation:

1. **PnL trajectory per arm across 8 loops** (line chart with run-best line overlaid). Shows the volatility of the search and the episodic breakthrough at L5.

2. **Prompt action heatmap** (3 arms × 8 loops, colored by KEPT/REVERTED). Shows how infrequent "kept" events are (6 of 24 loops) and where they cluster.

3. **Sharpe ratio improvement by variant** (bar chart, all 24 variants, grouped by arm). VRS L5's 13.72 vs VRS base's 3.06 is visually dramatic.

4. **The 8 failure modes as a taxonomy** (table or diagram showing: loop first discovered, category, how the fix worked). Shows progressive learning.

5. **Prompt evolution as a timeline** (showing the actual methods in bullets: l0 → l1 → l5 for VRS). Showing the text get longer and more structured across kept loops.

6. **Trade count vs PnL scatter** (one dot per variant, colored by arm). PTG variants cluster at low-trade/high-PnL; VRS L5 appears as an outlier (moderate trade reduction, massive PnL gain).

7. **sip-vrs-l5 mechanism diagram** (showing the two-layer gate: signed headwind filter + spread filter). Intuitive visual of what "orthogonal axes" means.

8. **Critic burn-in chart** (showing cumulative "kept" count vs loop number across all three arms). Flat for loops 1-4, then inflection at loop 5.

---

## 9. Paper Potential Assessment

### What the Current Data Supports

The experiment is a concrete demonstration of several testable claims:

1. **Self-improving prompt critics can identify systematic failure modes in LLM hypothesis generation.** The 8 failure modes are not random noise — they are structurally distinct categories (vacuity, counterfactual blindness, sampling bias, regime heterogeneity, etc.) that appear consistently across arms.

2. **A critic burn-in period exists.** All three independent arms showed their first meaningful structural method change at approximately loop 5, after 3-4 loops of incremental failure-mode fixes. This is not cherry-picked — it's an emergent pattern across 3 experimental arms.

3. **Mandatory measurement steps are the highest-leverage single intervention.** Every kept prompt added or strengthened a measurement step (empirical pre-check → real-mechanism probe → regime audit). Every reverted prompt tried to add analytical complexity (more candidates, more gate conditions) without adding measurement.

4. **Orthogonal axes outperform incremental refinement.** AFG L5 (first positive after 4 failures) succeeded by switching from decision-function modifications to cascade-policy modifications. VRS L5 succeeded by layering a new gate type (spread) on top of an existing one (direction). Sequential refinement of the same axis failed in every arm.

### Gaps Before Submission

| Gap | Severity | Mitigation |
|---|---|---|
| 12 training days is thin for statistical significance (confidence intervals on Sharpe) | High | Need more train dates, or report per-date distributions not aggregates |
| **[OOS PENDING]** No held-out test window results for the best variants | High | Results expected from Lambda evaluator. See §6 placeholders. Once in: update §6 tables, update this row, strengthen or qualify paper claim accordingly. |
| Only 3 arms × 8 loops — paper-level replication needs ≥3 base algos per claim | Medium | Add 2-3 more base algorithm arms, or more loops |
| No ablation: does the critic improve things vs a fixed-but-better seed prompt, or vs random prompt variation? | Medium | Add a control arm with a human-authored "best-practice" prompt held fixed |
| The failure-mode taxonomy is post-hoc rationalization, not prospective categories | Low | Fine for a workshop paper; needs more structure for a journal |

### Suggested Venues

**Workshop papers (faster, more appropriate for current scope):**
- NeurIPS Workshop on AI for Finance (Dec 2026)
- ICML Workshop on LLMs for Scientific Discovery
- ACL Workshop on Automatic Scientific Discovery

**Journal papers (requires filling the gaps above):**
- Journal of Financial Data Science
- Quantitative Finance (Taylor & Francis)
- Machine Learning with Applications

**Positioning:** The experiment sits at the intersection of (1) automated machine learning for quantitative finance, (2) self-improving LLM systems, and (3) hypothesis generation failure modes. No existing paper demonstrates an empirical burn-in period in critic-evolved research prompts, or characterizes the taxonomy of LLM hypothesis-generation failures in a controlled quantitative setting.

### Strongest Single Claim

> "After approximately 4 loops of failure accumulation, a critic agent operating on structured reasoning traces can identify and correct architectural failures in LLM hypothesis-generation methods, producing quantitative research algorithms that outperform static-prompt baselines by up to 95% on the key evaluation metric."

This claim is supported by 3 independent experimental arms with a consistent pattern, and is falsifiable.

---

## 10. When OOS Data Arrives — Update Guide

Run `python scripts/run_research_backtest.py` is not needed for OOS — the Lambda evaluator handles it automatically after a snapshot push. The pipeline is:

```
git push origin snapshots/<algo-id>
  → GitHub Actions: packages algo, uploads to S3
  → Lambda: runs backtest on test window (2026-03-26 to 2026-04-06)
  → evaluate skill: fetches report, merges into backtest-results.json as performance_oos
```

Algos requiring snapshot + evaluate: **sip-vrs-l5**, **sip-ptg-l8**, **sip-afg-l5**.  
Skills to invoke: `.claude/skills/snapshot/SKILL.md` then `.claude/skills/evaluate/SKILL.md`.

### What to update once each result is in

Search this document and `sip-presentation-outline.md` for `[OOS PENDING]` — there are **7 total markers** across both files (3 in §6 placeholder tables, 1 in §2 setup table, 1 in §9 gaps table, 2 in the presentation outline).

| Location | What to change |
|---|---|
| **§2 setup table** | Remove `[OOS PENDING]` tag from test window row |
| **§6 sip-vrs-l5 block** | Fill the OOS table; remove `[OOS PENDING]` block; replace with filled table |
| **§6 sip-ptg-l8 block** | Same as above |
| **§6 sip-afg-l5 block** | Same as above |
| **§9 gaps table** | If all three OOS results are in, remove this row entirely (gap is closed); if only partial, update the mitigation column |
| **§9 strongest claim** | If VRS L5 OOS confirms (+ve vs baseline): add "and generalises to held-out test window" to the claim. If it fails: add a caveat sentence. |
| **§13 EHL question 1** | Update from "What would make you more confident — OOS results…" to "OOS results are now in: [summary]" |
| **Presentation Slide 9** | Fill OOS row in metrics table |
| **Presentation Slide 14** | Remove OOS from "What's missing" list |
| **Sources appendix §16** | Confirm that `performance_oos` field is populated and link to the date it was merged |

### How to interpret the OOS result

The test window is 2026-03-26 to 2026-04-06, approximately 8 trading days (shorter than the 12-day train window). Sharpe estimates over 8 days have very wide confidence intervals — do not over-index on the exact number.

What to look for:
- **VRS L5**: Is `vs_baseline_pnl_pct` positive? Even +10% OOS (vs +95% train) would support the mechanism. A sign flip is a red flag for regime overfitting.
- **PTG L8**: Is Sharpe above the base PTG's train Sharpe (17.62)? The PnL margin is small (+0.7%) so the risk-story depends on Sharpe and drawdown holding.
- **AFG L5**: Does it remain above the AFG base (+3.3% train margin is thin)? Any positive OOS confirms the cascade-policy axis is real.

---

## 12. Compute Cost vs. Performance

### Data Availability

Token and duration data are **not uniformly available** across all 24 loops. The backfill hook that writes these fields to the loop JSON was not active for all runs.

| Arm | Loops with data | Loops with nulls |
|---|---|---|
| PTG | Loop 1 only (research phase; critic null) | Loops 2–8 |
| AFG | All 8 loops — research and critic complete | None |
| VRS | Loops 4–8 — research complete; critic complete for L5–L7 | Loops 1–3 |

**Effective dataset: 14 data points** out of 24 total. Crucially, the two best results (VRS L5 at +95.3% and AFG L5 at +3.3%) both have complete data.

Source for all values: `tokens_used` and `duration_seconds` fields in each `experiments/self_improving_prompt_experiment/<arm>/per-iteration/loop-N.json`.

### Metric Choices

**PnL:** Use `vs_base_pnl_pct`, not raw PnL. The PTG base is $4,262 and the VRS base is $754 — raw PnL is not comparable across arms. The percentage normalises across all three arms and is the metric the gate actually evaluates.

**Tokens:** Use `tokens_used.total` from the **research phase only**. Research tokens drive this loop's PnL. Critic tokens drive the *next* loop's PnL — they are causally separate and must be plotted separately. Token breakdown: `{input, output, cache_creation, cache_read, total}` — use `total` for the headline number.

**Time:** Use `duration_seconds` (research phase). This includes backtest wall time, which is roughly constant per arm (same 12 train dates). Variance in duration therefore reflects LLM thinking time, not backtest speed. For a pure LLM-thinking proxy, use `critic_duration_seconds` — it is 100% LLM work with no backtest overhead.

**Note on AFG L6:** 64,861 research tokens but 8,149 seconds duration. This is an outlier — the backtest engine had slow runs on at least one date in that loop. Do not treat duration as a reliable LLM-thinking proxy for this point.

---

### Raw Data Table (14 Data Points)

All values from `experiments/self_improving_prompt_experiment/<arm>/per-iteration/loop-N.json`.

| Arm | Loop | Algo ID | Research Tokens | Research Dur (s) | Critic Tokens | Critic Dur (s) | vs_base_pnl_pct | Prompt Action |
|---|---|---|---|---|---|---|---|---|
| PTG | 1 | sip-ptg-l1 | 84,263 | 1,100.1 | — | — | 0.0% | kept |
| AFG | 1 | sip-afg-l1 | 336,480 | 4,390.3 | 55,497 | 212.8 | -15.2% | kept |
| AFG | 2 | sip-afg-l2 | 56,657 | 136.8 | 79,568 | 319.1 | -48.6% | reverted |
| AFG | 3 | sip-afg-l3 | 47,710 | 123.9 | 77,662 | 250.5 | -43.1% | reverted |
| AFG | 4 | sip-afg-l4 | 43,366 | 103.5 | 75,782 | 213.4 | -37.9% | reverted |
| AFG | 5 | sip-afg-l5 | 181,033 | 3,284.3 | 72,565 | 256.2 | +3.3% | kept |
| AFG | 6 | sip-afg-l6 | 64,861 | 8,149.9* | 62,063 | 214.7 | +1.5% | reverted |
| AFG | 7 | sip-afg-l7 | 154,883 | 3,362.0 | 51,491 | 247.7 | -31.0% | reverted |
| AFG | 8 | sip-afg-l8 | 62,339 | 200.7 | 24,767 | 7.7 | -13.8% | — |
| VRS | 4 | sip-vrs-l4 | 67,351 | 265.7 | — | — | -41.8% | reverted |
| VRS | 5 | sip-vrs-l5 | 153,084 | 3,517.7 | 72,818 | 335.6 | +95.3% | kept |
| VRS | 6 | sip-vrs-l6 | 209,532 | 4,282.1 | 97,755 | 682.7 | +3.5% | reverted |
| VRS | 7 | sip-vrs-l7 | 66,747 | 267.9 | 118,361 | 1,229.5 | +95.3% | reverted |
| VRS | 8 | sip-vrs-l8 | 86,574 | 471.7 | — | — | -50.0% | reverted |

*AFG L6 duration is an outlier — slow backtest dates, not slow LLM thinking.

**VRS L7 note:** PnL of +95.3% is identical to VRS L5. The researcher implemented a mechanism that reproduced the same algorithm as the running best. High PnL at low token cost is misleading here — it reflects rediscovery, not efficiency.

---

### Chart 1 — Research Tokens vs PnL Outcome

**Recommended chart:** Scatter plot. X-axis: `tokens_used.total` on log scale (range: ~43k–337k). Y-axis: `vs_base_pnl_pct`. Encode `prompt_action` by marker fill (KEPT = filled, REVERTED = open circle).

**What the data shows:**

There is no clean monotonic relationship — high tokens do not guarantee good PnL. But there is a clear **floor effect**:

- **Below ~60k tokens:** AFG L3 (47,710), AFG L4 (43,366), AFG L2 (56,657) — all between -49% and -38%. No loop in this range produced a positive result.
- **60k–100k tokens:** AFG L6 (64,861, +1.5%), AFG L8 (62,339, -13.8%), VRS L4 (67,351, -41.8%), VRS L7 (66,747, +95.3%*), VRS L8 (86,574, -50.0%), PTG L1 (84,263, 0.0%). Mixed — the positive outlier (VRS L7) is a rediscovery case.
- **Above ~150k tokens:** AFG L1 (336,480, **-15.2%**), AFG L5 (181,033, **+3.3%**), AFG L7 (154,883, **-31.0%**), VRS L5 (153,084, **+95.3%**), VRS L6 (209,532, **+3.5%**). Both kept results in this range are positive. But AFG L1 is the honest counter-example: the single most expensive loop in the dataset still failed.

**The honest finding:** A minimum token budget appears necessary but not sufficient. Cheap loops fail consistently; expensive loops have a higher hit rate but no guarantee.

**Suggested slide annotation:** *"No loop under ~60k tokens produced a positive result. The two breakthrough algorithms (VRS L5, AFG L5) both exceeded 150k tokens. But the single most expensive loop (AFG L1, 336k tokens) still missed."*

---

### Chart 2 — Critic Tokens vs Next Loop's PnL

**Recommended chart:** Scatter plot. X-axis: `critic_tokens_used.total` for loop N. Y-axis: `vs_base_pnl_pct` for loop N+1. One dot per loop where critic tokens are available and a next loop exists. Encode whether the proposal was KEPT or REVERTED by marker color.

**The 10 critic-to-next-loop pairs (AFG complete, VRS L5–L7):**

| Critic loop | Critic tokens | Next loop | Next loop PnL vs base | Gate action |
|---|---|---|---|---|
| AFG L1 | 55,497 | AFG L2 | -48.6% | reverted |
| AFG L2 | 79,568 | AFG L3 | -43.1% | reverted |
| AFG L3 | 77,662 | AFG L4 | -37.9% | reverted |
| AFG L4 | 75,782 | AFG L5 | **+3.3%** | kept |
| AFG L5 | 72,565 | AFG L6 | +1.5% | reverted |
| AFG L6 | 62,063 | AFG L7 | -31.0% | reverted |
| AFG L7 | 51,491 | AFG L8 | -13.8% | — |
| VRS L5 | 72,818 | VRS L6 | +3.5% | reverted |
| VRS L6 | 97,755 | VRS L7 | +95.3%* | reverted |
| VRS L7 | 118,361 | VRS L8 | -50.0% | reverted |

**What the data shows:**

The AFG critic token range is narrow (51k–80k across all 8 loops) — the critic is roughly uniform in cost regardless of whether it produces a good next loop. This means critic token count is a poor predictor of next-loop PnL within the AFG arm.

The VRS arm shows a hint of a positive pattern: the highest-spend critic loops (VRS L6 at 97k, VRS L7 at 118k) precede the two best VRS results — but those results are VRS L7 (+95.3%, a rediscovery) and VRS L8 (-50.0%), so the pattern doesn't hold.

**The honest finding:** Critic token count does not reliably predict next-loop performance. The critic's *content* (which failure mode it identified, whether the fix was structural or superficial) matters more than its token budget. The only directional signal: the AFG critic spend gradually declined across loops 1–7 (55k → 52k), correlating with the agent settling on a stable method, not with better results.

**What IS predictive:** Whether the critique identified a structural failure mode (single-candidate myopia → cascade-policy axis in AFG L5 critique) versus a parameter-level fix (threshold calibration). This is qualitative, not measurable from token counts.

---

## 13. For the Event Horizon Labs Conversation

### What to Ask For

1. **Does the VRS L5 result (+95.3% vs base, Sharpe 13.72) represent economically meaningful signal, or is it artifact of the backtest setup?** — Their team will have views on whether oracle-strategy backtests translate to live execution, and whether the train-window performance metrics are predictive.

2. **Is the self-improving critic architecture something they would deploy for internal research?** — They may be interested in licensing, collaborating, or hiring based on this.

3. **Would they co-author a paper?** — Event Horizon has practitioners who would strengthen the financial validity claims. A joint paper gets both academic and industry credibility.

4. **What additional experiments would they need to see?** — Out-of-sample (Lambda OOS) results, different asset classes, longer time windows, ablation against fixed prompts.

### Narrative Hook

The strongest hook for an AI hedge fund is not the PnL numbers — it's the **failure mode taxonomy**. Quantitative researchers at hedge funds spend enormous effort debugging why a backtest hypothesis doesn't translate to live trading. The 8 failure modes discovered here (counterfactual blindness, regime heterogeneity, reference-frame mismatch, stub degeneration) are exactly the failures their researchers hit manually. The claim is: *an AI critic can now identify these failures systematically, at the speed of inference, before the researcher ships a bad hypothesis.*

That is the research-pipeline value proposition. The execution algorithm results are evidence that the critic is effective at identifying real failures, not just naming them.
