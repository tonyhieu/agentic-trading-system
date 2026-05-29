# Hypothesis Generation Method — base_algo=aggressor-flow-gate (loop 3+)

You are an execution-algorithm researcher. Produce ONE hypothesis for `<algo-id>` that you believe will beat `<base_algo>` on the train window's realized P&L without meaningfully worse slippage. Implementation and backtesting are handled by surrounding infrastructure — do not include them here.

Loop 2's method correctly forced three candidates and a mandatory EDA gate, and picked the candidate with the strongest statistical signal (t=-41 SELL-skip inversion across 562k events). But its EDA sampled every TradeTick where `|net_v| >= 2`, while gating decisions in the backtest happen at oracle order-arrival times (~1Hz, much more uniform). The researcher named this concern but the method had no mechanism to act on it. Loop-2's pre-registered falsifier ("trade_count rises >3% but P&L falls") was triggered exactly: trade_count went +12.84% as predicted, realized_pnl fell -48.6%. The tick-level signal did not transfer to the arrival distribution. **Fix: the EDA must be evaluated at the same sampling distribution the backtest will see — at the strategy's order-arrival times, not at arbitrary tick events. A candidate whose tick-level signal evaporates under arrival-cadence resampling is dead.**

This method is **proposer–EDA-grounded–gate-aligned-criticizer**. The change vs loop 2 is a new Step 3b gate-alignment EDA pass that every candidate must pass to survive.

## Step 1 — Read context

Read in order:
1. `execution_algos/<base_algo>/execution_algorithm.py`
2. `execution_algos/<base_algo>/NOTES.md`
3. `execution_algos/<base_algo>/results/backtest-results.json`
4. `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json` — every prior loop's algo_id, mechanism family, action, delta vs base.
5. `research/config.yaml` for `data_window.train`, `execution_constraints`, and any strategy fields implying order-arrival cadence (e.g. `signal_interval_seconds`).

You may not read other entries in `execution_algos/` or other experiments. Write a 3–6 line summary: base mechanism, the single inefficiency claim, what prior loops tried, which directions are still open, and the strategy's order-arrival cadence in seconds (default 1.0s if not exposed).

## Step 2 — Propose THREE candidate mechanisms

Generate exactly THREE distinct candidate modifications. Each must:
- name a SPECIFIC weakness in the base algo's mechanism,
- name a SPECIFIC modification (one concrete code-level change),
- state the predicted direction and rough magnitude of the P&L change,
- name the ONE data assumption the prediction most depends on.

Three candidates MUST be mechanistically distinct. Do NOT pick a family already tried with the same intent in the program_database.

Write to `execution_algos/<algo-id>/NOTES.md → ## Candidates Considered`.

## Step 3 — Tick-level EDA (assumption survival)

For EACH candidate, run a SHORT EDA on 1–2 dates in `data_window.train` (NOT test — that is data leakage). Use the `analysis` skill mechanics. Produce ONE concrete number that supports or weakens the key assumption.

Write to `NOTES.md → ## EDA Findings (tick-level)`: dates loaded, the decisive number, survives or falsified.

If falsified, the candidate is dead. If zero survive, return to Step 2.

## Step 3b — Gate-alignment EDA (mandatory survival gate)

**This is what loop-2 was missing. Do not skip it.**

For EACH Step-3 survivor, re-sample the decisive number at the **order-arrival cadence the backtest will use**:

1. Pick ONE date from `data_window.train` (may reuse a Step-3 date — record which).
2. Build a synthetic order-arrival stream at the strategy's cadence (one decision point every cadence-seconds of wall-time across the session). If cadence not exposed, use 1.0s and flag it.
3. At each synthetic arrival, evaluate the candidate's gate state on the same rolling buffer the algorithm would maintain, and record the same conditional outcome Step 3 measured (e.g. 30s-ahead drift, skip value).
4. Compute the SAME decisive number as Step 3, but over this arrival-sample distribution.

Write to `NOTES.md → ## EDA Findings (gate-aligned)`: date, n arrivals, the decisive number, and its **delta** vs Step 3.

**Survival criterion (hard):**
- Sign agrees with Step 3 AND magnitude ≥ 50% of Step-3 magnitude AND (if Step 3 used a t-stat) |t| ≥ 5 on the arrival-sampled set → survives.
- Sign flips, OR magnitude < 50%, OR |t| < 5 → **killed by sampling-distribution shift.** This is the failure mode that destroyed loop-2.
- If the candidate's parameter (threshold, window, side selection) implies a per-arrival firing rate, compute and report that rate on the arrival-aligned sample.

If zero survive, do NOT ship the least-bad — return to Step 2 with `## ESCALATION` in NOTES.md. After two failed Step 2/3/3b cycles, write `## ESCALATION (terminal)`, pick the least-falsified candidate, and document the sampling-shift gap you are accepting.

## Step 4 — Criticize the survivors

For each Step-3b survivor, attack it. Must cover:
- Could the mechanism interact badly with `top_of_book_only`, `participation_cap`, `intraday_flat`, or the quantity invariant?
- Does the predicted P&L direction depend on a sub-assumption that NEITHER Step 3 nor Step 3b tested?
- What is the predicted `trade_count` change AT THE ARRIVAL-CADENCE rate from Step 3b — and is the P&L claim consistent with THAT count, not the tick-level count?
- Is every quantitative parameter justified by a Step-3 or Step-3b number? If a parameter rests on Step 3 alone, flag the sampling-shift risk.
- State interaction: if the candidate changes when a gate fires, does the base algo have any flag (e.g. `_position_flat`) set on every-side skips that now needs to be set on only the gating side? Name the line and the fix.

Write to `NOTES.md → ## Critique`.

## Step 5 — Select ONE survivor and write the hypothesis

Pick the candidate with strongest combination of (a) Step-3 support, (b) Step-3b gate-aligned support (more important), (c) parameters justified by Step-3 / Step-3b numbers, (d) most-survived critique.

Write to `NOTES.md → ## Hypothesis`:
- **Mechanism** — one paragraph.
- **Inefficiency exploited** — which specific weakness it addresses.
- **Why it survives costs** — what does NOT change (constraints preserved).
- **Quantitative anchors** — every numeric parameter with its Step-3 AND Step-3b number. A parameter may rest on Step-3 alone only if inherited unchanged from the base.
- **Predicted outcome** — directions and magnitudes for `realized_pnl`, `mean_slippage`, `trade_count`, `is_weighted_bps`. The `trade_count` prediction MUST be derivable from the Step-3b arrival-aligned gate-firing rate, not the tick-level rate.
- **What would falsify this hypothesis** — name ONE result that invalidates the mechanism, and that the Step-3b EDA has NOT already ruled out (i.e. tests a genuine unknown).
- **Alternatives considered and rejected** — one sentence each for the two non-picked candidates, including whether they died at Step 3 (tick-level) or Step 3b (gate-alignment).

## Boundaries (hard)

- Keep each NOTES.md section under ~500 words; signal over verbosity.
- Do NOT read test-window dates during EDA — train only, for both Step 3 and Step 3b.
- Do NOT read other experiments or other tracks' algorithm code; only `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- Every quantitative parameter must have a Step-3 or Step-3b number. No armchair numbers.
- ONE concrete modification per hypothesis. Do not stack multiple changes.
- Step 3b is non-optional. Loop-2 shipped a hypothesis whose tick-level signal (t=-41) did not transfer to the arrival distribution; do not repeat that.
- On ambiguity, pick the more conservative interpretation (more EDA, tighter survival, less commitment) and note it.
