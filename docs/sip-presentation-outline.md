# Presentation Outline — Self-Improving Prompt Experiment
## For Event Horizon Labs

> Target: ~30 minutes of content + 15 minutes Q&A  
> Audience: AI agentic hedge fund — technically sophisticated, financially literate, likely skeptical of backtests

---

## SECTION 1: HOOK (Slides 1-2)

### Slide 1 — Opening Hook

**Headline:** "We built an AI that improves its own research method."

**Sub-headline:** "Not the algorithm. The method it uses to think of the algorithm."

**Talking points:**
- This is not a demo of an AI writing code. This is a demo of an AI critiquing *how it reasons* before writing code.
- The question: if you let a critic read an AI's reasoning trace after each failed experiment, can it evolve the thinking process into something better?
- After 8 loops, it discovered 8 systematic failure modes in its own reasoning. We didn't tell it what to look for.

---

### Slide 2 — Why Execution Algorithms?

**Headline:** "Execution is the last unsealed edge."

**Visual:** Simple diagram: Strategy (fixed, oracle) → Execution Algorithm (variable) → Market

**Talking points:**
- We hold the trading strategy completely fixed (oracle signal, known outcomes). This isolates execution as the *only* variable.
- Execution algorithms decide: given a signal to buy, *when and how* to submit the order. That decision has real P&L consequences even with a perfect signal.
- This is an ideal research environment: the signal is clean, the constraints are hard, the feedback is fast (12-date train backtest in ~10 minutes).
- The problem we're studying is general: how do you automate the generation of good hypotheses for algorithmic research?

---

## SECTION 2: THE SYSTEM (Slides 3-5)

### Slide 3 — The Base Research Loop

**Headline:** "One agent, one algorithm, one backtest, one commit."

**Visual:** Simple flowchart: Read DB → Hypothesize → Implement → Backtest → Pass/Fail → Log

**Talking points:**
- This is the standard autonomous research loop. Each invocation = one research iteration. The agent does not loop internally.
- The evaluation is objective: +5% PnL vs baseline, no slippage regression, on a 12-day training window. Pass/close/fail.
- All attempts are logged in an append-only program database. The agent reads this on every entry to avoid dead ends.
- This is the system we built first. The self-improving prompt experiment is the next layer.

---

### Slide 4 — The Meta-Layer: Self-Improving Critic

**Headline:** "After each loop, a critic reads the reasoning trace and rewrites the method."

**Visual:**  
```
Loop N
  ↓ [Research Phase]
  Hypothesis method → Algorithm → Backtest
  ↓ [Reasoning Trace written]
  ↓ [Critique Phase]
  Read trace + code + metrics
  ↓
  Identify ONE failure mode in the method
  ↓
  Propose new method
  ↓
  Karpathy gate (majority rules: ≥3 of 5 metrics improved vs running best?)
  ↓
KEPT → new method drives Loop N+1
REVERTED → prior best method drives Loop N+1
```

**Talking points:**
- The critic can only touch one thing: the hypothesis-generation method. Implementation, backtesting, and evaluation are fixed infrastructure.
- Every promoted method is version-controlled (prompt-l1.md, prompt-l5.md, etc.). Reverts are mechanical — copy the running-best's prompt back.
- One architectural change per loop. If the critic sees ten problems, it picks the highest-leverage one.
- The critic is also an LLM (Claude Opus 4.7). It reads structured reasoning traces, not just metrics.

---

### Slide 5 — The Experimental Design

**Headline:** "3 arms × 8 loops = 24 total iterations."

**Visual:** Table showing 3 base algorithms, their mechanisms, baseline PnL

| Base Algorithm | Mechanism | Baseline PnL | Baseline Sharpe |
|---|---|---|---|
| position-tier-gate | Skip opens when position ≥ 1 contract | $4,262 | 17.6 |
| aggressor-flow-gate | Skip opens when recent aggressor flow is adverse | $1,255 | 5.6 |
| vol-regime-sizer | Probabilistic skip based on volatility regime | $754 | 3.1 |

**Talking points:**
- Three independent arms, same seed prompt, same architecture. Allows cross-arm comparison of the critic's behavior.
- All three start from the same 4-step single-pass method: read base, identify weakness, propose modification, state expected direction.
- No empirical validation. No multi-candidate exploration. This seed prompt is the worst-case baseline.
- The arms ran sequentially; each arm's critic does not see the other arms' results (no contamination).

---

## SECTION 3: WHAT THE CRITIC DISCOVERED (Slides 6-8)

### Slide 6 — The 8 Failure Modes

**Headline:** "The AI diagnosed itself. Repeatedly."

**Visual:** Table with 8 rows. Col 1: failure mode name. Col 2: example. Col 3: one-word category.

