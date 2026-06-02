# Algorithm Notes: sig-isl-g1l3 (island-sig, generation 1, loop 3)

## Island lineage

- Island: island-sig (theme: "Microstructure signals")
- Parent: `sig-isl-g1l2` (opposite-tape Lipton imbalance + Kolm OFI SKIP gate; PASS at +863.30% vs simple, sharpe 5.83)
- Seed papers: BookImbalance (Lipton), PredictionFromOrderFlowImbalance (Kolm)
- Cross-island input: migrations `generation-1.json` through `generation-4.json`

## Hypothesis

**Single change vs G1L2**: STACK a rolling-spread-p75 OPEN-side SKIP gate
ON TOP of G1L2's opposite-tape (Lipton imbalance + Kolm OFI) gate, with
OR-skip composition semantics — an OPEN order is skipped if EITHER the
opposite-tape AND-gate fires OR the spread-quantile gate fires. The
opposite-tape gate itself is preserved bit-for-bit (predicate direction,
thresholds, window, AND semantics) so the only attributable behavioral
change is the *addition* of one orthogonal SKIP axis.

**Mechanism — why a composed SKIP stack should improve PnL**

The cross-island migration evidence is unambiguous on this direction.
Across four generations of island-experiment loops the most reliable PnL
mechanism has been *composing strictly orthogonal SKIP axes on top of an
unmodified base*:

- Gen-1: rolling-spread-p75 lifted island-0's base +26.55% PnL;
  choppiness-ratio lifted island-2's base +34.13%.
- Gen-2: stacking spread on top of base on island-1 gave +70.29% PnL;
  *adding* a third axis (chop) amplified to +173.95% (1.7× lift).
- Gen-2: chop+spread two-gate composition on island-2 gave +223.42% vs base.
- Gen-3: top-of-book size-asymmetry stacked on island-2's two-gate stack
  produced the largest single-loop lineage gain of the experiment (+92.42%
  vs lineage, +522.30% vs base).

The shared mechanism is that the oracle's 30s forward signal degrades
disproportionately during structurally distinct adverse-microstructure
regimes (wide-spread liquidity vacuums, whipsaw price-path chop, signed
aggressor-flow pressure), and these regimes are near-independent — their
union covers a larger top-cost slice than any single gate, while the
multiplicative trade-count cost stays modest (≤7% incremental per axis
on most bases). Drawdown also TIGHTENED on every island where stacking
worked, evidence the filtered slice carries tail-loss trades.

G1L2's opposite-tape SKIP gate is structurally a SIGNED-FLOW axis (book
direction + per-quote OFI direction, both gating on the *adverse-to-trade*
sign). Rolling spread is a BOOK-DISTANCE axis (the absolute quote-distance
between best bid and best ask, independent of side). These two axes
should be near-orthogonal: a quote can have a high spread regardless of
which side has the heavier resting size, and the OFI can be strongly
adverse regardless of whether the spread is wide or tight. Independence
is the necessary condition the migrations have established for clean
additive compounding.

**Why I picked this over the alternative (passive child placement)**

G1L2's pre-registered `next` field offered two G1L3 candidates: (1)
stack a second orthogonal SKIP axis; (2) revisit G1L1's deferred
passive-child-placement branch (route borderline opposite-tape entries
as LIMIT children at the near side instead of binary-skipping them).

Candidate 2 structurally resembles the **failed "recover rejected
entries" pattern** documented in the gen-1 migration: island-1 g1l1's
flow-flip reversal exception (-43.13% PnL), island-1 g1l2's
min_trade_count loosening (-21.15% PnL), and island-2 g1l2's
trend-magnitude neutral-zone widener (-0.32%, zero marginal EV). The
common mechanism in all three failures was that the admitted population
carried path-risk or near-zero net EV — they were NOT a hidden cache of
high-EV entries the original gate had wrongly rejected. Routing
opposite-tape entries as passive LIMIT children would re-admit the
exact slice G1L2 just established is the *highest-cost* slice, hoping a
better entry price compensates for fighting fresh adverse flow — the
gen-1 migration's IS-vs-PnL dissonance finding (island-1 g1l2) directly
warns against this: better arrival price quality can coexist with worse
realized PnL because gates encode path-risk information beyond
execution-cost quality.

