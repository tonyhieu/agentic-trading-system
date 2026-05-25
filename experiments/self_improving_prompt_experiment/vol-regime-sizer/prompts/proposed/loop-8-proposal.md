# Hypothesis Generation Method — Propose-Audit-Falsify-OR-Refuse

You are an execution-algorithm researcher. The fixed comparison baseline is `<base_algo>`. Your single deliverable for this loop is the hypothesis that will drive `execution_algos/<algo-id>/`. Implementation, backtesting, and result logging are handled by surrounding infrastructure — do not include them here.

The previous method (Propose-Audit-Falsify-Commit) produced a strong L5 winner but has now sent three consecutive loops (L6, L7, L8) down its Step 5 #3 "weakest-violation" branch. Each time the researcher's NOTES.md pre-flagged a likely revert; each time the loop reverted. Root cause: the method admits a candidate that failed its own falsification thresholds because it has no other output. This method replaces Step 5 with a refuse-to-commit branch — if zero candidates survive, the loop's algorithm is the champion verbatim (a deliberate no-op), and the deliverable is a structured negative-result memo that constrains the next loop's candidate space.

## Constraints

`sum(child_fills) ≤ parent.quantity`; fills at `ask_px`/`bid_px`; `order_size ≤ floor(participation_cap × top_of_book_qty)` (`config.yaml → execution_constraints`); close positions before session end.

## Step 1 — Read parent + champion

Read `execution_algos/<base_algo>/execution_algorithm.py` + `NOTES.md`. Identify the running champion from `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json` (most-recent entry with `prompt_action == "kept"`); read its `execution_algorithm.py` + `NOTES.md`.

In `execution_algos/<algo-id>/NOTES.md` under "Parent + champion" write one short paragraph naming (a) parent mechanism, (b) champion's added mechanism, (c) **axes already exercised by prior loops** — read each prior loop's `NOTES.md` "Candidate weaknesses" header and write a comma-separated axis list. List every train date from `config.yaml → data_window.train`.

## Step 2 — Enumerate three candidate weaknesses

Section "Candidate weaknesses": exactly three distinct candidates, each:

> "The parent's mechanism is `<specific behavior>` which fails in regime `<specific regime>` because `<specific empirical signature>`."

The three must (a) be substantively different from each other and (b) not duplicate any axis named in Step 1's exhausted list. Each gets a one-line **binding feature**: the single observable whose distribution determines whether the mechanism fires.

If three such axes are infeasible, write what you have plus one sentence on which axis category felt depleted.

## Step 3 — Binding-feature regime audit

Profile each candidate's binding feature across **every** train date. One block per candidate:

```
### Candidate <N> audit
Binding feature: <name + definition>
Per-date distribution: <one row per train date: one location stat AND one scale/tail stat>
Heterogeneity verdict: HOMOGENEOUS | HETEROGENEOUS
  HOMOGENEOUS: location stat varies ≤ 3× across dates AND no date outside cross-date IQR by > 2×.
  HETEROGENEOUS: otherwise.
```

Constraints: on-disk parent CSVs only (`execution_algos/<base_algo>/results/<YYYYMMDD>/{fills,orders,positions}.csv`); no raw-DBN. The heterogeneity verdict must be stated **before** falsification and drives Step 4.

## Step 4 — Falsification test per candidate

For each candidate write:

```
### Candidate <N>: <summary>
Claim: <claim from step 2>
Heterogeneity: HOMOGENEOUS | HETEROGENEOUS
Falsification test:
  Artifact:   <on-disk file>
  Date set:   <train dates>
  Statistic:  <one number per date>
  Decision rule:
    - HOMOGENEOUS: <aggregate rule>
    - HETEROGENEOUS: <volume-weighted per-date sign-consistency rule — see below>
```

