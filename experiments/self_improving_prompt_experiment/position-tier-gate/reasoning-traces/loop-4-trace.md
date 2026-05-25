# Loop 4 Reasoning Trace

## Hypothesis generation method used

Propose -> empirically verify event-class non-empty -> commit (the loop-1
critic's evolved method, restored to .current_prompt.md by the loop-3
revert). Mandatory step 4: commit to a numeric N for events-per-day, count
from the cheapest verification surface (cached `positions.csv` from a
behaviorally-identical algorithm), pass/fail based on `actual >= N` (no
counterfactual probe required).

## How the hypothesis emerged from the method

The method's "ONE plausible weakness" constraint forced me to pick a
single axis. The loop-3 critique flagged loops 2 and 3 as having both
attacked the SAME axis (spread at on_order time) with flag-inverted
predicates. Step 2's "highest plausible frequency" instruction nudged
me toward weaknesses already known to be high-volume (~7,500
base-skipped OPENs/day), so I looked for a NEW conditioning variable on
the same event class.

I considered four alternatives during step 2:
1. Hold-time of the in-flight position at flip moment (would override on
   long-hold flips).
2. Direction of the in-flight position's unrealized PnL at flip moment
   (override when underwater).
3. Number of recent same-direction flips in the last N seconds
   (override when not in a flicker pattern).
4. Aggressor side of the most recent trade tick (override when
   aggressor matches the OPEN side).

I picked (2) because it was the easiest to verify with a static artifact
(sip-ptg-l2's positions.csv has realized_pnl per closed position, which
proxies in-flight unrealized PnL at the close moment). The empirical
pre-check requirement explicitly biased me toward weaknesses that can be
counted from cached files; (1), (3), (4) would have needed a probe or
raw DBN inspection.

Step 4 then forced a numeric commitment. I wrote N=100 events/day,
counted 1,054/day in the surface (10.5x the floor), and passed. The
sign signal was strong: the 12,652 in-flight positions that were
underwater by > 1 tick collectively lost -$9,337 — meaning the prior
direction was demonstrably wrong on aggregate. From this I anchored the
expected uplift band at +3% to +10%, with explicit acknowledgment that
the chain-effect lesson from loops 2/3 could erode or reverse this.

## Where the method helped

The empirical pre-check forced me to operationalize a fuzzy intuition
("flip after losing should be corrective") into a counted, falsifiable
event class. Without the N-commitment, I would have proposed "override
when the in-flight is losing" without specifying HOW LOSING (which I
defaulted to 1 tick); the count showed where the distribution lives and
gave me the threshold-tier table (12,652 at 1 tick, 816 at 5 ticks, 62
at 10 ticks). That same table also revealed the magnitude band: at
1-tick threshold the override is plentiful but per-event signal is
weak (-$0.738 mean prior-PnL); at 5-tick threshold it's rare but
strong (-$1.870 mean). I chose 1 tick on the conservative-frequency
side; a 5-tick variant would have been a different proposal.

The "ONE modification" constraint also kept me from bundling.
Specifically, I considered pairing the loss-corrective override with
keeping a tighter loss_threshold for the trailing trades in a session
(adapting threshold by time-of-day). The method's hard cap on
modifications per loop forced me to leave that for a future loop.

## Where the method felt limiting or unnecessary

**The pre-check surface is the chronic blind spot.** Step 4b says "if
your proposal conditions on an order-stream property, count it from
cached artifacts." But my conditioning property — in-flight unrealized
PnL at on_order() time — is NOT in cached artifacts directly. It is
*proxied* by `positions.csv:realized_pnl` (PnL at close moment).
Realized_pnl ≈ unrealized at flip is true to within microseconds of
slippage when the close fires at the same ts_init as the flip... but
it does NOT capture the on_order time computation that uses the LIVE
QUOTE MID, which can differ from the close fill price by spread/2.
The method gave me no language to think about this gap.

In practice, the override fired 653/day (actual) vs 1,054/day
(predicted) — a 1.6x undercount, well within the 5x failure threshold,
so the method judged the count "fine." But the discrepancy is a signal
that my on_order-time mid is materially different from the close-fill
distribution, in ways the method had no machinery to surface.

**The method has no counterfactual.** This is the persistent failure
mode the loop-3 critique tried to fix and the revert undid. My step 5
explicitly acknowledged loops 2/3 had falsified linear-EV
extrapolation, but I had no way to TEST whether my new axis would
suffer the same fate. I wrote "+3% to +10% with risk of reversal" —
which is honest, but conservative-band hedging is not the same as
falsifying a hypothesis before burning a 12-date eval. The probe loop-3
implemented was exactly the right shape; reverting threw it away.

**Step 5's magnitude band is degenerate when chain effects are
significant.** "A few percent" vs "double-digit percent" doesn't
distinguish "method passed but axis is dead" from "method passed and
axis is promising but my chain-effect intuition is wrong." Loop 4
landed at -33.7% — way outside even the pessimistic side of my band.
The method asked me to predict direction and magnitude on an
event-class signal that has been repeatedly shown to be a poor
predictor for aggregate outcomes.

## What a different method might have produced

