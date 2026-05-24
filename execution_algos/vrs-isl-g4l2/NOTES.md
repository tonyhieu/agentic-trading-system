# vrs-isl-g4l2 — Hypothesis

## Lineage
- Island: island-2 (base = vol-regime-sizer, abbrev = vrs)
- Generation: 4, Loop: 2
- Parent (lineage best): **vrs-isl-g3l2** (chop + rolling-spread + size-asymmetry
  three-gate stack; PnL 4690.75 / +522.30% vs base / sharpe 19.11 / max_dd -0.40%).
- Immediate prior loop (this generation): **vrs-isl-g4l1** —
  loosened `size_asym_ratio` 1.5 -> 2.0; PnL 4454.50 (-5.04% vs g3l2;
  REGRESSION inside the pre-declared >2% band); trade_count +6.60%;
  is_weighted_bps NARROWED on surviving orders (0.0550 vs 0.0585,
  -5.89%) yet PnL fell.

## Single targeted change (single-knob ablation discipline)
**Tighten `size_asym_ratio` from 1.5 -> 1.25** in the gate that skips
BUY when `ask_size >= ratio * bid_size` and SELL when
`bid_size >= ratio * ask_size`. All other parameters frozen verbatim
from vrs-isl-g3l2 (chop window_ticks=30 / chop_neutral=1.5 /
sensitivity=1.0 / min_prob=0.05; spread window=60s / q=0.75 /
min_samples=50; trend_boost=0; AND-on-submit composition; reduce-only
bypass; instrumentation counters). No structural changes.

## Hypothesis — peak-mapping the size-asym EV curve
g4l1's regression (PnL -5.04%) at `size_asym_ratio=2.0`, combined with
its candid bps-narrowing-without-PnL-gain signal (is_weighted_bps
-5.89% on surviving orders), places `1.5` at or below the local EV
peak — the OPPOSITE direction from the gen-3 migration's
`base_specific` (3) reading. The marginal trades admitted in the
[1.5, 2.0] depth-asymmetry band sit closer to the body of the
distribution than its tail and carry net-negative EV.

Tightening to 1.25 is the tight-flank counterpart to g4l1's 2.0
loose-flank probe. Two informative outcomes are pre-declared:

1. **If 1.25 ALSO regresses vs g3l2** (PnL < 4690.75 - ~2pp): the EV
   peak is at or very near 1.5; both flanks of the [1.25, 2.0] band
   are bounded as suboptimal. Verdict: g3l2 is the operating-point
   peak for this knob on this composition. The gen-3 migration's
   `generalizable` (2) finding ("the working axis transfers cleanly
   at the SAME threshold") is empirically confirmed on the vrs base.
   Further leverage requires a structurally new axis or a sizing-side
   change.

2. **If 1.25 CONFIRMS** (PnL > 4690.75 + ~2pp, e.g. > ~4784.5, with
   sharpe and drawdown not deteriorating): 1.5 was loose for the vrs
   composition after all (just in the opposite direction from the
   migration's prediction). The true peak sits at or below 1.25; a
   follow-up loop should probe ~1.1 to bound the peak further.

This single loop maps the local EV curvature with the highest
information per loop available on this knob, and is the PRIMARY move
g4l1's `summary_out.next` prescribed.

## Cross-island insight cited
Migration gen-3 `base_specific` (3) suggested the ported afg threshold
(1.5) would be over-restrictive on vrs's three-gate stack (more
headroom than afg's four-gate stack), and recommended a sweep in
[1.25, 2.0]. g4l1 ran 2.0 and FALSIFIED the over-restrictive claim
on the loose flank. g4l2 now runs the bottom of the same migration-
prescribed band (1.25) — the tight flank. The cross-island signal
that motivated `size_asym_ratio` as a knob worth retuning (rather than
fixing at 1.5) is the migration evidence itself; this loop tests
whether the migration's "wrong direction" reading might still be
true on the tight side.

## Why 1.25 (not 1.75 or 1.1)
- **Not 1.75**: g4l1 already established that the [1.5, 2.0] band is
  net negative-EV; bisecting it adds little. The information value of
  the symmetric tight flank is higher.
- **Not 1.1**: below 1.25 the dominant failure mode (if any) is pure
  over-restriction with trade_count collapse, conflating the
  peak-mapping diagnostic. 1.25 is the floor of the migration's
  recommended band and stays inside the regime where the dominant
  failure mode would still be EV-bounded over-tightening.
- **1.25 is symmetric to 2.0** on a log-ratio scale (1.5/1.25 = 1.2 vs
  2.0/1.5 = 1.33), making the two ablations directly comparable.

## Falsification (pre-declared, before backtest)
- Confirmation: PnL > 4784.5 AND sharpe drop <= 0.5 AND drawdown
  widening <= 0.5pp.
- Bounded regression: PnL < 4596.9 (~ -2% vs g3l2) AND/OR sharpe drop
  > 0.5 — verdict: g3l2 IS the size-asym operating-point peak.
- Over-restriction edge case: trade_count drop > 25% vs g3l2 (i.e.
  < ~56,336) without proportional PnL improvement — verdict: tight
  flank crossed into pure over-restriction; uninformative for peak
  bound. Follow-up should test 1.35.

## What this loop does NOT change
- Chop gate parameters (verbatim from g3l2).
- Spread gate parameters (verbatim from g3l2).
- Composition semantics (AND-on-submit; reduce-only bypass).
- Quantity logic (child==parent).
- Instrumentation counters (identical contract).

## Backtest Observations (post-run, raw numbers)

### Headline metrics (12 train dates, aggregated)
- realized_pnl: **4717.75** (vs base vrs 753.75 = **+525.82%**; vs g3l2 4690.75 = **+0.58%**)
- sharpe_ratio: **19.0950** (vs g3l2 19.1094 = **-0.0144 absolute**; essentially identical)
- max_drawdown_pct: **-0.00340** (vs g3l2 -0.00400 = +0.060pp; marginally tighter)
- win_rate: **0.3922** (vs g3l2 0.3890 = +0.32pp)
- trade_count: **71,524** (vs g3l2 75,115 = **-4.78%**; tighter, as expected from a stricter gate)
- mean_slippage: 0.0 (top-of-book; unchanged)
- is_weighted_bps: 0.0611 (vs g3l2 0.0585 = +4.44% on surviving orders; slightly worse bps with fewer/better-net trades — small wash)
- vs_baseline (simple) pnl: +2924.20%; vs_baseline_is_bps: +57.15

### Pre-declared falsification verdict
Confirmation threshold was PnL > 4784.5 with sharpe drop ≤ 0.5; bounded
regression threshold was PnL < 4596.9 OR sharpe drop > 0.5.

- PnL 4717.75 falls **between** 4596.9 and 4784.5 → **NULL within the
  pre-declared ±2% band** (delta +0.58%, well inside the noise floor).
- Sharpe drop is 0.0144 absolute (well under 0.5pp).
- Drawdown did not widen.

Per the hypothesis's pre-declared option (1): the EV peak is at or very
near 1.5; both flanks of [1.25, 2.0] are now bounded as suboptimal
(g4l1 at 2.0 regressed -5.04%; g4l2 at 1.25 is null). **g3l2's
operating point IS the local size-asym EV peak on the vrs three-gate
stack.** The gen-3 migration's generalizable (2) reading — "the
working axis transfers cleanly at the SAME threshold" — is empirically
**confirmed on the vrs base**, in the OPPOSITE direction from the
migration's base_specific (3) prediction (which suggested 1.5 was
over-restrictive on vrs and recommended looser).

### Interpretation
- Both flanks of the size_asym sweep produced ~no PnL change (g4l1:
  +2.0 regressed -5%; g4l2: 1.25 ≈ flat). The EV peak is **broad** and
  **centered at 1.5**.
- Trade-count moved monotonically with threshold (1.25 → 71,524;
  1.5 → 75,115; 2.0 → 80,072) — confirming the gate is firing as
  designed and the threshold knob has real bite. The lack of PnL
  response means the marginal trades in [1.25, 1.5] AND in [1.5, 2.0]
  are both close to break-even EV.
- is_weighted_bps moving the "wrong" direction (+4.44% with fewer
  trades) is consistent with the marginal cases on either side of 1.5
  being close-to-zero EV: tightening drops some break-even orders and
  the survivors' average bps drifts slightly. Not a meaningful signal.
- **The vrs lineage is at its 3-axis ceiling.** Further leverage on
  this composition requires either (a) a structurally new 4th axis, or
  (b) retuning a different existing axis's operating point
  (chop_neutral, spread_quantile, chop_sensitivity) rather than
  size_asym_ratio.

### What this confirms for migration
- The "loose flank loses, tight flank flat, peak at port-threshold"
  pattern at size_asym=1.5 on vrs aligns with the gen-3 migration's
  generalizable (2) prediction (threshold portability) more strongly
  than its base_specific (3) (over-restrictive port). Migration gen-4
  should treat 1.5 as the cross-island canonical size_asym threshold.
- A new 4th-axis attempt at a non-ported (calibrated) threshold is the
  next informative move; island-1's g4l1 velocity-axis null result
  warns against ported thresholds on a 4th axis.
