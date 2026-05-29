# Hypothesis Generation Method — base_algo=aggressor-flow-gate (loop 4+)

You are an execution-algorithm researcher. Produce ONE hypothesis for `<algo-id>` that you believe will beat `<base_algo>` on the train window's realized P&L without meaningfully worse slippage. Implementation and backtesting are handled by surrounding infrastructure.

Loop 3 (seed prompt-l0, single-pass) picked the canonical NOTES.md weakness ("base over-skips during transient flow bursts") and proposed a 3s confirmation gate. Mechanism was clean and constraint-safe. Backtest regressed -43.13% with trade_count +7.4% — the recovered orders were systematically adverse. The trace identifies the exact failure mode: the proposed mechanism (base over-skips stale-but-ended flow) has a MIRROR (base correctly skips active flow merely in a short pause) that is equally consistent with the base's observed IS regression, predicts the OPPOSITE outcome of the modification, and was never distinguished from the primary before committing. Loop 2's EDA-heavy method (reverted) over-measured generic assumptions; loop 3's no-EDA method (reverted now) under-measured. **Fix: every hypothesis must be paired with its mirror — the strongest alternative reading of the same base weakness that predicts the OPPOSITE backtest outcome — and the EDA must discriminate between the two, not merely confirm one.**

This method is **mirror-hypothesis discrimination**. The novelty is not "more EDA" — it is that EDA must answer ONE question whose two possible answers point to opposite mechanisms.

## Step 1 — Read context

Read in order:
1. `execution_algos/<base_algo>/execution_algorithm.py`
2. `execution_algos/<base_algo>/NOTES.md`
3. `execution_algos/<base_algo>/results/backtest-results.json`
4. `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json` — every prior loop's algo_id, mechanism family, action, delta vs base. Note which families have failed and how.
5. `research/config.yaml` for `data_window.train` and `execution_constraints`.

You may not read other entries in `execution_algos/` or other experiments.

Write a 4–6 line summary in your reasoning trace: the base mechanism, the single inefficiency it claims, which families have already failed (cite database deltas), and which directions remain open.

## Step 2 — Propose ONE primary hypothesis

Pick ONE concrete modification: a different gate input, a different decision rule shape, a guard layered on top, or a parameter retune. State:
- The SPECIFIC weakness it addresses.
- The SPECIFIC code-level change.
- Predicted direction and rough magnitude of realized_pnl.
- Predicted direction of trade_count. State whether the change moves WHICH orders are gated or HOW MANY. "trade_count unchanged but P&L rises" requires extra justification — it is the hardest claim to defend.

Do NOT pick a mechanism family the program_database shows has already been tried with the same intent. If the same family with a different intent, name the differentiating intent.

Write to `execution_algos/<algo-id>/NOTES.md → ## Primary Hypothesis`.

## Step 3 — Write the MIRROR HYPOTHESIS (mandatory)

For the primary from Step 2, write the strongest competing reading of the SAME base weakness that:
- Cites the SAME NOTES.md text or SAME observed metric the primary cites.
- Proposes the OPPOSITE direction for the modification (stricter where primary loosens; longer where primary shortens; SELL-favoring where primary BUY-favors; etc.).
- Predicts the OPPOSITE backtest outcome (positive vs negative P&L delta) if the mirror is the true explanation.

The mirror is NOT a strawman. Steelman it: assume an equally-careful researcher would have arrived at the mirror given the same NOTES.md. Write its mechanism, predicted direction, and the one claim it makes about the data.

Examples:
- Primary: "base over-skips stale flow → add 3s confirmation → more good fills." Mirror: "base correctly skips active flow whose pauses are mid-burst → loosening exposes more bad fills, not fewer."
- Primary: "SELL adverse selection > BUY → disable SELL gating." Mirror: "BUY adverse selection > SELL → tighten BUY gating, leave SELL alone."
- Primary: "10s window too short → lengthen to 30s." Mirror: "10s too long, dilutes recent pressure → shorten to 3s."

If you cannot construct a non-strawman mirror, your primary is too vague — sharpen it until a mirror exists.

Write to `NOTES.md → ## Mirror Hypothesis`.

## Step 4 — Identify the discriminating observable

Find ONE observable in the train data whose value points to the primary OR the mirror, not both. It must:
- Have a numerical answer.
- Have a sign or magnitude threshold committed IN ADVANCE: "if X then primary; if Y then mirror; if between, inconclusive."
- Be cheap to compute (1 date of DBN ticks, one rolling pass).

Examples of well-formed discriminating observables (do not reuse — adapt):
- "Stale vs mid-pause": at moments where net_flow_10s exceeds threshold AND net_flow_3s is neutral, the 5s-ahead net_flow_10s — stays elevated (mirror) vs decays (primary). Commit to a magnitude threshold.
- "BUY vs SELL adverse selection": 30s-ahead drift conditional on aggressor side, sampled at ~1Hz synthetic arrivals. Commit to sign and magnitude.
- "Window length": autocorrelation of signed flow at lags 3s, 10s, 30s. Commit to a relative ordering.

Write to `NOTES.md → ## Discriminating Observable`: the question, the threshold rule, and what each outcome means.

## Step 5 — Measure the discriminating observable

Use the `analysis` skill mechanics. Load 1–2 dates from `data_window.train` (NOT test). Run the measurement. Produce the single number.

Write to `NOTES.md → ## Measurement`: dates used, the number, and the verdict (primary, mirror, or inconclusive).

If the measurement supports the **mirror**, you must either:
(a) Swap to the mirror as your new primary and re-run Steps 3–5 from scratch (the new primary needs its own new mirror), OR
(b) Drop this hypothesis entirely and return to Step 2 with a different mechanism family.

Do NOT ship the primary if its mirror is empirically supported. **This is the load-bearing rule.**

If the measurement is **inconclusive**, you may ship the primary, but the hypothesis section must explicitly say "discriminating measurement was inconclusive" and your falsifier in Step 6 must be tighter than usual (e.g. "if trade_count moves >2% in EITHER direction and P&L is flat or negative, mechanism is wrong").

## Step 6 — Write the final hypothesis

Write to `NOTES.md → ## Hypothesis (final)`:
- **Mechanism** — one paragraph.
- **Inefficiency exploited** — which base weakness.
- **Why it survives costs** — what does NOT change (constraints preserved).
- **Quantitative anchors** — every numeric parameter. Inherited from base → say so. New → justify with the Step 5 measurement OR mark "uncalibrated; armchair" and flag as a known risk.
- **Predicted outcome** — directions for realized_pnl, mean_slippage, trade_count. State whether WHICH-orders shift or HOW-MANY shift.
- **Discriminating-observable verdict** — one sentence: primary supported, mirror supported, or inconclusive.
- **Falsifier in the backtest** — ONE result that would invalidate the mechanism, distinct from the mirror prediction.

## Boundaries (hard)

- Keep each NOTES.md section under ~400 words. Signal over verbosity.
- Do NOT read test-window dates during EDA — train only.
- Do NOT read other experiments or other tracks' algo code; only `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- ONE concrete modification per hypothesis. No stacking.
- Steps 3, 4, 5 are non-optional. The mirror must be a steelman.
- If Step 5 supports the mirror, you may NOT ship the primary.
- On ambiguity, pick the more conservative interpretation (tighter falsifier, more flagging) and note it.
