# Loop 3 Reasoning Trace

## Hypothesis generation method used

Seed `prompt-l0.md` — a 4-step linear single-pass method: (1) read the base algo's
code + NOTES.md, (2) identify ONE weakness, (3) propose ONE concrete modification,
(4) state the expected direction of change in P&L and slippage. The previous loop's
evolved method (proposer–EDA-criticizer) was reverted by the critic after loop 2's
-48.6% regression, so this loop runs on the same seed method that produced loop 1.

## How the hypothesis emerged from the method

Step 1 → I read `execution_algos/aggressor-flow-gate/execution_algorithm.py` and
its NOTES.md. The base maintains a 10s signed-aggressor-flow deque with
`flow_threshold = 2.0`, and the NOTES.md "What underperformed" section flags the
canonical weakness verbatim: "the filter holds back entries during adverse-flow
periods, but those exact moments sometimes offer the best fill prices". A +21.9%
IS regression vs `simple` is named as the manifestation.

Step 2 → The weakness I picked is the stale-window failure mode of a single
rolling window: a 10-contract sweep at t=-9s leaves `net_flow_10s = +10` for nearly
10 more seconds even if no further buying continues. The 10s window cannot
distinguish "pressure is still active" from "pressure ended 9s ago but the window
hasn't aged it out yet." Same rolling-bucket signal, two very different regimes.

Step 3 → ONE concrete modification: add a 3-second inner confirmation window and
require BOTH windows to be adverse for a skip. SELL skip iff
`net_flow_10s >= 2.0 AND net_flow_3s >= 1.0`. BUY skip iff
`net_flow_10s <= -2.0 AND net_flow_3s <= -1.0`. Threshold 1.0 ≈ one MES contract
in the last 3s, picked by proportional reasoning (3s is 30% of 10s, 0.6 rounded
up to 1.0). No EDA on either parameter — the seed method has no EDA step.

Step 4 → Predicted realized_pnl up (+5% to +20%), trade_count up modestly, slippage
unchanged, sharpe/win_rate/max_dd directionally uncertain. The single-result
falsifier I named in NOTES.md: if trade_count is flat AND P&L is flat or negative,
the 3s/1.0 confirmation almost never vetoes (1.0 too loose) and the algo
degenerates to base.

The hypothesis emerged cleanly from the method in the sense that Steps 1–4 ran in
order. But the method does not require me to validate the 3s window length or
the 1.0 threshold against the data, and I did not. Both came from armchair
proportional reasoning.

## Where the method helped

Forcing exactly ONE modification kept the algo simple. The patch is gate-only:
add a parallel deque, AND the two conditions. No fill mechanics change, no
quantity manipulation, no participation-cap interaction. The constraint-compliance
case writes itself when the modification is bounded to one mechanism (submit-vs-
skip). Loop 2's reverted method allowed three candidates and a final selection
step that arguably amplified armchair choices across more surface area; this seed
method's "pick one" rule kept attack surface small.

Reading the base's NOTES.md "What underperformed" section was load-bearing —
it named the IS regression directly and described the over-skipping mechanism in
the base author's own words. I picked the weakness the base author flagged
themselves, not one I had to discover.

## Where the method felt limiting or unnecessary

The 3s window length is the single biggest unknown in this algo, and the method
gives no way to calibrate it. I picked 3s because it's "roughly one-third of 10s"
and "long enough for 2–3 prints under typical MES arrival rates" — neither
number is measured. Step 3 of the seed method is "propose ONE concrete
modification," and that step is silent on how to set continuous parameters inside
the modification. Same problem the loop-1 critic flagged about the
`flow_threshold = 0.6` choice in loop 1: the method permits an uncalibrated
quantitative knob inside an otherwise sound mechanism.

The 1.0 confirmation threshold has the same problem. I rounded up from 0.6 to 1.0
to make "one fresh MES contract" the minimum confirmation. That's an aesthetic
choice, not a data-driven one. If the typical 3s aggressor-flow magnitude during
the regime I'm targeting (stale-but-windowed pressure that has actually ended) is
0.5 or 1.5 contracts, the 1.0 threshold is on the wrong side of the empirical
distribution.

Step 4 (predicted direction) had to be stated without any prior count of how
often the 3s window will actually veto a base-gate skip. I wrote "+5% to +20% P&L"
and "trade_count up 1-6%" but those bounds are pulled from intuition — the method
gave me no way to derive them from the data. The realized -43.1% P&L on
trade_count +7.4% is exactly the falsifier shape I named: trade_count rose more
than my upper bound (6%) AND P&L fell. The method has no Step-X that would have
caught this in advance.

## What a different method might have produced