Candidate 1 structurally resembles the **succeeded "compose SKIP axes"
pattern** documented in all four migrations. It is strictly the higher-
expected-value choice on the available evidence.

**Why rolling-spread-p75 specifically (not choppiness or size-asymmetry)**

Three candidate axes are well-established by cross-island migrations:
rolling-spread-p75 (gen-1+), choppiness-ratio (gen-1+, base-agnostic at
1.5), and top-of-book size-asymmetry (gen-3, ratio=1.5).

- Spread-quantile is the *most-replicated* axis: it has been
  successfully composed on top of *every* base it has been tried on
  (island-0 g1l1 +26.55%, island-1 g2l1 +70.29%, island-2 g2l1
  +223.42%). It carries the strongest prior probability of working.
- Choppiness-ratio is well-validated and base-robust at chop_neutral=1.5
  (afg, ptg, vrs all use 1.5), but on island-sig its information content
  could overlap with OFI (chop and short-window OFI both react to
  rapid signed-flow reversals — chop encodes magnitude, OFI encodes
  sign). The orthogonality argument is weaker here.
- Size-asymmetry uses the same `bid_size`/`ask_size` ratio that
  Lipton's imbalance `I` derives from — direct redundancy with the
  G1L2 imbalance leg. Falsified as a candidate by inspection.

Spread-quantile is the clean winner: structurally orthogonal to the
opposite-tape gate (book-distance vs signed-flow), most-replicated across
bases, ports cleanly at island-0's verbatim parameters (60s window,
q=0.75, min_samples=50). Per gen-3's ptg-isl-g3l2 finding, q=0.75 sits
on the EV peak across multiple bases — not a value that needs per-base
retuning.

**Why OR-skip composition (not AND-skip)**

The canonical winning recipe on island-1 g2l1 (the first successful
cross-island compose-spread-on-base loop) uses OR-skip: the spread gate
and the base gate each independently veto an entry. AND-skip would
require BOTH gates to fire simultaneously to skip, which would
*loosen* the existing G1L2 gate (a behavior pattern the migrations
established as a consistent regression). OR-skip preserves G1L2's
existing skip set as a strict subset of the new skip set, and adds the
spread-extreme slice as a new orthogonal contribution. This is the
single-change-per-loop preserving attribution: the opposite-tape gate's
PnL contribution is the floor for G1L3's expected PnL; spread-extreme
filtering is the variable under study.

**Expected outcome (pre-registered, fail criteria)**

- PASS the configured pass_gate (≥+5.0% PnL improvement vs simple,
  ≤+5.0% slippage regression). This is structurally guaranteed because
  G1L2 already PASSes at +863.30% and OR-skip can only add to the skip
  set, not remove from it — so the PnL contribution of G1L2's existing
  filter is preserved as a floor unless the new spread gate is so
  poorly tuned that it removes positive-EV trades faster than negative-
  EV ones.
- BEAT G1L2 by `refinement.targets`: at minimum +2.0pp PnL delta vs
  G1L2 ($1502.75 baseline → ≥ $1532.81) OR a meaningful sharpe lift
  (≥+0.5 absolute, 5.83 → ≥6.33) without regressing the others by more
  than `refinement.targets` allows. This is the *targeted* hypothesis:
  the spread axis should add residual PnL on top of G1L2's signed-flow
  axis. Failure here would be the most informative single result:
  spread is partially redundant with imbalance/OFI on the *sig* base in
  a way that wasn't visible to other islands' bases.
- DOWNSIDE FALSIFICATION: trade_count drop > 15% incremental vs G1L2's
  126,216 (i.e., trade_count < 107,284) with PnL also lower would
  indicate the spread gate is *over-restrictive on this base* — the
  surviving-population on a sig base has a different spread
  distribution and 60s/q=0.75 is too aggressive a cut. Per gen-2
  migration: re-tuning would then be the gen-2 followup.

**Cross-island input applied**

From `generation-1.json → what_worked` (compose SKIP axes): spread+chop
+(third) lifts PnL on every base where tested. I am adding spread on
top of my third axis (signed-flow opposite-tape), forming a
spread+signed-flow two-gate composition — different ordering from the
island-1 trio, but the same composition principle.

From `generation-1.json → what_failed`: I am NOT loosening the existing
gate — OR-skip strictly grows the skip set. I am NOT modifying base
mechanics — the opposite-tape gate is bit-for-bit unchanged.

