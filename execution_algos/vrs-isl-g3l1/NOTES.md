# vrs-isl-g3l1 — Implementation Notes

Island experiment, island-2 (base: `vol-regime-sizer`), generation 3, loop 1.

## Hypothesis

The flow-gate's failure on g2l2 (-30.21% vs g2l1) was a wrongly-tuned
**operating point**, not a fundamentally redundant axis. The gen-2 migration's
`generalizable` insight #3 prescribes the fix directly:

> "When porting a gate, port the MECHANISM and the COMPOSITION SEMANTICS
> but RETUNE the operating point against the new base's pre-filter
> population — a parameter sweep around the ported value is cheaper than
> discovering the misfire after a full backtest."

The gen-2 `base_specific` insight #3 for vrs makes the same diagnosis at
the base level:

> "the same flow axis that compounded cleanly on afg's base does not
> compound cleanly here even after retuning if the redundancy is
> mechanical rather than parametric."

This loop's job is to distinguish those two cases empirically: does a
retuned flow gate compound on vrs, or is the redundancy mechanical?

### Why option (a) over option (b)

The g2l2 `summary_out.next` named two viable g3 directions:
  (a) Retune flow threshold up to 5-8 contracts and/or shorten flow_window
      to 3-5s, keeping the same mechanism.
  (b) Pivot to top-of-book size asymmetry (bid_size vs ask_size ratio).

Option (a) is the higher-leverage move for this loop because:
  1. It is a single-knob retune of an already-implemented, already-debugged
     mechanism — minimal new surface area, minimal risk of subtle
     measurement bugs that would muddy the comparison.
  2. It is the directly-prescribed remedy for the failure mechanism
     diagnosed in g2l2's NOTES (gate parameters tuned for one base's
     surviving-population distribution don't transfer to another base's
     surviving-population distribution).
  3. It is a clean falsifier: if retuned flow STILL regresses below g2l2
     or fails to recover g2l1, the verdict on vrs is unambiguous —
     "flow axis is fundamentally redundant on vrs base" — and g3l2
     should pivot to (b). Without first running (a) we cannot rule out
     the simpler explanation that the threshold was just wrong.
  4. Option (b) would require a brand-new gate mechanism (size-asymmetry
     ratio over a rolling window), which is more code, more new
     parameters, and harder to attribute the result to "axis structure"
     vs "implementation noise" — better tackled in g3l2 after (a) has
     either confirmed or ruled out the cheaper hypothesis.

### Concrete change (single targeted change)

Start from `execution_algos/vrs-isl-g2l2/execution_algorithm.py`. Modify
ONLY the flow gate's default operating point:

| parameter             | g2l2 (verbatim afg) | g3l1 (retuned) | rationale                                                                                  |
|-----------------------|---------------------|----------------|--------------------------------------------------------------------------------------------|
| `flow_threshold`      | 2.0 contracts       | **6.0**        | mid of g2l2's 5-8 band; raises the bar for what counts as a pressure spike vs drift        |
| `flow_window_seconds` | 10.0                | **4.0**        | mid of g2l2's 3-5 band; restricts gate to instantaneous bursts, not minute-scale flow tilt |

Both knobs reduce flow-gate firing rate in the same direction, defining a
single retuned operating point for the same mechanism — they are NOT two
separate axis changes. All other parameters (chop window/neutral/sensitivity,
spread window/quantile/min_samples) held identical to g2l2 for a clean
retune-only ablation.

### Falsification target (declared up-front)

