# Champion-Anchored Propose-Audit-Falsify-Commit

Execution-algorithm researcher. Baseline: `<base_algo>`. Deliverable: the hypothesis driving `execution_algos/<algo-id>/`. Implementation, backtesting, logging are infrastructure — do not include them.

Loop 7's failure mode: the L5 method's audit + falsification both ran on the *parent*'s CSVs. L7's streak-gate was unanimous on the parent but fired on **zero** of L5's orders across all 11 train dates — per-date pnl tied L5 exactly. The champion already pruned the regime where the binding feature lives. This method anchors audit and falsification on the **current champion's** order stream and adds a pre-commit feasibility gate.

## Constraints
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells).
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`.
- **intraday_flat**: close positions before session end.

## Step 1 — Champion + parent

The **champion** is the most recent `sip-vrs-l<X>` whose `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-<X>.json` has `prompt_action == "kept"`. Read its `execution_algorithm.py` and `NOTES.md`, and every prior loop's `NOTES.md`.

Under "Champion + parent" in `execution_algos/<algo-id>/NOTES.md`:
- One paragraph naming the champion's gate(s) and the submit/skip regimes.
- **Residual table**: per train date, the champion's `realized_pnl` from `execution_algos/sip-vrs-l<X>/results/<YYYYMMDD>/metrics.json` (sign + magnitude). Mark the 2-3 worst dates or the residual signature — new mechanism must move pnl there.
- "Prior-loop axes (do not duplicate)" list.
- Train dates from `research/config.yaml → data_window.train`.

## Step 2 — Three candidates targeting champion residuals

Section "Candidate weaknesses": exactly three, each:

> "The champion's surviving mechanism is `<specific behavior>` which leaves residual loss in regime `<specific regime>` because `<specific empirical signature>`."

Each carries a one-line **binding feature**. All three substantively different and orthogonal to every prior-loop axis. **Each must reference at least one champion-residual date or signature from step 1** — candidates whose regime does not overlap any champion residual are illegal.

Binding features should be derivable from on-disk CSVs (champion's or parent's). Raw-DBN permitted only if no CSV-derivable feature plausibly captures the residual.

## Step 3 — Champion-anchored binding-feature audit

For each candidate, profile the binding feature on the **champion's** `execution_algos/sip-vrs-l<X>/results/<YYYYMMDD>/{fills,orders,positions}.csv` across every train date. Under "Regime audit":

```
### Candidate <N> audit
Binding feature: <name + definition>
Per-date distribution (champion stream): <row per date: location stat AND scale/tail stat>
Champion-coverage: <row per date: fraction of champion's orders where the binding feature crosses the candidate threshold>
Heterogeneity verdict: HOMOGENEOUS | HETEROGENEOUS
  - HOMOGENEOUS: location stat varies ≤ 3× across dates AND no date outside cross-date IQR by > 2×.
  - HETEROGENEOUS: otherwise.
```

Constraints:
- **Champion CSVs, not parent's.** If a champion CSV is missing, re-run the champion on that date first.
- One pandas aggregation per date per candidate.
- The Champion-coverage row is mandatory — step 5 reads it.

## Step 4 — Falsification on the champion's stream

For each candidate:

```
### Candidate <N>: <summary>
Claim: <claim from step 2>
Heterogeneity: HOMOGENEOUS | HETEROGENEOUS
Falsification test:
  Artifact:   champion positions.csv (typically)
  Date set:   <train dates>
  Statistic:  per-date mean realized_pnl of CHAMPION positions where binding feature crosses threshold, minus mean realized_pnl where it does not
  Decision rule:
    - If HOMOGENEOUS: aggregate δ across the date set satisfies <pre-stated inequality, e.g. δ ≤ -$0.05>
    - If HETEROGENEOUS: per-date sign-consistency — δ crosses threshold on ≥ 8 of N dates AND zero sign-reversals of magnitude > 2× threshold
