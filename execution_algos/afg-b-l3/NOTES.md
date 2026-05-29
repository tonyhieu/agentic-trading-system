# afg-b-l3 — aggressor-flow-gate with DISJUNCTIVE absolute OR (ratio AND busyness) gate

Brief-summary arm, loop 3. Prior context = ONLY the `summary_out`
(changed / outcome / hypothesis / brief_summary / next) blocks from
loop-1.json (afg-b-l1) and loop-2.json (afg-b-l2), plus the headline
metrics for each. Per the brief-summary mode boundary I did NOT read any
prior NOTES.md prose or any full_reasoning text -- only the brief
summaries and the L1 + L2 source files (mechanical chassis-shape
inspection only, to know what parameters and class structure were in
play).

## Hypothesis

L1 + L2 brief_summary establish:

  1. L1 swapped base's absolute |net_flow| >= 2.0 gate for a pure ratio
     gate (|r| >= 0.35). Result vs base: -53% pnl, +13.5k extra admits.
     The ratio gate is RELAXED relative to the absolute gate in busy
     windows (where 2-contract imbalance against 100-contract abs_vol
     gives r=0.02 << 0.35).
  2. L2 conjoined the two: skip iff (|net_flow| >= 2.0) AND (|r| >= 0.35).
     Hypothesis was that intersection of skip conditions yields strict
     subset of admits. Reality: trade_count rose to 102,005 vs base's
     87,760 (+14.2k). The conjunction's joint SKIP set is the
     intersection of each operand's skip set, so the ADMITTED set is
     the UNION of admits -- worse selectivity than base, not better.
  3. On this oracle the relationship between admits and pnl is roughly
     monotone: each +1k extra admits costs ~$47 of pnl. So the path to
     beat base is to ADD skips, not subtract them.

L2's "next" prescribes the obvious correction: DISJUNCTIVE join. Skip
iff EITHER operand triggers. The disjunction makes the joint skip set
the UNION of each operand's skip set, hence a strict SUPERSET of either.
By construction, admitted-trades <= base.

The ratio leg gets gated by a minimum absolute-volume floor
(`min_busy_abs_vol = 5.0`) to avoid the L1 failure mode where a single
2-contract trade in an otherwise empty window trivially yields r=1.0 --
those are zero-information warm-up windows where the ratio is undefined
in any meaningful sense. With the floor, the ratio leg only adds skips
in *moderately busy* windows where >=5 contracts have already hit; this
is exactly the regime where L1's data suggested the ratio carries
information beyond the absolute threshold.

Expected direction:
  * vs base: trade_count strictly <= 87,760; pnl >= base ($970.00). The
    L1 per-1k arithmetic ($47/1k) implies that for any K extra skips
    beyond base's admit set, pnl improves by ~$47*K/1000, provided
    those extra skips are at most weakly informative.
  * vs L2: trade_count significantly < L2's 102,005 (probably also
    < base's 87,760 because the disjunction adds skips on top); pnl
    > L2's $464.25.

If pnl improves materially over base, the brief-summary arm finally
beats its base on this lineage and this is the new high-water mark.
If it merely matches base within noise, the ratio leg carries little
incremental information beyond the absolute threshold and future loops
should target a structurally different axis (per-side asymmetric
thresholds; longer/shorter windows; regime-conditional thresholds via
e.g. session-time buckets).

## Implementation Decisions

  * ONE targeted structural change vs L2: flip the joiner from AND to OR
    in `_flow_is_adverse()`. Both operand conditions (absolute and
    ratio) carry over from L2 unchanged in their internal form.
  * New parameter `min_busy_abs_vol = 5.0` added: gates the ratio leg
    by `abs_vol >= 5.0` so the ratio leg cannot fire on near-empty
    warm-up windows. Default chosen as ~3 average MES contracts in 10s,
    enough to make the ratio statistically meaningful but low enough
    not to dominate the floor.
  * `min_abs_baseline = 2.0` (ratio denominator floor) retained
    unchanged -- in the disjunctive structure the denominator floor
    matters only when `abs_vol < min_abs_baseline`, which is gated out
    by `min_busy_abs_vol = 5.0 > 2.0` for the ratio leg; functionally
    inert here but kept for API symmetry with L1 / L2.
  * Window kept at 10s -- isolate the gate-structure change; do not
    retune the window in the same loop.
  * Direction-side logic: BUY adverse when (net <= -flow_threshold) OR
    (busy AND r <= -ratio_threshold); SELL adverse when
    (net >=  flow_threshold) OR (busy AND r >=  ratio_threshold).
    Per-side signed test mirrors base + L1 + L2 exactly.
  * Anti-cascade semantics (`_position_flat = True` after any skip,
    forcing the next OPEN through unconditionally) preserved exactly
    from base + L1 + L2. Reduce-only orders always submit
    (intraday_flat).
  * Quantity invariant strictly preserved -- orders are skipped or
    submitted unmodified.