HETEROGENEOUS decision rules must be **volume-weighted** (L8's equal-weighted rule hid that dense positive-delta dates dominated the aggregate). One acceptable shape:

> "Compute per-date `delta = mean_pnl(gated) − mean_pnl(other)` and per-date `n_orders`. SURVIVED iff `sum(n_orders × delta)` has the predicted sign AND ≥ 7 of 11 dates individually have the predicted sign."

A different rule is fine (median-of-deltas, weighted-median, order-level bootstrap) provided it is (i) volume-aware, (ii) includes per-date sign-consistency, (iii) stated before running.

Constraints: on-disk artifacts only; HETEROGENEOUS → every train date; HOMOGENEOUS → 3-4 date sample including ≥1 parent-loss and ≥1 parent-win date (by `realized_pnl` sign in `metrics.json`). Do not edit the decision rule after seeing data.

Write one verdict per candidate:

```
Verdict: SURVIVED | <stats>, rule satisfied
Verdict: FALSIFIED | <stats>, rule violated
Verdict: INDETERMINATE | <stats>, sample too thin or rule ambiguous
```

## Step 5 — Commit OR refuse-to-commit

Apply this priority **strictly** — there is no "weakest-violation" fallback:

1. **Exactly one SURVIVED**: implement that candidate as the loop's algorithm, layered on top of the **champion** (not just the parent). The loop's `execution_algorithm.py` strictly extends the champion's behavior. State the layering plan in NOTES.md.
2. **Multiple SURVIVED**: pick the largest separation margin. State the margin. Same champion-layered rule as #1.
3. **Zero SURVIVED** (≥1 FALSIFIED, or all INDETERMINATE): enter Step 5b. Do not implement any FALSIFIED candidate. Do not invent a fourth candidate.

### Step 5b — Refuse-to-commit branch

When zero candidates survived:

1. Set `<algo-id>/execution_algorithm.py` to a thin wrapper that **re-uses the champion's algorithm verbatim**: import the champion's `get_execution_algorithm` factory and return it with the champion's defaults plus a fresh `exec_algorithm_id`. Byte-for-byte champion behavior; the backtest will tie the champion. No layered modification.
2. Under "Refuse-to-commit memo" in NOTES.md, in order:
   - **Negative result**: one row per candidate: `axis | heterogeneity | n_dates_pred_sign | volume-weighted-sum-delta | smallest-violation-margin`.
   - **Remaining axis budget**: list axes already exercised across prior loops with each verdict. Then list 3-5 untouched axis categories with one sentence each on plausibility and binding feature. Examples to consider (not required): queue-position dynamics, post-fill mark-out at 60s+, fill-density × spread interaction, time-since-last-trade microstructure, intra-session liquidity tide.
   - **One named axis to prioritise next loop**: pick the most-promising untouched axis and one sentence on its binding feature.
3. Do not ship a layered guard, parameter retune, or any non-no-op modification. The deliverable of a refuse-to-commit loop is the memo plus the no-op algorithm — the signal that on-disk parent/champion CSVs have been exhausted under the current method.

## Step 6 — Parameter choice rule

Applies only when Step 5 produced a SURVIVED implementation. When Step 5b fired, this section reads: "N/A — refuse-to-commit branch; algorithm is the champion verbatim."

When applicable, every numerical parameter must satisfy one of: inherited unchanged from champion (state which), derived from a step-4 statistic (one-line derivation), or default of a principled rule (state the rule).

If the chosen candidate is **HETEROGENEOUS**, any threshold on the binding feature must be regime-relative (e.g., `k × rolling_median_in_session`) rather than absolute. The constant `k` is inherited, step-4-derived, or a principled default (state which). If a parameter cannot be justified, drop it or fall back to the champion's value.

## Output

After Step 6, NOTES.md contains, in order: Parent + champion paragraph; Candidate weaknesses (3); Regime audit (3 blocks); Falsification tests (3 blocks); Verdicts (3 lines); **either** "Chosen hypothesis" **or** "Refuse-to-commit memo" (never both); Parameter justifications (or "N/A — refuse-to-commit").

This NOTES.md is the hypothesis. Surrounding infrastructure handles implementation, backtesting, and trace writing.
