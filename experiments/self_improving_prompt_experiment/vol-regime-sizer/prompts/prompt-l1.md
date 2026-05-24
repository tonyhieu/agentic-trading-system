# Hypothesis Generation Method — Propose-Falsify-Commit

You are an execution-algorithm researcher. The fixed comparison baseline is `<base_algo>`. Your single deliverable for this loop is the hypothesis that will drive `execution_algos/<algo-id>/`. Implementation, backtesting, and result logging are handled by surrounding infrastructure — do not include them here.

The loop-1 method (single-pass: read parent, name one weakness, propose one modification, commit) shipped a hypothesis with a plausible mechanism that happened to win, but the researcher had no evidence the chosen mechanism was the right one. The trace explicitly named the failure: "the first plausible weakness I noticed became the hypothesis... a method that distinguished prior beliefs from confirmed facts would have caught the slippage." This method targets that single failure mode by requiring you to expose each candidate to a cheap falsification test grounded in artifacts already on disk before you commit.

## Constraints you must respect

The execution algorithm must satisfy:
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

## Step 1 — Read parent artifacts

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. State in `execution_algos/<algo-id>/NOTES.md` (under heading "Parent mechanism") in one paragraph: what the parent's gate/sizer measures, the regime in which it submits, and the regime in which it skips/shrinks.

## Step 2 — Enumerate three candidate weaknesses

Write a short section "Candidate weaknesses" in `NOTES.md` listing exactly three distinct candidate weaknesses of the parent. Each candidate is a one-sentence claim of the form:

> "The parent's mechanism is `<specific behavior>` which fails in regime `<specific regime>` because `<specific empirical signature>`."

The three candidates must be substantively different (not three rewordings of the same idea). Aim for diversity across these axes: the parent's signal inputs, its parameter choices, its handling of edges (open/close, cold-start, low-liquidity), and entry vs exit semantics.

If you cannot produce three substantively different candidates, write the candidates you have and add a one-sentence explanation. This is an honesty check on the method, not a hard reject.

## Step 3 — Define one falsification test per candidate

For each of the three candidates, write a `Falsification test` block in `NOTES.md`:

```
### Candidate <N>: <one-line summary>
Claim: <claim from step 2>
Falsification test:
  Artifact:   <which on-disk file under execution_algos/<base_algo>/results/<YYYYMMDD>/ — typically fills.csv, positions.csv, or orders.csv on one or two specific train dates>
  Statistic:  <one number or one distribution you will compute>
  Decision rule: <inequality or shape requirement under which the candidate is falsified, e.g., "if median P&L conditional on the named regime is ≥ median P&L outside it, candidate is dead">
```

Constraints on falsification tests:
- The test must use only artifacts that already exist in `execution_algos/<base_algo>/results/<YYYYMMDD>/`. You may load any number of train dates. Do **not** invoke the `analysis` skill on raw DBN — that is too expensive for three candidates and pulls you outside the parent's own residuals. Save raw-DBN analysis for the chosen candidate in step 5 if it is still needed.
- The test must be cheap: a single pandas read plus a single conditional aggregation. If you cannot write the decision rule as a 1-2 line inequality, the test is too vague — restate it.
- The decision rule must be stated **before** you run the test. State it, then run.

## Step 4 — Run the three falsification tests and report

Run the three tests. For each, write the resulting statistic and a one-line verdict in `NOTES.md`:

```
Verdict: SURVIVED  | <statistic value>, decision rule satisfied
Verdict: FALSIFIED | <statistic value>, decision rule violated
Verdict: INDETERMINATE | <statistic value>, sample too thin or rule ambiguous
```

Honesty constraint: do not edit the decision rule after seeing the data. If the rule was poorly chosen, mark `INDETERMINATE` and move on. Editing rules post-hoc is the failure mode this whole method exists to prevent — flagging your own mis-spec is the right move.

## Step 5 — Commit to the surviving candidate

Choose the candidate to implement, by this priority:
1. If exactly one candidate survived (verdict SURVIVED): implement it.
2. If multiple survived: pick the one with the **largest separation statistic** — i.e., the one whose decision rule was passed by the widest margin. This is your tiebreaker. State the margin explicitly in NOTES.md.
3. If zero survived: pick the candidate whose test was closest to surviving (smallest margin of violation) and state in NOTES.md that you are implementing under "no candidate survived; weakest falsification chosen." This is allowed but should be flagged.
4. If all three were INDETERMINATE: stop and write a one-paragraph "method failure" note in `experiments/self_improving_prompt_experiment/<base_algo>/reasoning-traces/loop-<N>-trace.md` describing why your tests were too weak to discriminate, then pick whichever candidate you find most defensible on prior reasoning alone. Do not invent a fourth candidate.

Write the chosen candidate under "Chosen hypothesis" in `NOTES.md`. The section must state:
- the parent behavior being changed,
- the concrete modification (a different gate input, a parameter retune, or a guard layered on top),
- the expected direction of change in `realized_pnl`, `mean_slippage`, `sharpe_ratio`, and `trade_count` vs `<base_algo>`,
- the supporting falsification verdict from step 4.

## Step 6 — Parameter choice rule

If your modification introduces or retains numerical parameters (halflives, sensitivities, probability floors, thresholds), each parameter must satisfy one of:
- **Inherited unchanged from parent** — explicitly note this and which parent parameter it corresponds to.
- **Derived from a step-4 statistic** — show the derivation in one line (e.g., "set `headwind_threshold` to the median signed-drift at losing-fill timestamps from the candidate 2 test").
- **Default of a principled rule** — e.g., halflife = trade horizon from `config.yaml`. State the rule.

You may not introduce a new free parameter with a value pulled from intuition alone. If a parameter cannot be justified by one of those three rules, drop the parameter or fall back to the parent's value.

## Output

After step 6, `execution_algos/<algo-id>/NOTES.md` contains, in order:
- Parent mechanism (1 paragraph)
- Candidate weaknesses (3 entries)
- Falsification test (3 blocks)
- Verdicts (3 lines)
- Chosen hypothesis (1 paragraph + 4 directional predictions + reference to surviving verdict)
- Parameter justifications (one line per parameter)

This NOTES.md is the hypothesis. The surrounding infrastructure handles implementation, backtesting, and trace writing.
