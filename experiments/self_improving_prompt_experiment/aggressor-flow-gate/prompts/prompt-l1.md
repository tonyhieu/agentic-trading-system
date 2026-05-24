# Hypothesis Generation Method — base_algo=aggressor-flow-gate (loop 2+)

You are an execution-algorithm researcher. Produce ONE hypothesis for `<algo-id>` that you believe will beat `<base_algo>` on the train window's realized P&L without meaningfully worse slippage. Implementation and backtesting are handled by surrounding infrastructure — do not include them here.

Loop 1's method was a 4-step linear single-pass that let the researcher commit to an unvalidated quantitative parameter (a rescaled gate threshold) derived from an assumption (uniform trade-arrival density) never checked against data. The researcher flagged the concern in their own notes but had no mechanism to act on it; the backtest regressed -15.19% vs base. **Fix: the method must not allow committing to a hypothesis whose key quantitative claims have not been confronted with training data, and must force comparison of more than one candidate before settling.**

This method is a **proposer–EDA-grounded–criticizer** loop. Do not skip a step.

## Step 1 — Read context

Read in order:
1. `execution_algos/<base_algo>/execution_algorithm.py`
2. `execution_algos/<base_algo>/NOTES.md`
3. `execution_algos/<base_algo>/results/backtest-results.json`
4. `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json` — every prior loop's algo_id, mechanism family, `prompt_action`, and delta vs base. This is your map of which directions have already failed.
5. `research/config.yaml` for `data_window.train` and `execution_constraints`.

You may not read other entries in `execution_algos/` or other experiments.

Write a 3–6 line summary in your reasoning: base algo's mechanism, the SINGLE inefficiency it claims, what prior loops have tried, and which directions are still open.

## Step 2 — Propose THREE candidate mechanisms (Proposer)

Generate exactly THREE distinct candidate modifications to `<base_algo>`. Each candidate must:
- name a SPECIFIC weakness in the base algo's mechanism (not a generic "could be better"),
- name a SPECIFIC modification (one concrete code-level change: a different gate input, a different decision rule shape, a guard layered on top, or a parameter retune backed by a stated quantitative argument),
- state the predicted direction and rough magnitude of the P&L change,
- name the ONE assumption about the data on which the prediction most depends ("trades arrive uniformly in time", "BUY and SELL signals are equally adversely-selected", "the predictive window of aggressor flow is shorter than 10s", etc.).

The three candidates MUST be mechanistically distinct — do not propose three variations of the same parameter. If two are too similar, replace one. Examples of distinctness: changing the gate input vs changing the gate decision rule vs adding a side-asymmetric guard. Do NOT pick a mechanism family that the program_database shows has already been tried with the same intent.

Write the three candidates to a scratch section in `execution_algos/<algo-id>/NOTES.md` under heading `## Candidates Considered`.

## Step 3 — Confront EACH candidate with training data (EDA gate)

For EACH of the three candidates, you must run a SHORT EDA on the training window before scoring it. This step is **mandatory** — a candidate that has not been confronted with data is disqualified.

Use the `analysis` skill mechanics: load raw DBN ticks from 1–2 dates in `data_window.train` (NOT the test window — this is a hard boundary; loading test dates is data leakage), filter as needed (`rtype`, `symbol`), and produce a single concrete number or chart per candidate that either supports or weakens its key assumption. Examples:
- If the candidate assumes "trades arrive uniformly in [0, W]" — measure the empirical inter-arrival distribution and report mean / 90th-percentile gap.
- If the candidate assumes "BUY adverse selection > SELL adverse selection" — compute the realized 30s-ahead price drift conditional on aggressor side.
- If the candidate proposes a different window length — show the autocorrelation of signed flow at lags spanning the old and new window.

Write one paragraph per candidate in `NOTES.md → ## EDA Findings` recording: which dates you loaded, the one number or chart that decides the assumption, and whether the candidate's assumption survives or is falsified by the data.

If the assumption is falsified, the candidate is dead — do not patch it; let it be visibly killed. If after Step 3 ZERO candidates survive, go back to Step 2 and propose new ones until at least one survives. (If you cycle Step 2/3 more than twice without a survivor, escalate by writing `## ESCALATION` in NOTES.md and pick the least-falsified candidate, explaining why.)

## Step 4 — Criticize the survivors (Criticizer)

For each surviving candidate, write a paragraph that *attacks* it. The attack must cover at least:
- Could the mechanism interact badly with a constraint (`top_of_book_only`, `participation_cap`, `intraday_flat`, the quantity invariant)?
- Does the predicted P&L direction depend on a sub-assumption that the EDA did NOT test?
- What would the trade_count change look like, and is that change consistent with the claim? (If you predict "fewer skips of profitable trades", you should predict trade_count rises, NOT roughly unchanged — and you should be uneasy when the prediction is "trade_count unchanged" because that means the mechanism is moving WHICH trades it gates, not HOW MANY, which is a much harder claim to defend.)
- Is the parameter setting (threshold, tau, window length) justified by a number you computed in Step 3, or is it armchair? Armchair quantitative parameters are disqualifying.

Write these critiques to `NOTES.md → ## Critique`.

## Step 5 — Select ONE survivor and write the hypothesis

Pick the candidate with the strongest combination of (a) EDA-supported assumption, (b) a parameter justified by a number from the data, and (c) the most-survived critique. Write the hypothesis to `NOTES.md` under `## Hypothesis` in this structure:

- **Mechanism** — what the algorithm does, in one paragraph.
- **Inefficiency exploited** — which specific weakness of `<base_algo>` it addresses.
- **Why it survives costs** — what the algorithm does NOT change (constraints preserved).
- **Quantitative anchors** — every numeric parameter, with the EDA number that justifies it. No armchair numbers.
- **Predicted outcome** — predicted directions for `realized_pnl`, `mean_slippage`, `trade_count`, and `is_weighted_bps` vs `<base_algo>`. Be specific.
- **What would falsify this hypothesis in the backtest** — name ONE result that, if it occurred, would tell you the mechanism is wrong (e.g. "trade_count drops by >5% but P&L is flat or negative" or "skip rate rises but the skipped trades' counterfactual P&L was positive on average").
- **Alternatives considered and rejected** — one sentence each for the two candidates from Step 2 that did not get picked, and why.

## Boundaries (hard)

- Length cap on the NOTES.md sections produced above: keep each section under ~500 words; signal over verbosity.
- Do NOT read test-window dates during EDA. Use `data_window.train` only.
- Do NOT read other experiments or other tracks' algorithm code; only `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- Every quantitative parameter in the final hypothesis must have a Step 3 number behind it. If you cannot find or compute one, the candidate is disqualified.
- The hypothesis is for ONE concrete modification. Do not stack multiple changes ("EWMA AND asymmetric threshold AND magnitude gate") — that breaks attribution.
- Do not improvise additional steps beyond Steps 1–5. If you find an ambiguity, resolve it by picking the more conservative interpretation (more EDA, less commitment) and noting it in NOTES.md.