From `generation-1.json → generalizable (3)`: "Gate additions MUST ship
with instrumentation counters or null-effect results are
undiagnosable." I preserve G1L2's per-side `evaluated/skipped` counters
AND add NEW per-axis (`opposite-tape vs spread`) counters so the
attribution between the two SKIP axes is recoverable from logs.

From `generation-2.json → generalizable (1)`: ADD orthogonal SKIP axes
ON TOP of an unmodified base; never modify the base. I am layering on
top of the unmodified G1L2; G1L2 itself was the "unmodified base" for
this loop.

From `generation-2.json → generalizable (3)`: port the MECHANISM and
the COMPOSITION SEMANTICS verbatim; consider per-base retuning of the
operating point. For spread-quantile the migrations established q=0.75
is base-robust (gen-3 ptg-isl-g3l2 confirmed q=0.75 sits on the EV
peak). I port the operating point verbatim and defer per-base retuning
to G1L4 if warranted.

From `generation-3.json → what_worked`: top-of-book size-asymmetry
ported at the same threshold (1.5) across two different bases. By
analogy, spread q=0.75 ported across three different bases continues to
work without retuning.

From `generation-4.json → generalizable (1)`: mechanism class, not axis
count, is the binding constraint at saturation. This island is far
from saturation — G1L2 is the FIRST gate on the sig lineage, so I am
adding axis #2 of an empirically-confirmed 4-axis stack (spread, chop,
flow, size-asymmetry). There is no saturation-class concern here yet.

## Implementation Decisions

**Structural change vs G1L2**: ONE change. Add the rolling-spread-p75
gate as an orthogonal SKIP axis. The opposite-tape gate's predicate,
thresholds, window, AND semantics, OFI computation, instrumentation
counters, and anti-cascade contract are bit-for-bit preserved from
G1L2.

1. **New state for the spread gate**, mirrored from `afg-isl-g2l1` for
   minimum-risk porting:
   - `_spread_window_ns: int` (60.0s as ns)
   - `_spread_quantile: float` (0.75)
   - `_min_samples: int` (50)
   - `_spread_deque: deque[tuple[ts_event_ns, spread]]`
   - `_latest_spread: float | None`

2. **New on_quote_tick branch**: append `(ts_event, ask - bid)` to
   `_spread_deque` and update `_latest_spread`. Already-subscribed
   quote-ticks from G1L2 — no new subscription needed.

3. **New gate function** `_spread_gate_skip(order)`: prune to window,
   warm-up no-op when `n < min_samples`, otherwise compute the
   linearly-interpolated quantile, skip if `latest_spread >
   threshold`. Code ported verbatim from `afg-isl-g2l1`.

4. **OR-skip composition in `on_order`**: evaluate the spread gate
   FIRST (cheaper, no OFI prune), then the opposite-tape gate. If
   either fires, skip; `_position_flat = True` (anti-cascade).

5. **Per-axis instrumentation**: in addition to G1L2's
   `_evaluated_count_{buy,sell}` and `_skipped_count_{buy,sell}`,
   add `_skipped_by_spread_{buy,sell}` and
   `_skipped_by_opposite_tape_{buy,sell}` so the attribution between
   the two axes is recoverable. NB: the per-side `evaluated` count
   semantics are preserved (evaluated = reached the gate region;
   excludes reduce-only and anti-cascade re-entries). The two
   per-axis skip counters together sum to `_skipped_count_*` ONLY
   in the absence of co-firing; with OR-skip a single order can match
   both gates and we count it under the FIRST-firing gate
   (spread-first ordering chosen). This is documented in the on_stop
   log so the human reader can read the firing-rate attribution
   correctly.

**Quantity invariant**: never modify `order.quantity`. Only skip or
submit (same as G1L2).

**No look-ahead**: spread deque is fed by `on_quote_tick`; pruning uses
`order.ts_init` as the cutoff anchor. Same guarantee as G1L2's OFI
deque.

**Subscription**: `_ensure_subscribed` already subscribes to quote
ticks (G1L2 contract) — no change needed.

**Reduce-only / closing orders always submit** (intraday_flat
compliance). Same as G1L2.

**Defensive**: if `ask < bid` (crossed book), skip the spread sample
(same defensive guard as `afg-isl-g2l1`).

