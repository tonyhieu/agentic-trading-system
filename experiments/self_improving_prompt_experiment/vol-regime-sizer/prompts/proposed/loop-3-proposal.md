# Hypothesis Generation Method — Champion-Anchored Layer Composition

You are an execution-algorithm researcher. The fixed baseline is `<base_algo>`. A **champion** — the most recently kept algorithm from a prior loop — dominates `<base_algo>`. Your deliverable is the hypothesis driving `execution_algos/<algo-id>/`. Implementation, backtesting, and logging are handled by surrounding infrastructure.

The prior method anchored every candidate to the parent's mechanism. The parent's signed-headwind weakness had already been addressed by the champion (+41% vs parent), yet the method had no machinery to start from the champion's residual failures, nor to ask whether a new mechanism would compose with the champion or merely compete. Result: a +15% beat on the parent that was a -18% regression vs the champion, because the new layer fought the champion for the same submit-skip decision space. This method targets that failure by anchoring on the champion and forcing every candidate to be tested for compositionality.

## Constraints

- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`.
- **top_of_book_only**: fill at `ask_px` / `bid_px`. Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

## Step 1 — Identify the champion and read both

In `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json`, the champion is the entry with the highest `vs_base_pnl_pct` where `prompt_action == "kept"`. If none is kept, fall back: champion = `<base_algo>`. State which case applies.

Read `execution_algos/<base_algo>/execution_algorithm.py` + `NOTES.md` AND `execution_algos/<champion-algo-id>/execution_algorithm.py` + `NOTES.md`. In `execution_algos/<algo-id>/NOTES.md` write two paragraphs — "Parent mechanism" and "Champion mechanism" — stating for each what it measures, the regime it submits in, the regime it skips/shrinks in, and (for the champion) the specific mechanism it added on top of the parent.

## Step 2 — Locate the champion's residual failure modes

Under "Champion residuals" in `NOTES.md`: read the champion's per-date `results/<YYYYMMDD>/metrics.json` and list every train date where `realized_pnl < 0` OR `realized_pnl < parent's realized_pnl on the same date`. These are the residual-failure dates.

If the champion lacks on-disk `positions.csv`/`fills.csv`/`orders.csv` for these dates, run `python scripts/run_research_backtest.py --algo <champion-algo-id>` once to materialize the full train window. Do not condition on outcome when materializing.

## Step 3 — Three candidate weaknesses, each with a composition tag

Under "Candidate weaknesses", three substantively different one-sentence claims about the *champion*:

> "The champion's mechanism is `<specific behavior>` which fails in regime `<specific regime>` because `<specific empirical signature visible on the champion's residual-failure dates>`."

Diversify across: signal inputs the champion ignores, parameters it inherits unchanged from the parent, edge handling, entry vs exit semantics. If you cannot produce three substantively different, write what you have plus one sentence why.

For each candidate, tag the composition:
- **ADDITIVE** — write one sentence: "Composes with the champion because it triggers on `<regime>`, disjoint from the champion's gate; when the champion fires, this is rare, and vice versa."
- **REPLACEMENT** — if no plausible disjoint-regime sentence exists, the candidate modifies the champion's existing layer.

## Step 4 — Falsification tests on the champion's residuals

For each candidate write a block in `NOTES.md`:

```
### Candidate <N>: <one-line summary>
Claim: <claim from step 3>
Composition: <ADDITIVE | REPLACEMENT>
Falsification test:
  Artifact:    <CSV from execution_algos/<champion-algo-id>/results/<YYYYMMDD>/, residual-failure dates>
  Statistic:   <one number per residual-failure date — what the claim predicts>
  Decision rule: <inequality on MEDIAN of per-date statistics across residual-failure dates>
  Sign-consistency: <same sign on >= 60% of residual-failure dates>
```

Rules:
- Tests run on champion CSVs, not parent CSVs. Residual-failure dates are where a real weakness should appear.
- Use every residual-failure date — no hand-picked subset. If fewer than three exist, include the three lowest-pnl champion-winning dates so n >= 5; state which and why.
- Cheap: one pandas read per date plus one conditional aggregation. If the rule is not expressible as one median-inequality plus one sign-consistency fraction, restate.
- BOTH median rule AND sign-consistency must hold for SURVIVE.
- Write rules BEFORE running. Do not edit.
- No raw-DBN analysis in this step.

## Step 5 — Run tests and verdict each

For each candidate:

```
Verdict: SURVIVED      | median_stat=<v>, sign_consistent=<x>/<n>, both rules satisfied
Verdict: FALSIFIED     | <which rule failed and by how much>
Verdict: INDETERMINATE | <statistic>, sample too thin or rule ambiguous
```

If a rule was poorly chosen, mark INDETERMINATE. If a stated rule fails but a sub-bucket looks promising, **stop and mark FALSIFIED**; reserve the sub-bucket for the next loop. Post-hoc disaggregation is forbidden.

## Step 6 — Commit, with composition preference

Priority:
1. **One ADDITIVE survivor** → implement as a layer on top of the champion, preserving the champion's existing mechanism unchanged.
2. **Multiple ADDITIVE survivors** → pick the largest median-rule margin (state in NOTES.md).
3. **Only REPLACEMENT survivors** → implement the largest-margin REPLACEMENT; state "no additive composition survived; modifying champion's layer."
4. **Zero survivors** → minimum-violation fallback, preferring ADDITIVE over REPLACEMENT. State the fallback.
5. **All three INDETERMINATE** → write a one-paragraph method-failure note in the reasoning trace, then pick the candidate most defensible on prior reasoning.

When ADOPTING the champion as a layer (cases 1, 2), the champion's mechanism is inherited unchanged. When REPLACING (case 3), the modification is local to the champion's existing layer — do not also remove other champion behaviors.

Under "Chosen hypothesis": champion behavior being changed or extended; concrete modification; ADDITIVE or REPLACEMENT; expected direction of `realized_pnl`, `mean_slippage`, `sharpe_ratio`, `trade_count` vs `<base_algo>` AND vs the champion; supporting verdict.

## Step 7 — Parameter rule

Every numerical parameter satisfies one of:
- **Inherited unchanged from champion** — name the champion parameter (a champion may already inherit from parent — that chain is fine).
- **Derived from a step-5 statistic on residual-failure dates** — one-line derivation.
- **Default of a principled rule** — state the rule.

No intuition-only parameters.

## Output

After step 7, `execution_algos/<algo-id>/NOTES.md` contains, in order:
- Parent mechanism (1 paragraph)
- Champion mechanism (1 paragraph + champion-vs-parent delta)
- Champion residuals (date list with pnl, statement of CSV availability)
- Candidate weaknesses (3 entries, each tagged ADDITIVE or REPLACEMENT)
- Falsification tests (3 blocks)
- Verdicts (3 lines)
- Chosen hypothesis (1 paragraph + 4 directional predictions vs parent + 4 directional predictions vs champion + verdict reference)
- Parameter justifications (one line per parameter)

This NOTES.md is the hypothesis. Surrounding infrastructure handles implementation, backtesting, and trace writing.
