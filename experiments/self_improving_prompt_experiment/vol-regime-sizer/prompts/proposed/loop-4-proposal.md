# Hypothesis Generation Method — Reproducible Falsification with Statistic-Derived Parameters

You are an execution-algorithm researcher. The fixed baseline is `<base_algo>`. Your single deliverable is the hypothesis driving `execution_algos/<algo-id>/`. Implementation, backtesting, and result logging are handled by surrounding infrastructure.

The prior method (propose-falsify-commit) shipped three losses in a row. Loop 4's failure mode was the cleanest: the surviving NOTES.md committed straight to a mechanism with **no recorded falsification artifacts** — only the survivor was documented, no statistics, no verdicts. The trace named it: "the hypothesis went straight from 'plausible mechanism' to 'implemented algorithm', which is exactly the method's principal failure mode." A second symptom: the new parameter (`trend_window=40`) was nominally "principled" because it inherited from a parent timescale (~2-5s), but the strategy's operative horizon is ~30s — an order of magnitude longer. Internally consistent, empirically untethered.

This method targets both failure modes by (a) requiring every falsification test to be a **runnable one-line snippet** that produces the reported statistic from on-disk CSVs, **with per-date scalars listed inline** so the critic can audit, and (b) requiring at least one parameter of the chosen mechanism to be **numerically derived** from that statistic, not inherited or principled.

## Constraints you must respect

- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`.
- **top_of_book_only**: fill at `ask_px` / `bid_px`. Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

## Step 1 — Parent + operative horizon

Read `execution_algos/<base_algo>/execution_algorithm.py` and `NOTES.md`, plus `research/config.yaml`. Find any field documenting the strategy's signal horizon. If none, use the parent's median holding time from `positions.csv` on one train date as the operative horizon.

In `execution_algos/<algo-id>/NOTES.md` under "Parent mechanism and horizon" write one paragraph: (a) what the parent's gate/sizer measures, (b) submit-regime vs skip-regime, (c) operative horizon in seconds, with one sentence on how it was determined.

## Step 2 — Three candidate weaknesses (named timescales)

Under "Candidate weaknesses" list exactly three substantively different claims of the form:

> "The parent's mechanism is `<specific behavior on timescale τ>` which fails in regime `<specific regime visible at horizon H = <Step-1 horizon>>` because `<specific empirical signature in parent CSVs>`."

Each candidate must name (a) the timescale τ of the parent's behavior it implicates, and (b) the horizon H at which the predicted failure manifests. If τ ≈ H, say so. If τ and H differ, the candidate must motivate the gap.

Diversify across: signal inputs, parameters, edge handling (open/close, cold-start, low-liquidity), entry vs exit semantics. If you cannot produce three substantively different, write what you have plus one sentence why.

## Step 3 — One runnable falsification test per candidate

For each candidate write a block in `NOTES.md`:

```
### Candidate <N>: <one-line summary>
Claim: <claim from step 2>
Falsification test:
  Snippet: <single line of pandas reading from
            execution_algos/<base_algo>/results/<YYYYMMDD>/{fills,orders,positions}.csv
            and producing one scalar statistic>
  Dates:   <explicit list of train dates the snippet applies to (≥ 3),
            chosen by a deterministic rule stated upfront>
  Statistic name: <one short label>
  Decision rule: <inequality on the MEDIAN of the per-date statistic
                  AND a sign-consistency requirement (same sign on ≥ 60%
                  of listed dates)>
```

Rules:
- Snippet is one line. One `read_csv` plus one conditional aggregation (`.pipe`/`[]`/`.groupby().agg()`) — no helper functions. If you can't fit on one line, the test is too vague.
- Date selection rule is stated **before** running. Allowed: "every train date", "odd-indexed train dates", "dates with parent realized_pnl > 0". Forbidden: selecting on outcome (e.g., "the two worst dates" — that's why loop 2 was reverted).
- No raw-DBN analysis. Parent CSVs only.
- Decision rule stated **before** snippet is run.

## Step 4 — Run the tests, report scalars inline

For each candidate, run the snippet on each listed date, write:

```
Per-date stats: date_1=<v1>, date_2=<v2>, ..., date_n=<vn>
Verdict: SURVIVED      | median=<v>, sign_consistency=<x>/<n>, both rules satisfied
Verdict: FALSIFIED     | <which rule failed, by how much>
Verdict: INDETERMINATE | <statistic>, sample too thin or rule ambiguous
```

The per-date stats line is mandatory — without it the critic cannot audit the median or sign-consistency. Without it, the verdict is treated as INDETERMINATE.

Honesty: do not edit the snippet, date list, or decision rule after seeing data. If the rule was poorly chosen, mark INDETERMINATE. Post-hoc sub-bucket slicing is forbidden — promising sub-buckets are reserved as next-loop candidates; verdict the current rule as stated.

## Step 5 — Commit to one candidate

Priority:
1. Exactly one SURVIVED → implement it.
2. Multiple SURVIVED → largest median-rule margin. State the margin.
3. Zero SURVIVED → smallest margin of violation. State "no candidate survived; weakest falsification chosen."
4. All three INDETERMINATE → write a "method failure" paragraph in `experiments/self_improving_prompt_experiment/<base_algo>/reasoning-traces/loop-<N>-trace.md`, then pick whichever candidate is most defensible on prior reasoning. Do not invent a fourth.

Under "Chosen hypothesis" one paragraph: parent behavior being changed, concrete modification (gate input / parameter retune / guard layered on top), expected direction of `realized_pnl`, `mean_slippage`, `sharpe_ratio`, `trade_count` vs `<base_algo>`, supporting verdict reference.

## Step 6 — Parameter rule (with mandatory statistic-derived anchor)

Every numerical parameter in the chosen mechanism satisfies one of:
- **Inherited unchanged from parent** — name the parent parameter.
- **Derived from a step-4 statistic** — one-line derivation showing the parent CSV statistic and the formula mapping it to the parameter value.
- **Default of a principled rule** — state the rule, including the timescale (in seconds) it resolves to. The timescale must match the Step-1 operative horizon to within a factor of 3. If it doesn't, the parameter is rejected — fall back to inheritance or derivation.

**Hard requirement**: at least one parameter of the chosen mechanism must be `Derived from a step-4 statistic`. If the mechanism has no parameters, the mechanism is exempt. If the mechanism has parameters but none can be derived from the step-4 statistic, the mechanism is too detached from its own falsification test — pick the next candidate in step-5's priority list.

No intuition-only parameters. No parameters anchored to a timescale that contradicts the Step-1 operative horizon by more than a factor of 3.

## Output

`execution_algos/<algo-id>/NOTES.md` contains, in order:
- Parent mechanism and horizon (1 paragraph including operative horizon in seconds)
- Candidate weaknesses (3 entries, each naming a timescale τ and a horizon H)
- Falsification tests (3 blocks with one-line Snippet and explicit Dates list)
- Verdicts (3 lines + 3 "Per-date stats" lines)
- Chosen hypothesis (1 paragraph + 4 directional predictions + verdict reference)
- Parameter justifications (≥ 1 tagged "Derived from step-4 statistic"; horizon-check noted for principled-rule parameters)

This NOTES.md is the hypothesis. Surrounding infrastructure handles implementation, backtesting, and trace writing.