## Backtest Observations

**Train window**: 12 dates, 2026-03-08 .. 2026-03-20 (full configured train set).

**Raw aggregate numbers (sig-isl-g1l3 vs simple baseline AND vs G1L2 parent)**:

| metric              | sig-isl-g1l3 | sig-isl-g1l2 (parent) | simple (base) | vs_base    | vs_parent  |
|---------------------|--------------|-----------------------|---------------|------------|------------|
| realized_pnl        |  3265.00     |  1502.75              |   156.00      | +1992.95%  | +117.27%   |
| unrealized_pnl      |     0.00     |     0.00              |     0.00      |  n/a       |  n/a       |
| sharpe_ratio (12d)  |   13.4510    |    5.8283             |    0.5996     | +2143.48%  | +130.79%   |
| max_drawdown_pct    |   -0.0268    |   -0.0472             |   -0.0529     |  +49.24%   |  +43.11%   |
| win_rate            |    0.3668    |    0.3600             |    0.3506     |  +4.62%    |  +1.91%    |
| trade_count         | 121,024      | 126,216               | 136,734       |  -11.49%   |  -4.11%    |
| mean_slippage       |     0.0      |     0.0               |     0.0       |   0.0%     |   0.0%     |
| is_weighted_bps     |    0.0389    |    0.0472             |    0.0389     |   +0.05%   |  -17.64%   |

(`mean_slippage = 0.0` on both sides reflects pure marketable-order
arrival-mid slippage being zero in this strategy+symbol; vs_base/vs_parent
slippage % carries no information content. Same artifact as G1L1, G1L2,
and every other algo on this baseline.)

**Trade count**: 121,024 — far above the 30-trade reliability threshold;
per-date sample sizes range from 349 (20260308) to 22,222 (20260319);
every date has ≥349 trades. Numbers trustworthy.

**Trade-count slice comparison vs G1L2**:

- G1L2 (opposite-tape only):           126,216 trades (-7.69% vs base)
- G1L3 (opposite-tape OR spread-p75):  121,024 trades (-11.49% vs base, -4.11% vs G1L2)