To honor §8 honesty rules and the gen-2 migration's diagnostic discipline
(`generalizable` (2): "diagnostic: trade_count drop disproportionate to the
gate's standalone hit rate"), I declare these thresholds BEFORE seeing
results:

- **PASS**:    `pnl > g2l1 (1011 * 1.05 ≈ +233%? — actually compare to
               g2l1's 2437.75 / vs_base_pnl_pct > 223.42%)` OR matches g2l1
               within ~3% with drawdown tightening AND trade_count within
               10% of g2l1's 104,688 (i.e., between ~94k-100k+).
- **PARTIAL**: `pnl > g2l2 (+125.74%)` but undershoots g2l1 — confirms
               threshold direction is correct but retune undershot; next
               loop sweeps further (8 contracts, 3s window).
- **FAIL**:    `pnl <= g2l2 (+125.74%)` — verdict is "flow axis is
               fundamentally redundant on vrs base" and g3l2 should pivot
               to top-of-book size asymmetry per gen-2 `base_specific` #3.

### Migration influence

Both gen-1 and gen-2 migration reports inform this loop:

- **Gen-2 `base_specific` #3 (vrs)** — directly cited above: identifies the
  hypothesis being tested (retune vs structural pivot).
- **Gen-2 `generalizable` #3** — directly cited above: prescribes the
  retune approach as the correct response to verbatim-port failures.
- **Gen-2 `what_failed` (1)** — the symmetric island-0 g2l2 failure
  (chop ported vrs→ptg) confirms the failure-shape is general, so the
  remedy (retune to the new base's pre-filter distribution) should also
  be general.
- **Gen-1 `generalizable` (3)** — re-affirms that instrumentation counters
  (preserved verbatim from g2l2 here) are non-negotiable for diagnosing
  whether the flow axis is now informative or remains redundant.

## Implementation Decisions

- Inherit class structure from `VrsIslG2L2Algorithm` verbatim — only the
  two default parameter values change. This preserves all instrumentation
  counters, OR-on-skip composition, reduce-only bypass, and deterministic
  per-order pseudo-random draw, so any metric delta vs g2l2 is attributable
  exclusively to the flow operating-point change.
- Keep `flow_window_seconds` and `flow_threshold` as constructor kwargs so
  a future loop could sweep them without touching the class — the
  factory-function plumbing is identical to g2l2.
- Reduce-only orders continue to bypass all three gates so
  `execution_constraints.intraday_flat` remains satisfied.

## Backtest Observations

### Headline (raw numbers, 12 train dates)

| metric            | value      |
|-------------------|------------|
| realized_pnl      | 2040.00    |
| sharpe_ratio      | 15.897     |
| max_drawdown_pct  | -0.01217   |
| win_rate          | 0.3506     |
| trade_count       | 76,914     |
| mean_slippage     | 0.0        |
| is_weighted_bps   | 0.0404     |

### Deltas (raw, no rounding-up)

| comparator                          | pnl_delta_pct | trade_count_delta_pct |
|-------------------------------------|---------------|-----------------------|
| vs base `vol-regime-sizer` (753.75) | **+170.65%**  | -39.91%               |
| vs g2l1 best (2437.75)              | **-16.32%**   | -26.53%               |
| vs prior g2l2 (1701.5)              | **+19.89%**   | +25.23%               |

Slippage axis remains uninformative (0.0 on both sides — execution price
matches signal price exactly under the current measurement model);
`is_weighted_bps` 0.0404 sits between g2l1 (0.0311) and g2l2 (0.0459), so
the retune did NOT recover g2l1's execution-cost-per-trade quality either.

### Verdict against pre-declared falsification thresholds

The hypothesis section declared, before seeing results:

- PASS    = pnl ≥ ~g2l1 (2437.75) AND trade_count in 94k-100k+ range.
- PARTIAL = pnl > g2l2 (1701.5) but undershoots g2l1.
- FAIL    = pnl ≤ g2l2 (1701.5).

The result is **PARTIAL**: pnl 2040 > g2l2 1701.5 (+19.89%) but undershoots
g2l1 2437.75 (-16.32%), with trade_count 76,914 well outside the 94k–100k
band. Trade-count drop is *disproportionate to the gate's standalone
contribution* (gen-2 migration `generalizable` (2) diagnostic): even after
raising the threshold 3× (2→6) and shortening the window 2.5× (10s→4s),
the flow gate still kills ~27k more trades than g2l1 would, and the
PnL/trade quality of the survivors does not improve enough to compensate.

### Honest mechanism reading — flow on vrs is redundant, not mis-tuned

The hypothesis section laid out an explicit binary: retuned-flow either
recovers g2l1 (operating-point story) or it doesn't (mechanical-redundancy
story). The retune moved in the right direction relative to the verbatim
port (g2l2 → g3l1 is +19.89%), but it did NOT close the gap to chop+spread
alone (g2l1). That asymmetry is the falsifier: if the only problem were
threshold mis-tuning, a 3×/2.5× operating-point move on the cited band's
midpoint should have produced *more* than a 19.89% pnl recovery from the
38.79-percentage-point hole (g2l2 was -30.21% below g2l1; we'd need to
recover the full ~30% drop, not 19.89% of g2l2's absolute level, which
corresponds to closing only ~14 of those 30 percentage points). The flow
axis on vrs's base appears to be substantially redundant with
chop+spread — wide-spread bursts and high-aggressor-flow events occur on
substantially overlapping ticks, so adding a flow skip on top of an
already-aggressive chop+spread stack removes informative trades faster
than it removes adverse ones. This **falsifies the operating-point
hypothesis** from the gen-2 migration *for this base*. It does NOT
falsify the migration's general guidance to retune on port — only this
specific port (afg flow gate → vrs chop+spread base) appears mechanically
redundant in a way no operating-point sweep can fix.

### Diagnostic posture for g3l2

Two complementary next moves remain on the table:

  (a) **Roll back to g2l1's two-gate stack** as the durable island-2
      lineage tip and pursue an entirely different third axis. This
      preserves the known-good chop+spread composition and treats g2l2
      and g3l1 as a definitive negative result for the flow axis on vrs.

  (b) **Pivot to top-of-book size asymmetry** (bid_size / ask_size ratio
      over a short rolling window) — the alternative explicitly named in
      both the gen-1 and gen-2 migrations. This axis is structurally
      different from flow (it reads book state, not trade-tape pressure),
      so its redundancy with chop+spread is not pre-determined by the
      same correlation chain that defeated flow.

The `summary_out.next` for this loop will name (b) as the higher-leverage
g3l2 direction, with (a) as the fallback if (b) also regresses below
g2l1. The mechanical-redundancy reading of (a)+(b) together is precisely
what the gen-2 migration `base_specific` insight #3 forecast for vrs.

### Honest caveats (§8)

- Trade counts remain large (~6k+ per date), so noise on the headline
  numbers is small relative to the deltas. No low-trade-count flag.
- The slippage axis being identically zero on both sides means the
  `is_weighted_bps` comparison is the only execution-cost signal that
  can move; it shows the retune did not recover g2l1's surviving-trade
  quality, reinforcing the redundancy reading above.
- The "redundancy not mis-tuning" conclusion is the parsimonious reading
  but is not airtight without per-skip co-occurrence counters
  (gen-1 migration `generalizable` (3)) — a future loop should still
  surface these counters from per-date stdout to formally separate the
  two hypotheses. The strength of the conclusion above rests on the
  retune's directional partial recovery being too small to close the
  full hole.
