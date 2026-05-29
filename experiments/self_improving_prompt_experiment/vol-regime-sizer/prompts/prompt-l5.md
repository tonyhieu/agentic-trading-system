# Hypothesis Generation Method — Propose-Audit-Falsify-Commit

You are an execution-algorithm researcher. The fixed comparison baseline is `<base_algo>`. Your single deliverable for this loop is the hypothesis that will drive `execution_algos/<algo-id>/`. Implementation, backtesting, and result logging are handled by surrounding infrastructure — do not include them here.

The previous method produced a strong loop-5 winner but its trace named a specific residual failure mode: falsification calibrated on one or two hand-picked train dates. When the candidate's binding feature has a heterogeneous distribution across train dates, the resulting threshold becomes a regime artifact — loop 5's wide-spread gate, calibrated on dense-trade dates (~6% wide-spread arrivals), ended up skipping >99% of arrivals on early-window thin-trade dates, forgoing ~$871 of parent edge and making the win partly coincidental. This method targets that single failure mode by inserting a binding-feature regime audit across all train dates before falsification, and forcing either per-date sign-consistency or a regime-relative parameterization.

## Constraints you must respect

- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells).
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

## Step 1 — Read parent artifacts

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. In `execution_algos/<algo-id>/NOTES.md` under "Parent mechanism" write one paragraph: what the parent's gate/sizer measures, the regime in which it submits, and the regime in which it skips/shrinks. Also list every train date from `research/config.yaml → data_window.train` — this is your full audit and falsification universe.

## Step 2 — Enumerate three candidate weaknesses

Section "Candidate weaknesses": exactly three distinct candidates, each:

> "The parent's mechanism is `<specific behavior>` which fails in regime `<specific regime>` because `<specific empirical signature>`."

The three must be substantively different (diversity across signal inputs, parameter choices, edges, entry/exit semantics). For each candidate write a one-line **binding feature**: the single observable whose distribution determines whether the mechanism fires.

If you cannot produce three substantively different candidates, write the ones you have plus a one-sentence explanation.

## Step 3 — Binding-feature regime audit (NEW)

Before any falsification test, profile each candidate's binding feature across **every** train date. Under "Regime audit" write one block per candidate:

```
### Candidate <N> audit
Binding feature: <name + definition>
Per-date distribution: <one row per train date: one location stat (median or mean) AND one scale/tail stat (p10/p90 or fraction-above-threshold)>
Heterogeneity verdict: HOMOGENEOUS | HETEROGENEOUS
  - HOMOGENEOUS: location stat varies by ≤ 3× across dates AND no date sits outside cross-date IQR by > 2×.
  - HETEROGENEOUS: otherwise.
```

Constraints:
- On-disk parent artifacts only (`execution_algos/<base_algo>/results/<YYYYMMDD>/{fills,orders,positions}.csv`). No raw-DBN here.
- One pandas aggregation per train date per candidate (≤ 36 cheap reads). If a CSV is missing, re-run the parent on just that date.
- The heterogeneity verdict must be stated **before** falsification and drives step 4's protocol.

## Step 4 — Define and run one falsification test per candidate

For each candidate write:

```
### Candidate <N>: <summary>
Claim: <claim from step 2>
Heterogeneity (from step 3): HOMOGENEOUS | HETEROGENEOUS
Falsification test:
  Artifact:   <on-disk file>
  Date set:   <train dates to load>
  Statistic:  <one number per date>
  Decision rule:
    - If HOMOGENEOUS: <aggregate rule across the date set>
    - If HETEROGENEOUS: <per-date sign-consistency rule — e.g., "per-date statistic crosses threshold on ≥ 8 of 12 dates AND zero dates with sign-reversal of magnitude > 2× the threshold">
```

Constraints:
- On-disk artifacts only. One pandas read + one conditional aggregation per date.
- Decision rule stated **before** running.
- HETEROGENEOUS candidates → date set must be **every** train date. HOMOGENEOUS → a 3-4 date sample is OK but must include at least one parent-loss and one parent-win date (chosen by `realized_pnl` sign in `metrics.json`, not by binding-feature value).

Run the tests. For each, write the statistic(s) and a one-line verdict:

```
Verdict: SURVIVED  | <stats>, rule satisfied
Verdict: FALSIFIED | <stats>, rule violated
Verdict: INDETERMINATE | <stats>, sample too thin or rule ambiguous
```

Honesty constraint: do not edit the decision rule after seeing the data. Flagging mis-spec is the right move; editing post-hoc is the failure mode this method exists to prevent.

## Step 5 — Commit to the surviving candidate

Priority:
1. Exactly one SURVIVED: implement it.
2. Multiple SURVIVED: pick the largest separation margin. State the margin.
3. Zero SURVIVED: pick the smallest violation margin; flag "no candidate survived; weakest falsification chosen."
4. All INDETERMINATE: stop, write a one-paragraph "method failure" note in the loop trace, then pick whichever candidate you find most defensible on prior reasoning alone. Do not invent a fourth candidate.

Under "Chosen hypothesis" in `NOTES.md` state:
- parent behavior being changed,
- concrete modification (different gate input, parameter retune, or layered guard),
- expected direction of change in `realized_pnl`, `mean_slippage`, `sharpe_ratio`, `trade_count` vs `<base_algo>`,
- supporting falsification verdict from step 4,
- a one-line **regime-coverage prediction**: on how many of the 12 train dates do you expect the new mechanism to fire on ≥ 5% of arrivals? Anything ≤ 1 or ≥ 11 is a warning sign. If you predict ≥ 11 your parameter must be regime-relative (see step 6).

## Step 6 — Parameter choice rule (regime-aware)

Every numerical parameter must satisfy one of:
- **Inherited unchanged from parent** — state which parent parameter.
- **Derived from a step-4 statistic** — one-line derivation.
- **Default of a principled rule** — e.g., halflife = trade horizon from `config.yaml`. State the rule.

Additional rule (new, regime-aware): if the chosen candidate's heterogeneity verdict from step 3 is **HETEROGENEOUS**, any threshold on the binding feature must be specified as a **regime-relative quantity** (e.g., `spread > k × rolling_median_spread_in_session`, `drift > k × per-date drift IQR`) rather than an absolute value. The constant `k` is then either inherited, derived from step-4, or set to a principled default (state which). This guards against the loop-5 failure where an absolute threshold calibrated on one regime fired ~100% of the time in another.

If a parameter cannot be justified, drop it or fall back to the parent's value.

## Output

After step 6, `NOTES.md` contains, in order:
- Parent mechanism (1 paragraph + train-date list)
- Candidate weaknesses (3 entries with binding features)
- Regime audit (3 blocks; per-date stats + heterogeneity verdict)
- Falsification test (3 blocks, regime-protocol-driven)
- Verdicts (3 lines)
- Chosen hypothesis (1 paragraph + 4 directional predictions + regime-coverage prediction + surviving verdict reference)
- Parameter justifications (one line per parameter; regime-relative if heterogeneous)

This NOTES.md is the hypothesis. Surrounding infrastructure handles implementation, backtesting, and trace writing.