## Backtest Observations

Aggregated 11-date train window (20260308..20260320, 20260319 OOM-dropped
on both sides per the 11-date aggregate convention):

  * realized_pnl: $970.00  (= base aggressor-flow-gate $970.00 exactly)
  * sharpe_ratio: 4.5809
  * max_drawdown_pct: -3.32%
  * win_rate: 35.44%
  * trade_count: 87,760  (= base 87,760 exactly)
  * mean_slippage: 0.0  (slippage 0.0/0.0 vs simple; no regression)
  * vs simple baseline ($43.25 / 132,228 trades on the same 11 dates):
    pnl +2142.77%, trade_count -33.6%, sharpe 4.58 vs 0.60 -- PASS gate
    (+5.0% min_pnl_improvement) by a wide margin.
  * vs base aggressor-flow-gate ($970.00 / 87,760 trades on the same
    11 dates): pnl_diff = 0.0% EXACTLY, trade_count diff = 0 trades
    EXACTLY.

**Collapse-to-base diagnosis.** The L3 disjunction
`skip iff (|net_flow| >= 2.0) OR (|r| >= 0.35 AND abs_vol >= 5.0)` is
mathematically a strict superset of base's skip set by construction.
Observed: it admits the SAME set as base. The only way both conditions
can yield identical decisions on every single one of 87,760+ orders is
that the ratio leg never adds any NEW skip beyond what the absolute leg
already catches. That requires, for every order where the absolute leg
does NOT fire (|net_flow| < 2.0), the ratio leg also does not fire --
i.e., (|r| < 0.35) OR (abs_vol < 5.0). With abs_vol >= 5.0 and
|net_flow| < 2.0, we'd need |net_flow|/abs_vol < 0.35; this becomes
TRUE for |net_flow| in {0, 1, 1.5} whenever abs_vol > ~5.7. So on this
dataset, whenever the window is busy enough to qualify (abs_vol >= 5)
and the absolute leg is silent (|net_flow| < 2), the ratio is already
< 0.35. The disjunction collapses to base because the parameter choices
(flow=2, ratio=0.35, busy_floor=5) make the ratio leg structurally
dominated by the absolute leg on this oracle.

Hypothesis verdict: CONTRADICTED. Expected pnl strictly > base; got
pnl = base exactly. The "ratio carries additional information beyond
the absolute threshold" hypothesis cannot be tested when the parameter
choice makes the ratio leg structurally inert.

**Status: PASS** vs simple baseline (+2142.77%, well above the +5.0%
gate; slippage 0.0/0.0 -- no regression). vs base_algo: identical
performance (no improvement, no regression). Trade count flag: 87,760
trades over 11 dates = ~7,978/day -- well above any sparseness flag.

**Next direction** (highest leverage, recorded for L4 in the
brief-summary stream): tighten the base's absolute threshold itself.
L1+L2+L3 collectively triangulate that on this oracle the ratio
reformulation cannot beat base, and that the path forward is to ADD
skips that the base does not currently make. The cheapest test of the
"base under-skips" thesis is raising `flow_threshold` from 2.0 to 3.0
contracts. If +X.X% pnl follows, the base's threshold is the binding
selectivity floor and there is room to push further. If pnl regresses,
the base's threshold is already near-optimal in the absolute-threshold
family and the next loop should structurally pivot (window length,
per-side asymmetric thresholds, or session-time regime gates).
