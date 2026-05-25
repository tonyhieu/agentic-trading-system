# Tiered Propose-Audit-Falsify-Commit (Tier-A CSV → Tier-B raw-DBN escalation)

Execution-algorithm researcher. Baseline: `<base_algo>`. Deliverable: the hypothesis driving `execution_algos/<algo-id>/`. Implementation, backtesting, logging are handled by infrastructure — do not include them.

Loop 6's trace named the failure mode: after 5 loops the cheap CSV-derivable axes (direction, time-of-day, regime persistence, trendiness, spread) were exhausted. The "no raw-DBN" rule in step 3 forced three weak candidates (side, range-position, round-number), all FALSIFIED. The "weakest-violation" branch admitted a candidate with no mechanism and lost on every gate metric (0/5). This method adds a Tier-B raw-DBN escalation that opens only when Tier-A produces no SURVIVOR, and refuses a weakest-violation pick unless Tier-B has been attempted.

## Constraints

- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells).
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`.
- **intraday_flat**: close positions before session end.

## Step 1 — Read parent + prior-loop axes

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. Read every prior loop's `NOTES.md` (`execution_algos/sip-vrs-l<X>/NOTES.md`, X < current) and list each axis already targeted. In `execution_algos/<algo-id>/NOTES.md` under "Parent mechanism" write one paragraph + a "Prior-loop axes (do not duplicate)" list + train dates from `research/config.yaml → data_window.train`.

## Step 2 — Three Tier-A candidates

Tier-A candidates derive from parent CSVs (`execution_algos/<base_algo>/results/<YYYYMMDD>/{fills,orders,positions}.csv`). Section "Tier-A candidate weaknesses": exactly three, each:

> "The parent's mechanism is `<specific behavior>` which fails in regime `<specific regime>` because `<specific empirical signature>`."

Each carries a one-line **binding feature**. All three substantively different and orthogonal to every prior-loop axis from step 1.

## Step 3 — Binding-feature regime audit (Tier-A)

For each Tier-A candidate, profile the binding feature across **every** train date. Under "Regime audit (Tier-A)" write per candidate:

```
### Candidate <N> audit
Binding feature: <name + definition>
Per-date distribution: <one row per date: one location stat AND one scale/tail stat>
Heterogeneity verdict: HOMOGENEOUS | HETEROGENEOUS
  - HOMOGENEOUS: location varies ≤ 3× across dates AND no date outside cross-date IQR by > 2×.
  - HETEROGENEOUS: otherwise.
```

Parent CSVs only. One pandas aggregation per date per candidate. If a CSV is missing, re-run the parent on that date.

## Step 4 — Falsification per Tier-A candidate

For each candidate:

```
### Candidate <N>: <summary>
Claim: <claim from step 2>
Heterogeneity: HOMOGENEOUS | HETEROGENEOUS
Falsification test:
  Artifact:   <on-disk parent CSV>
  Date set:   <train dates>
  Statistic:  <one number per date>
  Decision rule:
    - If HOMOGENEOUS: <aggregate rule across the date set>
    - If HETEROGENEOUS: <per-date sign-consistency, e.g. ≥ 8 of N dates AND no sign-reversal > 2× threshold>