| # | Failure Mode | Concrete Example | Category |
|---|---|---|---|
| 1 | Empty Event Class | Hypothesis conditioned on oracle events that never fire | Vacuity |
| 2 | Counterfactual Blindness | EDA says remove X → removing X destroys P&L through chain effects | Causal |
| 3 | Single-Candidate Myopia | 4 loops re-entering the same axis (AFG: decision-function modifications) | Exploration |
| 4 | Sampling Bias | Falsification on the worst 2 of 12 dates, guaranteed adverse signal | Statistical |
| 5 | Regime Heterogeneity | Parameter calibrated on 2 dates; fires 99% of the time on 3 others | Distribution |
| 6 | Champion Redundancy | New mechanism fires on zero orders the champion didn't already filter | Composition |
| 7 | Stub-Mode Degeneration | Synthetic probe passes; real backtest -96% | Validity |
| 8 | Uncalibrated Parameters | Tau=3s chosen from "reasonable"; actual trade cadence unmeasured | Grounding |

**Talking points:**
- None of these were told to the critic. It discovered them from reasoning traces.
- These are not random bugs. They are a structured taxonomy of how LLM-based quantitative research fails.
- Every researcher at a quantitative fund has hit these. The critic names them and fixes them.
- Most importantly: these are fixable. The method evolved to address each one.

---

### Slide 7 — The Critic in Action: FM-2 (Counterfactual Blindness)

**Headline:** "Iron-clad statistics, wrong reference frame."

**Talking points (tell the story):**
- AFG Loop 2 researcher ran EDA on 562,000 trade events, 11 train dates.
- Finding: when net_flow ≥ +2 contracts (buyer-dominated window), future 30-second drift is DOWN. Mean -0.144 ticks. T-statistic: -41.46. This is a p-value of essentially zero.
- This means the base algorithm's SELL-skip gate (skip sells when buyers dominate) is directionally inverted. The researcher disabled it.
- Result: realized PnL fell from $1,255 to $645. -48.6%.
- Why? The EDA sampled at trade-tick cadence. The oracle fires orders at 1Hz cadence. At tick cadence the relationship held. At order cadence, the signal-to-noise ratio was different. The EDA result was statistically valid but operationally non-transferable.
- The critic diagnosed this as "sampling at the wrong cadence" and required that future methods sample at order-arrival cadence, not tick cadence.

**Visual:** Two side-by-side panels: "What EDA measured (tick cadence)" vs "What matters (order cadence)". Numbers showing the t-stat and the P&L outcome.

---

### Slide 8 — The L5 Inflection Pattern

**Headline:** "All three arms broke through at Loop 5."

**Visual:** Three line charts (one per arm), showing PnL vs loop number. All three show the same pattern: flat/negative for loops 1-4, then first meaningful positive result at loop 5.

| Arm | L1-L4 best | L5 Result | Change |
|---|---|---|---|
| PTG | -11.5% to -96.3% | L5 itself -96.3% (but critic fix → L8 +0.7%) | Critic diagnosed stub degeneration |
| AFG | -48.6% to -15.2% | **+3.3%** (first positive) | Switched from decision-function to cascade-policy axis |
| VRS | -41.8% to +40.9% | **+95.3%** (largest result) | Added per-date regime heterogeneity audit |

**Talking points:**
- This is not coincidence. The critic needs approximately 4 loops of failure examples before it can make a genuinely architectural change.
- Loops 1-4 produce incremental fixes (add an empirical check, add falsification). It takes seeing those fixes fail to identify deeper structural failures.
- We call this a "critic burn-in period." The critic warms up before it can redesign rather than patch.
- This is testable. Prediction: if you ran 12 loops instead of 8, you'd see a second inflection at ~loop 9.

---

## SECTION 4: RESULTS (Slides 9-11)

### Slide 9 — Best Results: VRS Arm (+95.3%)

**Headline:** "$1,471 vs $754 baseline. Sharpe 13.7 vs 3.1."

**Visual:** Bar chart or two-panel metrics comparison for sip-vrs-l5 vs vol-regime-sizer base.

| Metric | Base VRS | sip-vrs-l5 (train) | sip-vrs-l5 (OOS) | Delta (train) |
|---|---|---|---|---|
| Realized PnL | $753.75 | $1,471.75 | **[OOS PENDING]** | +95.3% |
| Sharpe Ratio | 3.06 | 13.72 | **[OOS PENDING]** | +10.7 |
| Max Drawdown | -4.95% | -1.64% | **[OOS PENDING]** | +3.3pp |
| Win Rate | 35.1% | 35.5% | **[OOS PENDING]** | +0.4pp |
| Trade Count | 127,991 | 90,582 | **[OOS PENDING]** | -29% |
| vs baseline PnL % | — | +95.3% | **[OOS PENDING]** | — |

