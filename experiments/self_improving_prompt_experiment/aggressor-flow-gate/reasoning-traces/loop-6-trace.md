# Loop 6 Reasoning Trace

## Hypothesis generation method used

Single-axis sibling calibration (`.current_prompt.md` carried over from
prompt-l5.md). The method takes the most-recently-kept algorithm
(`sip-afg-l5`), enumerates the numeric parameters it introduced, picks
ONE whose value most directly governs how often the new mechanism
fires, defines a measurement from train data, runs EDA on 2 train
dates to compute the current value's empirical firing rate vs a
pre-committed target rate, and ships the calibrated value. No new
structural mechanism; one parameter only.

## How the hypothesis emerged from the method

The method drove the hypothesis end-to-end. L5 introduced two
uncalibrated parameters (`relaxation_factor = 1.5`,
`max_consecutive_skips = 2`). The Step-3 selection rule ("parameter
that most directly governs firing rate") picked `relaxation_factor`
because it gates the streak==1 re-evaluation while
`max_consecutive_skips` only activates as a strict subset. The
calibration measurement was the distribution of |net_flow| one second
after each base skip across 2 train dates (20260309, 20260311),
producing 19,495 post-skip samples. Pre-committed target firing rate
0.30 → 70th percentile of |next_net_flow| = 5.0 contracts → calibrated
`relaxation_factor = 5.0 / 2.0 = 2.5`. Survival criterion: 66.7%
change ≫ 10% → proceed.

Backtest of `sip-afg-l6` (`relaxation_factor = 2.5`, all else
identical to L5) over 11 of 12 train dates (20260319 OOM'd, dropped
as the spec allowed):

- realized_pnl  = 984.25 (vs L5's 1002.0 on its own 11-date subset; vs base 970.00 on the same 11 dates)
- trade_count   = 79,165 (L5: 78,442; base: 87,760)
- sharpe_ratio  = 4.83 (vs L5 4.95)
- mean_slippage = 0.0
- max_drawdown_pct = -0.0296 (vs L5 -0.0293)
- win_rate      = 0.3535
- vs_base_pnl_pct = +1.47% (vs L5's +3.30%)

## Where the method helped

The pre-committed falsifier caught a real defect. The hypothesis said
"trade_count is a clean function of the gate firing rate; if it
moves less than ~2% vs L5, the calibration measurement did not match
the running mechanism." Trade_count moved +0.92% — well inside the
falsifier band. Without the firing-rate calibration, the L5 outcome
would have been a black box of "+3.30% works, ship it." With the
calibration, we can now say concretely: changing `relaxation_factor`
from 1.5 → 2.5 (effective threshold 3.0 → 5.0) was supposed to drop
the streak==1 gate firing rate from 0.60 → 0.30 and recover ~9,000
trades toward base; in fact it recovered ~700. The gate is not
binding the way the offline EDA assumed.

The method also constrained me to ONE parameter change, which kept
the attribution clean: I can directly point at `relaxation_factor`
as the variable and not handwave.

## Where the method felt limiting or unnecessary

Two things felt off. First, the EDA used worst-case adverse side
(BUY-gate fires on net <= -2.0; SELL-gate on net >= 2.0) — this
maximizes the base-skip rate, which means the offline 19,495 sample
count is an upper bound on the live algorithm's post-skip arrival
count. The trade_count prediction band ([82k, 86k]) was therefore
already known to be an overestimate; the methodspec didn't have a
shape to model "what would the gate fire on the LIVE order side."
Second, the survival criterion (10% parameter shift required) is a
sanity check on whether the calibration moved the value, not on
whether the *predicted outcome* would be detectable. A 66.7% shift
in the parameter that produced a 0.92% shift in trade_count is a
diagnostic finding the method has no rule to detect ahead of time.

## What a different method might have produced

A "live-mechanism EDA" architecture: instead of computing the
firing rate from offline DBN replay, instrument the kept algorithm
itself with a counter on the streak==1 evaluation branch (how many
times did the relaxed gate fire? how many times did it skip vs
submit?), and run ONE quick backtest at the current parameter to
get the empirical firing rate AS THE ACTUAL ALGORITHM EXPERIENCES
IT. Then calibrate against that rate, not the offline replay rate.
This would have caught the offline-vs-live mismatch up front: it
appears the live mechanism produces fewer streak==1 evaluations
than the offline worst-case-side simulation predicts, because the
oracle picks a real (not always adverse) side. The hypothesis would
have either: (a) calibrated against a much smaller real-world firing
rate and shipped a smaller parameter change, or (b) identified that
streak==1 events are too rare to calibrate at all and triggered the
zero-uncalibrated-parameter escalation.

## What the backtest showed

11 dates aggregated (20260319 dropped due to OOM in the algo
subprocess — matches the prior agent's note about sip-afg-l5):

- realized_pnl 984.25 vs base 970.00 → +1.47% vs base
- vs L5's 1002.0 (on L5's own 11-date subset) → -1.77%
- trade_count 79,165 vs L5 78,442 → +0.92% (falsifier triggered: <2%)
- sharpe_ratio 4.83 vs L5 4.95 → very slight regression
- mean_slippage 0.0 unchanged (zero-fill-cost model)
- max_drawdown_pct -2.96% vs L5 -2.93% → essentially unchanged

What surprised me: the trade_count barely moved. The hypothesis
predicted [82k, 86k]. The realized count was 79.2k. This is a strong
signal that the streak==1 path is not as active in the live algorithm
as the offline EDA assumed.

What confirmed expectations: mean_slippage and max_drawdown_pct were
roughly unchanged, as predicted; the parameter change is purely
internal to the gate; quantity invariant preserved.

## Where I felt uncertain

- 20260319 dropped from the aggregate due to algo-side OOM
  (`memory allocation of 4294967296 bytes failed`, exit -6). Same
  failure mode as on sip-afg-l5. 11 of 12 dates remain. Per the spec
  this is flagged but not fatal; both L5 (78,442) and L6 (79,165)
  trade-count comparisons are over the *same* 11-date set so the
  comparison is internally consistent.
- The pre-committed target firing rate (0.30) was justified pre-EDA
  with intuition only — "0.30 keeps the gate firing on roughly the
  adverse third of post-skip cases." The method has no rule for
  selecting the target; this is the single armchair residue inside
  what was otherwise an EDA-calibrated method.
- The offline EDA used worst-case adverse side at every arrival.
  The live algorithm picks the oracle-driven side. The offline
  firing-rate estimate (0.6043 at threshold=3.0) is therefore an
  upper bound on the live rate; the calibrated value (relaxation
  factor 2.5 producing offline rate 0.30) is similarly an upper
  bound, and the LIVE firing-rate shift produced by the change is
  almost certainly smaller than the offline 30-point shift
  predicted. The NOTES.md "Concerns" section flagged this before
  the backtest; the backtest confirmed it (trade_count delta was
  ~1/30th of the predicted band).
- The pnl direction came in slightly positive vs base (+1.47%) but
  slightly negative vs L5 (-1.77%). The L5↔base spread (+3.30%) was
  itself only ~3% so the absolute movement is in noise range; the
  trade_count falsifier is the cleaner diagnostic and it tripped.