```

The statistic is conditional on the **champion's** positions, not the parent's. HETEROGENEOUS → every train date. HOMOGENEOUS → 3-4 dates including one champion-loss and one champion-win. Decision rule stated **before** running.

Run. Per candidate one verdict line:

```
Verdict: SURVIVED  | <stats>, rule satisfied
Verdict: FALSIFIED | <stats>, rule violated
Verdict: INDETERMINATE | <stats>, sample thin or rule ambiguous
```

Do not edit the decision rule after seeing data.

## Step 5 — Champion-feasibility gate (NEW)

Every candidate (SURVIVED, FALSIFIED, or INDETERMINATE) must pass:

```
### Feasibility (Candidate <N>)
Champion-trigger fraction: <cross-date mean of step 3 Champion-coverage rows>
Champion-gated-bucket mean δ: <cross-date mean of step 4 per-date conditional δ>
Feasibility verdict:
  - PASS if champion-trigger fraction ≥ 1% AND |gated-bucket mean δ| ≥ $0.02 in the predicted direction.
  - FAIL otherwise (structural redundancy — mechanism cannot move pnl on the champion's stream).
```

Both numbers come from step 3 and step 4 — no new compute. The 1% and $0.02 thresholds are absolute, stated here, not editable post-hoc.

## Step 6 — Commit

Priority:
1. **Exactly one SURVIVED + PASS**: implement it.
2. **Multiple SURVIVED + PASS**: pick largest step-4 separation margin. State margin.
3. **Zero SURVIVED, ≥ 1 FALSIFIED + PASS**: pick smallest violation margin among PASS. Flag "weakest falsification among feasible chosen."
4. **Zero PASS** (all candidates FAIL feasibility, regardless of falsification): method-failure paragraph. The loop's hypothesis is **revert to the champion** — `sip-vrs-l<N>` is an exact copy of the champion's `execution_algorithm.py`, NOTES.md states "all candidates structurally redundant with champion; no mechanism available." This is honest and prevents another zero-effect loop.
5. **All INDETERMINATE**: method-failure paragraph; pick the most defensible by prior reasoning among PASS candidates only. No fourth candidate.

Under "Chosen hypothesis":
- parent behavior being changed,
- concrete modification,
- expected direction of `realized_pnl`, `mean_slippage`, `sharpe_ratio`, `trade_count` vs `<base_algo>` AND vs champion,
- supporting verdict + feasibility numbers,
- **champion-coverage prediction**: on how many of N train dates will the new mechanism fire on ≥ 1% of champion arrivals?

## Step 7 — Parameter choice rule (regime-aware)

Every numerical parameter must satisfy one of:
- **Inherited unchanged from parent or champion** — state which.
- **Derived from a step-3 or step-4 statistic computed on the champion's stream** — one-line derivation.
- **Default of a principled rule** — state the rule.

If the chosen candidate's heterogeneity verdict is HETEROGENEOUS, any threshold on the binding feature must be **regime-relative** (e.g., `k × rolling_median_in_session_on_champion_stream`) rather than absolute. `k` is inherited, derived from step-4, or a principled default.

If a parameter cannot be justified, drop it or fall back to the champion's value.

## Output

`NOTES.md` contains, in order:
- Champion + parent (paragraph + residual table + prior-loop axes + train dates)
- Candidate weaknesses (3 entries, each tied to a champion residual)
- Regime audit (3 blocks; includes Champion-coverage row)
- Falsification test (3 blocks; statistic conditional on champion positions)
- Verdicts (3 lines)
- Feasibility (3 blocks; PASS/FAIL each)
- Chosen hypothesis (paragraph + 4 directional predictions vs parent AND champion + champion-coverage prediction + verdict + feasibility ref)
- Parameter justifications (one line each)

NOTES.md is the hypothesis. Infrastructure handles implementation, backtesting, and trace writing.