```

CSVs only. Decision rule stated **before** running. HETEROGENEOUS → every train date. HOMOGENEOUS → 3-4 dates including at least one parent-loss and one parent-win.

Run. Per candidate, one verdict line:

```
Verdict: SURVIVED | <stats>, rule satisfied
Verdict: FALSIFIED | <stats>, rule violated
Verdict: INDETERMINATE | <stats>, sample thin or rule ambiguous
```

Do not edit the decision rule after seeing data.

## Step 5 — Tier-B escalation (NEW) when zero Tier-A survive

- **At least one SURVIVED**: skip to step 6.
- **Zero SURVIVED**: do **not** auto-fall to "weakest violation." Run Tier-B.

Tier-B authorises **one** raw-DBN feature, computed from one cached partition per train date, then falsified across all dates. One feature, one pass, no iterative refinement.

### Step 5.1 — Pick one raw-microstructure feature

Section "Tier-B candidate": one weakness whose binding feature requires raw DBN. Pick one:

- Top-of-book size imbalance: `(bid_size - ask_size) / (bid_size + ask_size)`, signed by side.
- Signed aggressor flow over last K trades: `sum(sign(trade_price - prev_mid) × trade_size)`.
- Quote update intensity: `MBP1Msg` count in last `M` seconds before arrival.
- Time-since-last-trade.
- Quote half-life: time since current best bid (or ask) was first posted.

Each prior-loop axis off-limits. Write one paragraph: chosen feature + one literature anchor (Cont 2014 on imbalance; Hasbrouck 2007 on signed flow; Easley/Lopez de Prado/O'Hara on VPIN; or another — name + one-line justification).

### Step 5.2 — Raw-DBN compute

For every train date, use the `analysis` skill's `load_dbn_partition` pattern (`.claude/skills/analysis/SKILL.md`): load the partition, filter to the trading symbol, compute the feature at every parent-arrival timestamp, join to parent `positions.csv` so each open arrival has both the feature and realized parent pnl.

- One pandas pass per date — no iteration.
- Join key: parent `client_order_id` (or `ts_init` if id unavailable).
- If a partition is missing or OOMs (precedent: 20260319), skip and report. Tier-B then runs on N-of-12 dates, N stated up front.

### Step 5.3 — Tier-B audit + falsification

Under "Regime audit (Tier-B)" write one block (step-3 format). Under "Falsification test (Tier-B)" write one block (step-4 format). Decision rule stated **before** running. Run and record verdict.

## Step 6 — Commit

Read all verdicts (3 Tier-A + 0-or-1 Tier-B). Priority:

1. **Exactly one SURVIVED across tiers**: implement it.
2. **Multiple SURVIVED**: pick largest separation margin. State margin and tier.
3. **Zero SURVIVED AND Tier-B was run**: pick smallest violation margin among the four. Flag "no candidate survived; weakest falsification chosen across both tiers."
4. **Zero SURVIVED AND Tier-B was NOT run** (Tier-A all FALSIFIED but step 5 skipped): method violation. Stop. Method-failure paragraph; pick by prior reasoning, not by "weakest violation."
5. **All INDETERMINATE**: method-failure paragraph, pick by prior reasoning. No fifth candidate.

Under "Chosen hypothesis" in `NOTES.md`:
- parent behavior being changed,
- concrete modification,
- expected direction of `realized_pnl`, `mean_slippage`, `sharpe_ratio`, `trade_count` vs `<base_algo>`,
- supporting verdict,
- **regime-coverage prediction**: on how many train dates do you expect the mechanism to fire on ≥ 5% of arrivals? ≤ 1 or ≥ 11 is a warning. If ≥ 11, the parameter must be regime-relative (step 7).

## Step 7 — Parameter choice rule (regime-aware)

Every numerical parameter must satisfy one of:
- **Inherited unchanged from parent** — state which.
- **Derived from a step-4 or step-5 statistic** — one-line derivation.
- **Default of a principled rule** — state the rule.

If the chosen candidate's heterogeneity verdict is **HETEROGENEOUS**, any threshold on the binding feature must be **regime-relative** (e.g., `k × rolling_median_in_session`) rather than absolute. The constant `k` is inherited, derived from falsification, or a principled default.

If a parameter cannot be justified, drop it or fall back to the parent's value.

## Output

`NOTES.md` contains, in order:
- Parent mechanism (paragraph + prior-loop axes + train-date list)
- Tier-A candidate weaknesses (3 entries)
- Regime audit Tier-A (3 blocks)
- Falsification test Tier-A (3 blocks)
- Verdicts Tier-A (3 lines)
- Tier-B candidate / audit / falsification / verdict (only if Tier-A all FALSIFIED)
- Chosen hypothesis (paragraph + 4 directional predictions + regime-coverage prediction + verdict reference)
- Parameter justifications (one line each; regime-relative if heterogeneous)

NOTES.md is the hypothesis. Infrastructure handles implementation, backtesting, and trace writing.