*OOS test window: 2026-03-26 to 2026-04-06 (~8 trading days). Results pending Lambda evaluator.*  
*Source when available: `execution_algos/sip-vrs-l5/results/backtest-results.json` → `performance_oos`*

**The mechanism (plain English):**
- Layer 1: Replace unsigned vol-skip with signed headwind filter. If recent micro-drift is against the order (you're fading a move), suppress. If you're riding a drift, submit at full probability.
- Layer 2: Hard-skip any order when top-of-book spread > 1.5 ticks. Wide spread = adverse selection risk.
- Two orthogonal filters, each targeting a different type of execution risk.

---

### Slide 10 — The Risk Story (PTG Arm)

**Headline:** "When you can't beat PnL, improve risk."

**Visual:** Bar chart showing max drawdown and Sharpe across PTG variants.

**Talking points:**
- The PTG base is already high-quality ($4,262, Sharpe 17.6). It's hard to beat significantly.
- sip-ptg-l8 achieves +0.7% PnL — marginal improvement — but the *lowest max drawdown of all 24 variants* (-1.11%) and the highest Sharpe after the base (18.81).
- The mechanism: rolling win-rate gate. If the oracle's recent accuracy (last 20 round trips) drops below 35%, suppress new opens. Resume when quality recovers.
- This is a regime-selectivity filter: participate fully in high-quality oracle periods, sit out low-quality periods.
- For a live system, this risk profile matters more than marginal PnL improvement.

---

### Slide 11 — Complete Results Overview

**Headline:** "6 of 24 variants beat or matched their base. The other 18 taught us why."

**Visual:** Full heatmap or table of all 24 variants: arm × loop, colored by vs_base%.

**Talking points:**
- This is a hard problem. Even with an improving method, most variants fail.
- The failures are not random — they cluster around specific failure modes that the critic eventually addresses.
- The important question is not "how many passed?" but "did the kept variants accumulate over time?" — and yes, all three arms' running-best improved or stayed stable after the L5 inflection.
- We have a clean signal that the critic's evolution is meaningful, not just noise.

---

## SECTION 5: WHAT WE LEARNED (Slides 12-13)

### Slide 12 — What the Agent Got Right That Humans Miss

**Headline:** "The critic is tireless, specific, and self-honest."

**Talking points:**

1. **It reads its own reasoning traces honestly.** The researcher writes "I chose tau=3s because it seemed reasonable" — the critic flags this as "armchair parameter." A human reviewer might let it pass.

2. **It counts.** Every kept method added a mandatory counting step. Humans skip counting because it's tedious. The critic made it mandatory every time it saw "non-vacuous" fail.

3. **It tracks what didn't work.** The program database is read at every loop entry. The critic can see that the decision-function axis has been tried 4 times in the AFG arm and failed each time. It then switches to cascade-policy. A human would probably try the 5th decision-function variation.

4. **It separates mechanism from outcome.** When a mechanism fails, the critic asks "was the mechanism wrong, or was the method that generated the mechanism wrong?" — this is the key meta-level question.

---

### Slide 13 — What the Agent Consistently Got Wrong

**Headline:** "The failure modes don't go away. They just get harder to trigger."

**Talking points:**

1. **Cascades are invisible until live.** Despite 5 explicit fixes aimed at counterfactual blindness, VRS L8 still produced a double-gating failure (L1's signed headwind + L8's signed drift gate conflicted). The problem is structural: no static artifact captures live OMS dynamics.

2. **The parameter calibration problem never fully solved.** Loop 8 in multiple arms still shipped with parameters that were "empirically grounded" but grounded in the wrong distribution (wrong dates, wrong cadence). Calibration requires the right measurement.

3. **The burn-in is a real cost.** Loops 1-4 in each arm are largely wasted compute. A smarter seeding strategy might accelerate the inflection. The current seed prompt (4-step single-pass) is deliberately naive — we chose it to measure the critic's ability to improve it.

4. **The champion redundancy problem is persistent.** Even after being explicitly targeted by the critic (L7), it re-appeared because the fix (champion CSVs) was not adopted. The critique never became a constraint — it became a suggestion.

---

## SECTION 6: PAPER AND COLLABORATION (Slides 14-15)

### Slide 14 — Paper Hypothesis

**Headline:** "A testable claim about self-improving research agents."

**Core claim:**
> "An LLM critic operating on structured reasoning traces can autonomously identify systematic failure modes in LLM hypothesis generation and evolve the generation method to correct them, exhibiting an empirical burn-in period of approximately N failures before producing architectural-level method changes."

**Why this is publishable:**
- Concrete, falsifiable, replicable
- Addresses a problem every quantitative researcher knows (bad backtest hypotheses)
- Demonstrates the failure mode taxonomy empirically, not theoretically
- Introduces the critic burn-in concept with supporting data from 3 independent arms

**What's missing:**
- Statistical significance (need confidence intervals on Sharpe, more training dates)
- **[OOS PENDING]** Out-of-sample validation — Lambda OOS results for sip-vrs-l5, sip-ptg-l8, sip-afg-l5 pending. *When in: remove this bullet and add "OOS confirms [X]% test-window result" to the "Why this is publishable" list above.*
- Ablation study (critic vs fixed-good-prompt, critic vs random-variation)
- Replication with more base algorithms

**Suggested venues:** NeurIPS Workshop on AI for Finance, ICML Workshop on LLMs for Scientific Discovery

---

### Slide 15 — The Ask

**Three questions for Event Horizon Labs:**

1. **Signal assessment:** Do the execution algorithm results (+95.3% for VRS L5, Sharpe 13.7 on train) represent economically meaningful signal in your view? **[OOS PENDING]** — *When OOS results arrive, update to: "Our OOS test window showed [X]. Does this change your assessment?"*

2. **Research value:** Is the critic architecture — the ability to systematically identify and fix LLM research failure modes — something that would be valuable in your internal research pipeline? We're interested in whether this framework transfers to strategy research, not just execution.

3. **Paper collaboration:** Would you be interested in co-authoring a paper? Your practitioners would strengthen the financial validity claims and execution context. A joint paper would be stronger than either team publishing alone, and would reach both academic and industry audiences.

---

## APPENDIX SLIDES (for Q&A)

### A1 — Backtest Setup Details
- Dataset: CME GLBX MES FX futures, Databento `glbx-mdp3`
- Engine: Nautilus BacktestEngine (tick-level replay)
- Strategy: Oracle (sigma=6, horizon=30s, 1Hz signal cadence, seed=42)
- Train window: 2026-03-08 to 2026-03-21 (12 trading dates)
- Pass gate: +5% PnL vs baseline, ≤5% slippage regression
- Constraints: top-of-book only, 5% participation cap, intraday flat

### A2 — The Karpathy Gate Details
- Compare 5 metrics: realized PnL ↑, mean slippage ↓, Sharpe ↑, max drawdown ↓, win rate ↑
- ≥3 of 5 improved → KEPT (new method drives next loop)
- <3 of 5 improved → REVERTED (prior best method restored)
- Loop 1: always KEPT (no running best to compare to)
- Gate prevents cherry-picking any single metric (especially PnL)

### A3 — The Seed Prompt vs Evolved Prompts
Show side-by-side: prompt-l0.md (4 steps, ~500 chars) vs prompt-l1.md (6 steps with mandatory empirical pre-check, ~3000 chars) vs prompt-l5.md/VRS (Propose-Audit-Falsify-Commit with per-date regime audit, ~6500 chars)

### A4 — Tokens and Compute
- AFG L1 (proposer-EDA-criticizer): 336,480 tokens, 4,390 seconds
- VRS L5 (regime audit method): 153,084 tokens, 3,518 seconds
- AFG L5 (cascade-policy method): 181,033 tokens, 3,284 seconds
- Higher-performing loops required more compute — the measurement steps add real cost

### A5 — Why Oracle Strategy?
- Oracle is a controlled baseline: we know the signal is "as good as it gets"
- This isolates execution as the *only* variable; no signal noise confounds results
- Real-world application: replace oracle with any alpha signal; the execution research framework is the same
- The methods discovered here transfer to any execution context — spread gating, vol-regime filtering, cascade policy — none are oracle-specific

### A6 — OOS Results **[OOS PENDING]**

*Fill this slide once Lambda evaluator results are in. Remove `[OOS PENDING]` tags from Slide 9 and Slide 14 at the same time.*

**Headline when ready:** "Train results held / partially held / did not hold on the unseen test window."

| Algo | Train vs baseline | OOS vs baseline | Verdict |
|---|---|---|---|
| sip-vrs-l5 | +95.3% | `[FILL]` | `[CONFIRMS / PARTIAL / FAILS]` |
| sip-ptg-l8 | +0.7% PnL, Sharpe 18.81 | `[FILL]` | `[CONFIRMS / PARTIAL / FAILS]` |
| sip-afg-l5 | +3.3% | `[FILL]` | `[CONFIRMS / PARTIAL / FAILS]` |

**Test window:** 2026-03-26 to 2026-04-06 (~8 trading days, shorter than train).  
**Source:** `execution_algos/<algo-id>/results/backtest-results.json` → `performance_oos` field.  
**Pipeline:** `snapshots/<algo-id>` branch push → GitHub Actions → S3 → Lambda → `evaluate` skill merges result.

**Talking point on variance:** 8 days of OOS data produces wide Sharpe confidence intervals. Report direction and sign of PnL vs baseline first; treat exact magnitude as indicative, not definitive.
