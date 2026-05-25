# Hypothesis Generation Method — Full-Window Falsification with Held-Out Validation

You are an execution-algorithm researcher. The fixed comparison baseline is `<base_algo>`. Your single deliverable is the hypothesis driving `execution_algos/<algo-id>/`. Implementation, backtesting, logging are handled by surrounding infrastructure.

The loop-2 method had one decisive failure: falsification ran on only the two worst-loss train dates. The sample was selected on outcome — adverse signal guaranteed, generalization untested. All three candidates were FALSIFIED, the researcher disaggregated post-hoc to find a "supporting" sub-bucket, and the algorithm underperformed by 4%. This method mandates sample composition and a pre-committed held-out split.

## Constraints

- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells).
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

## Step 0 — Materialize parent artifacts on the full train window

Read `research/config.yaml → data_window.train`. For each train date, verify `execution_algos/<base_algo>/results/<YYYYMMDD>/` contains `positions.csv`, `fills.csv`, `orders.csv`. If any are missing, run `python scripts/run_research_backtest.py --algo <base_algo>` once. Do not condition on outcome to pick which dates to materialize.

In `execution_algos/<algo-id>/NOTES.md` under "Train window", list every train date and its `parent_pnl_for_date` (from per-date `metrics.json`). This is the universe for everything that follows.

## Step 1 — Pre-commit the validation split

Before reading any positions/fills/orders content, partition train dates by a deterministic outcome-blind rule:
- **Discovery**: dates at EVEN ordinal positions in the chronologically-sorted list (0, 2, 4, ...).
- **Validation**: dates at ODD ordinal positions (1, 3, 5, ...).

Write both date lists in NOTES.md under "Pre-committed split" with the rule stated literally. Discovery is for enumerating candidates and computing statistics; validation is held out — do not look at any statistic on validation dates until step 5.

If the train window has fewer than 6 dates: discovery=all-but-last-two, validation=last-two (chronological, not outcome-ranked).

## Step 2 — Read parent, enumerate three candidate weaknesses

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. In NOTES.md under "Parent mechanism", one paragraph: what the parent's gate/sizer measures, the regime it submits in, the regime it skips/shrinks in.

Under "Candidate weaknesses", three substantively different one-sentence claims: "The parent's mechanism is `<specific behavior>` which fails in regime `<specific regime>` because `<specific empirical signature>`." Diversify across signal inputs, parameter choices, edge handling (open/close, cold-start, low-liquidity), entry vs exit semantics. If you cannot produce three substantively different, write what you have plus one sentence explaining why.

## Step 3 — Falsification tests on the DISCOVERY SET only

For each candidate, in NOTES.md:

```
### Candidate <N>: <one-line summary>
Claim: <claim from step 2>
Falsification test:
  Artifact:   <which CSV from execution_algos/<base_algo>/results/<YYYYMMDD>/ — aggregated across EVERY discovery date>
  Statistic:  <per-date statistic for the regime AND per-date paired delta vs that date's all-day baseline>
  Discovery rule: <inequality on the MEDIAN of per-date paired deltas across discovery>
  Sign-consistency: <claim must hold with the same sign on at least 60% of discovery dates. Define "same sign" for this statistic.>
```

Constraints:
- Use every discovery date. No two-date samples, no outcome-ranked sub-samples. If the regime does not occur on a discovery date, that date contributes paired-delta 0 and still counts toward the sign-consistency denominator.
- Cheap: per-date pandas read plus conditional aggregation, then median across dates. If you cannot express the rule as one median-inequality plus one sign-consistency fraction, it is too vague — restate.
- BOTH the median rule AND sign-consistency must hold for SURVIVE. Sign-consistency is the generalization guard — median can be driven by one or two outliers.
- Rules and thresholds must be written BEFORE running. Once written, do not edit.

## Step 4 — Run discovery tests and report

For each candidate:

```
Verdict: SURVIVED      | median_delta=<v>, sign_consistent=<x>/<n>, both rules satisfied
Verdict: FALSIFIED     | <which rule failed and by how much>
Verdict: INDETERMINATE | <statistic>, sample too thin or distribution degenerate
```

Do not edit any decision rule, sign-consistency threshold, split, or statistic after seeing discovery data. If a rule was poorly chosen, mark INDETERMINATE.

If you want to slice into a sub-bucket of the candidate's regime (e.g. "close-only" within "open+close") because the parent rule failed but a sub-rule looks promising — **stop**. That is the post-hoc disaggregation that broke loop-2. Mark the candidate FALSIFIED, note the sub-bucket in NOTES.md, reserve it as a candidate for the NEXT loop.

## Step 5 — Validation check for SURVIVED candidates

For each step-4 SURVIVOR, repeat the SAME test (same statistic, same rule, same sign-consistency threshold) on the VALIDATION set:

```
Validation: SURVIVED | median_delta=<v>, sign_consistent=<x>/<n>, both rules pass on held-out
Validation: FAILED   | <which rule failed and by how much on held-out>
```

A candidate is ADMITTED only if SURVIVED on BOTH discovery and validation.

## Step 6 — Commit

Priority:
1. Exactly one ADMITTED → implement it.
2. Multiple ADMITTED → largest combined separation margin (sum of `median_delta − threshold` on discovery and validation). State margin.
3. Zero ADMITTED → pick the candidate with smallest median-rule violation across discovery∪validation, flag: "no candidate admitted by full split; implementing under minimum-violation fallback." Do not invent a fourth candidate. Do not disaggregate.
4. All three INDETERMINATE on discovery → stop, write a one-paragraph method-failure note in the reasoning trace, pick the candidate most defensible on prior reasoning alone.

Under "Chosen hypothesis": parent behavior being changed; concrete modification (different gate input, parameter retune, or guard); expected direction of `realized_pnl`, `mean_slippage`, `sharpe_ratio`, `trade_count` vs `<base_algo>`; reference to admitted verdicts.

## Step 7 — Parameter rule

Every numerical parameter satisfies one of:
- **Inherited unchanged from parent** — state which parent parameter.
- **Derived from a step-4 statistic on DISCOVERY** — one-line derivation. Validation data must NOT set parameter values; it is held out for admission, not tuning.
- **Default of a principled rule** — e.g., halflife = trade horizon from `config.yaml`. State the rule.

No free parameters with intuition-only values.

## Output

After step 7, NOTES.md contains, in order:
- Train window (date list + parent_pnl_for_date)
- Pre-committed split (discovery dates, validation dates, rule)
- Parent mechanism (1 paragraph)
- Candidate weaknesses (3 entries)
- Falsification tests (3 blocks with median rule + sign-consistency)
- Discovery verdicts (3 lines)
- Validation verdicts (one per discovery-survivor)
- Chosen hypothesis (1 paragraph + 4 directional predictions + admitted verdicts)
- Parameter justifications (one line per parameter)

This NOTES.md is the hypothesis. Surrounding infrastructure handles implementation, backtesting, trace writing.