A **mandatory one-day probe** (the loop-2 critic's design that was
reverted) would have caught this. I would have run sip-ptg-l4 on
20260313 and seen the per-date PnL was -$124.50 vs base +$65.50 (a
$190 loss on a moderate-volume day) — and aborted before burning the
12-date eval. The loop-3 single-date pattern (-$132.75 on 20260313)
was indeed predictive of the full-window failure; my loop-4 has
exactly the same shape (-$190 on 20260313 -> -$1,437 across 12 dates).
Both axes share the deeper structural property that "override the
base skip" is destructive — independent of which condition triggers
the override.

A **multi-candidate proposer-criticizer** (a structural variant the
loop-3 critic also proposed) would have helped differently. Of my four
candidates in step 2, the "hold-time of in-flight position" axis (1)
is structurally distinct from (2) in that it does NOT condition on a
quantity that has already shown the prior position is wrong — it
conditions on persistence, which has independent signal. A
two-candidate method that probed (1) AND (2) on one date side-by-side
would have provided diagnostic information about WHICH axis carries
signal rather than committing to one and post-hoc explaining failure.

Most importantly: a method that REQUIRED two structurally orthogonal
candidates (where "structural" is defined as "different field of
position/quote object") would have nudged me away from (2) entirely
once it became clear that "submit on a signal of prior-direction
wrongness" is the loop-3 anti-pattern in a new guise.

## What the backtest showed

Aggregate metrics over 12 train dates, sip-ptg-l4 vs base
`position-tier-gate`:

| metric            | base       | sip-ptg-l4 | delta                  |
|-------------------|-----------:|-----------:|------------------------|
| realized_pnl      | 4,262.50   | 2,825.25   | **-1,437.25 (-33.72%)**|
| sharpe_ratio      | 17.619     | 12.977     | -4.642 (-26.4%)        |
| max_drawdown_pct  | -0.01727   | -0.02175   | -0.00448 (worse 26%)   |
| win_rate          | 0.37204    | 0.36416    | -0.0079 (-0.79 pp)     |
| trade_count       | 90,433     | 98,270     | +7,837 (+8.67%)        |
| mean_slippage     | 0.0        | 0.0        | unchanged              |
| vs_base_pnl_pct   | —          | -33.72%    | —                      |
| vs_base_slippage_pct | —       | 0.0%       | —                      |

**The big falsification:** every single one of the 12 dates lost
PnL vs the base. Not one date showed a positive delta. This is a
cleaner falsification than loops 2 or 3 (each of which had a few
dates beat base). The corrective-momentum hypothesis is wrong; flips
that occur while the in-flight is underwater are NOT systematically
followed by reversion to the new direction. They are flips at adverse
selection moments — the price has already moved against the prior
direction, and the new opposite-side OPEN is now entering at a
disadvantageous level.

**Override fire rate** (from `trade_count` delta and the
override-only-adds-submits property): ~7,837 extra trades over 12
dates = ~653/day. My pre-check predicted 1,054/day. The undercount
(actual is 0.62x of predicted) suggests the on_order time mid is
shifted vs the close-fill price in a way that fewer flip moments meet
the threshold than the close-time PnL distribution implied.

**Per-date pattern:** the absolute PnL loss is roughly proportional
to volume — low-volume days (20260308, 20260315) lose ~$10-20 vs base;
high-volume days (20260319, 20260309, 20260318) lose ~$80-220. This
volume-proportional loss is consistent with the override firing on a
condition that's volume-proportional (more flips per day = more
underwater-at-flip events = more override fires).

**What did confirm expectations:**
- `mean_slippage` unchanged (no book walking; algorithm only routes).
- `trade_count` ^ (override adds submits) — direction correct,
  magnitude undershoot.

**What was wrong:**
- The mechanism story. I assumed underwater-at-flip implied
  corrective-momentum on the new direction. The data says no: those
  flips are at moments when the price has *already* moved, and the
  new OPEN is now entering AFTER the corrective move, riding the
  noise that follows.

## Where I felt uncertain

- **The on-order mid vs close-fill price gap.** I used positions.csv's
  realized_pnl (close-time) as a proxy for on_order time unrealized.
  At the moment of flip, these should be within microseconds, but the
  close-fill is the actual transaction price (post-slippage) while the
  on_order mid is (bid+ask)/2. The override checks the latter; the
  surface measured the former. The 0.62x fire-rate undershoot is the
  empirical evidence this gap matters.

- **Whether axis (2) was meaningfully different from loops 2/3.** I
  argued in NOTES it was "portfolio-state + market-state hybrid" vs
  loops 2/3 "spread-only." But the underlying mechanism is the same:
  use the on-order quote tick to filter which flips to honor. The
  loop-3 critique's "different conditioning axis" warning was
  technically satisfied (different field) but not architecturally
  satisfied (same submit-on-skip pattern).

- **The 0.62x undercount on fire rate.** I noted it in step 4c but did
  not investigate. With hindsight, the right action was to add a debug
  log of fire-vs-skip decisions on one date and reconcile with
  positions.csv. The method did not require this and I did not do it.

- **Threshold choice.** I picked 1 tick because the 12,652-event count
  exceeded N=100 comfortably. The threshold-tier table (816 at
  5-tick, 62 at 10-tick) shows a sharper signal at deeper losses
  but with too-few events to drive aggregate PnL. A different
  researcher might have picked 2 or 3 ticks. I did not sweep.

- **No tool errors worked around.** The 12-date backtest ran clean on
  the first try; no OOM, no reruns. `--use-cached-baseline` produced
  baseline results from cache as expected.