The spread axis adds an incremental ~4.1% trade-count cost on top of
G1L2's existing ~7.7%, well inside the migration-validated `≤7%
incremental per axis` headroom guide. The new total skip rate is ~11.5%
of the open-order population.

**Headline interpretation**: PASS both the configured pass_gate (vs
simple) by >1900pp margin AND the refinement.targets gate (vs G1L2
parent) by wide margins on PnL and sharpe simultaneously. The
composition mechanism predicted by the gen-1+ migrations transferred
cleanly from cross-island bases to the sig (signed-flow opposite-tape)
base: adding the orthogonal book-distance axis (rolling-spread-p75)
on top of the existing signed-flow axis (opposite-tape) compounded
EV-positively without meaningful redundancy.

**Mechanistic diagnosis** (per Step 8 honesty: explain, don't just report):

1. **Per-date PnL recovery is universal**: Every one of 12 train dates
   showed positive PnL improvement vs G1L2. The cleanest pattern is on
   the high-volume late-window dates where the spread distribution is
   wider and the opposite-tape gate had less of the available skip
   slice already covered:
   - 20260316: G1L2 -$318.00 → G1L3 -$8.00   (+$310.00 recovery)
   - 20260317: G1L2 -$20.50 → G1L3 +$130.50  (+$151.00 lift)
   - 20260319: G1L2 +$422.75 → G1L3 +$633.00 (+$210.25 lift)
   - 20260320: G1L2 +$336.00 → G1L3 +$546.00 (+$210.00 lift)
   - 20260318: G1L2 +$375.75 → G1L3 +$495.50 (+$119.75 lift)

   No date was meaningfully harmed.

2. **Drawdown TIGHTENED by 43% vs G1L2** (-0.0472 → -0.0268), reproducing
   the cross-island pattern (every island that stacked SKIP axes saw
   drawdown tighten alongside PnL gains). Confirms the spread-skipped
   slice contains tail-loss trades, not just mean-cost trades.

3. **is_weighted_bps essentially neutral**: G1L3 lands at 0.0389 bps vs
   base 0.0389 bps (+0.05% change) — a clean null on the execution-cost
   diagnostic. G1L2 had documented an IS-vs-PnL dissonance (+21.48%
   IS-worse while PnL was dramatically better), confirming that the
   opposite-tape gate's PnL benefit came from filtering path-risk that
   IS-bps couldn't see. Now adding the spread axis brings IS-bps back
   in line with base — the spread-cut trades have a higher arrival-price
   IS cost (wide-spread by definition), and removing them improves the
   surviving-population IS quality back to base levels. Mechanistically
   coherent: the two axes encode different cost components and removing
   both improves PnL via different mechanisms.

4. **Sharpe more than doubled** (5.83 → 13.45) on a strictly added gate
   — the additional filtered slice is high-variance loss material, so
   tightening the tail improves Sharpe disproportionately to mean PnL.

5. **Win rate moved +0.69pp** (0.3600 → 0.3668). This does not clear
   the refinement.targets.min_winrate_delta_pp = 2.0 target, but PnL
   (+117%) and sharpe (+130%) clear their respective deltas by orders
   of magnitude. The refinement gate requires at least one target to
   be cleared without meaningfully regressing the others; PnL and
   sharpe both clear by 50×+, mdd improves, win-rate moves the right
   direction. Verdict: PASS refinement.

**Verdict**: PASS. Realized PnL improvement +1992.95% vs simple base —
vastly exceeds the +5.0% pass gate. Sharpe improvement +2143%. Drawdown
tightened +49% (in the favorable direction). No slippage regression. PASS
refinement vs G1L2 parent on PnL +117% and sharpe +7.62 absolute, both
clearing their delta targets by wide margins.

**Status note**: per operator instruction "no snapshot, no push, no new
branch" — I am NOT invoking the snapshot skill despite the PASS verdict.
This loop file documents the result; OOS evaluation is the operator's
decision when this lineage is ready to ship.

**Implication for sig-isl-g1l4 (the next loop in this generation)**:

- **Two-axis composition has confirmed headroom on the sig base.** The
  next-highest-leverage direction is to test a THIRD axis. The
  gen-3 migration named two confirmed orthogonal candidates:
  - **Choppiness-ratio** (chop_neutral=1.5, base-agnostic per gen-3) —
    encodes price-PATH whipsaw, structurally distinct from book-distance
    and signed-flow. Highest cross-island replication count.
  - **Top-of-book size-asymmetry** (ratio=1.5, ported clean across two
    bases in gen-3 with no per-base retune required) — encodes book
    DEPTH state, complementary to spread's book-DISTANCE.

  Of the two, **choppiness-ratio is the cleaner first candidate** for
  G1L4 because size-asymmetry uses `bid_size`/`ask_size` ratios that
  overlap with Lipton's imbalance `I` in the opposite-tape gate
  (asymmetry threshold 1.5 maps to |I| ≈ 0.20, below the existing 0.33
  cutoff but still partially redundant). Choppiness is structurally
  furthest from both existing axes.

- **Threshold tuning is deferred**: G1L3 ports verbatim and passed
  cleanly; threshold sweeps on either axis can wait until composition
  is fully tested (per the gen-2 migration's prescription to map
  saturation before tuning).

**Cross-island corollary for the next migration**:

- The signed-flow + book-distance two-gate composition added +117%
  to G1L2's already-strong +863% standalone PnL — confirming that
  the gen-2 migration's `generalizable (1)` rule ("compose orthogonal
  SKIP axes ON TOP of an unmodified base") generalizes to a base
  whose existing gate is itself a microstructure SKIP composition
  (Lipton AND Kolm). The unmodified-base contract holds at the
  loop-lineage level, not just the algo-base level.
- The spread q=0.75 / 60s window / min_samples=50 operating point
  continues to port cleanly across bases — now confirmed on FOUR
  bases (ptg, afg, vrs, sig) without per-base retune. This is the
  most-replicated operating-point port in the experiment to date.
- IS-bps and PnL re-align after stacking the spread axis on top of
  the opposite-tape gate (G1L2's +21% IS dissonance shrinks to +0.05%
  on G1L3). This is a new diagnostic finding: the IS-vs-PnL
  dissonance documented as a generalizable cross-island warning in
  gen-1 can be _resolved_ by adding a book-distance axis that
  removes the wide-spread (high-IS-cost) slice the signed-flow axis
  was leaving intact.