A method that interposed a single mandatory measurement between Step 3 and Step 4
— "for any continuous parameter introduced by the modification, measure the
distribution of that signal under the regime the modification targets, and pick
the parameter at the boundary of that distribution" — would have forced me to
ask: across the base's 21% skip rate, what fraction of skips have a 3s net-flow
of magnitude < 1, < 0.5, < 0? An empirical histogram would have told me where
to put the threshold. If the typical 3s magnitude during base-skip events is
already 1.5+ contracts (because the base only fires when the burst is recent and
genuinely active), then 1.0 would veto almost nothing and the algo degenerates to
base — except this time both my windows ARE adverse-confirmed, so the gate fires
more reliably and I LOSE more good entries, not fewer. That looks consistent
with what the backtest actually showed: trade_count went UP (115,099 vs base's
107,198 = +7.4%) but P&L went DOWN, which means the extra orders are net
negative. The confirmation requirement reduced skips, but the orders it
recovered were the bad ones — adverse-flow events that are GENUINELY adverse,
and where the base's stricter (one-window) gate was correctly skipping. The
hypothesized "stale-window failure mode" was the wrong characterization. A
measurement step would have caught this: the regime I theorized (stale flow,
ended pressure, base over-skips) is rarer than the regime where the second
window happens to be neutral simply because aggressor flow is bursty (i.e., a
flat 3s window during an active 10s window often means the burst is mid-pause,
NOT that it has ended).

## What the backtest showed

| metric           | base       | sip-afg-l3 | delta            |
|------------------|------------|------------|------------------|
| realized_pnl     | 1255.5     | 714.0      | **-43.13%**      |
| mean_slippage    | 0.0        | 0.0        | 0.00%            |
| sharpe_ratio     | 5.594      | 3.057      | -45.4%           |
| max_drawdown_pct | -3.32%     | -4.13%     | worse by 0.81pp  |
| win_rate         | 0.3549     | 0.3507     | -0.42pp          |
| trade_count      | 107,198    | 115,099    | +7.4% (+7,901)   |
| is_weighted_bps  | 0.0472     | 0.0507     | +7.4% (worse IS) |

trade_count rose +7.4% (above my predicted upper bound of +6%) and realized_pnl
fell -43.1% (sign-opposite of my predicted +5% to +20%). The pre-registered
falsifier in NOTES.md ("trade_count flat AND P&L flat/negative") did NOT trigger
verbatim — trade_count was emphatically NOT flat. The actual outcome is a
DIFFERENT falsifier I should have named: "trade_count rises significantly AND
P&L falls" — which means the recovered orders are net-negative, i.e. the
mechanism's premise (recovered orders are 'good fills at temporarily-favorable
arrival prices') is empirically wrong. The is_weighted_bps regression (+7.4%
worse) is the cleanest signal that the recovered orders are systematically
adverse, not systematically favorable.

Surprises: the magnitude of the regression (-43%). I expected directional risk
but in the band of -10% to +20%, not -43%. Sharpe dropping 45% while win_rate
barely moved (-0.4pp) tells me the per-trade P&L distribution widened — recovered
orders aren't just slightly bad, they have high variance. max_drawdown worsening
by 0.81pp confirms more equity-curve excursions in volatile periods.

Confirmation of expectations: mean_slippage stayed at 0.0 (gate-only algo, no
fill mechanics). Quantity invariant held. Constraint compliance was preserved.

## Where I felt uncertain

The 3.0s window length: chose by proportional reasoning, did not measure typical
MES inter-trade gaps. If real density is much sparser than I assumed (and 3s
sometimes contains 0–1 prints), the inner window is too short to be statistically
meaningful and noise dominates the AND condition.

The 1.0 inner threshold: chose to make "one fresh MES contract" the minimum
confirmation. Did not measure the empirical distribution of 3s net-flow magnitudes
under base-skip events. NOTES.md "Concerns" section calls this out explicitly.

AND vs OR semantics: I reasoned that AND is the stricter (fires-less) gate,
matching the "base over-skips" hypothesis. I did not consider that fires-less
also means recovers-MORE-bad-orders if my characterization of the over-skip
regime is wrong. The backtest result suggests the latter dominated.

Anti-cascade interaction: after any skip, `_position_flat = True` forces the
next open unconditional. I preserved this verbatim from base. I did not consider
whether the interaction between fewer skips (from AND) and the post-skip
unconditional reset changes the equilibrium of skip-then-recover patterns. Lower
skip rate means fewer post-skip unconditional re-entries, which means more orders
go through the standard gate path, which means the gate's behavior on the
"normal" path matters more than in base. Not analyzed.

Single-result falsifier I named in NOTES.md was the wrong falsifier for what
actually happened. trade_count flat would have meant the gate didn't change
anything; instead trade_count rose meaningfully, which means the gate DID change
behavior — but in the wrong direction. The right falsifier would have been
something like: "if recovered orders (orders submitted by sip-afg-l3 that base
would have skipped) have mean P&L below the win-rate-implied baseline, the
hypothesis is wrong." I had no instrumentation to compute that.
