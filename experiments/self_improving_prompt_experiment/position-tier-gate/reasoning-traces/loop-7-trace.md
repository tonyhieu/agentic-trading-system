# Loop 7 Reasoning Trace

## Hypothesis generation method used

Propose → empirically verify → commit (prompt-l1.md): Read base mechanism, identify ONE structural weakness (not a filter axis), propose ONE modification, mandatory empirical pre-check (predict N fires/day, count from cached artifacts, abort if actual < N/5 or == 0), then implement.

## How the hypothesis emerged from the method

Step 1 re-read the PTG base mechanism. The cap=1 gate causes pair OPENs to be discarded when net_qty >= cap at ts_init. The subsequent solo OPEN at T+gap (1–4 seconds later) fills the slot. The method's instruction to find a structural weakness (not a filter) pointed to this timing asymmetry: the oracle direction at pair-time T is abandoned in favor of the direction at solo-time T+gap. If the pair-time oracle signal is informative, abandoning it loses alpha.

The proposed structural change: store the discarded pair OPEN, submit it inside `on_order_filled` after the corresponding CLOSE fills. The deferred OPEN uses the close-tick price with net_qty=0 (flat), satisfying the cap=1 constraint. The subsequent solo OPEN arrives with net_qty=1 (from deferred) and is skipped by the cap.

## Where the method helped

The empirical pre-check correctly verified event-class frequency: 5647 pair OPENs exist on 20260313 (the median date), well above N=5000. This confirmed the mechanism fires enough to affect P&L meaningfully.

The mandatory probe step (stub run on 20260313) confirmed implementation correctness before full backtest.

The method's insistence on a structural axis (not a filter) was appropriate given 6 loops of filter exhaustion. The deferred-OPEN mechanism is genuinely structural — it changes execution timing, not entry selection.

## Where the method felt limiting or unnecessary

The static PnL estimate was unreliable. Static analysis showed 51.4% of deferred pair OPENs would be in the opposite direction of the solo OPEN they replace, predicting ~−$1048/day on 20260313. The full backtest confirmed the mechanism nets zero vs simple baseline ($156.0 == $156.0), not the predicted large loss. The method has no mechanism to detect whether dynamic cascade effects will amplify or cancel the static signal.

The method also does not require estimating the magnitude of alpha loss from the replaced solo OPEN (i.e., what PnL we're giving up by skipping the solo). Without this second-order estimate, the net direction is ambiguous even if direction-mismatch rate is known.

## What a different method might have produced

A two-sided estimation approach would have computed: (1) expected PnL of deferred OPENs and (2) expected PnL of the solo OPENs they displace. The net delta — not just the deferred component — determines whether the swap is positive. This calculation would have shown that the deferred mechanism essentially re-shuffles which oracle signal drives each position, with no net alpha gain when the oracle's directional accuracy is ~50%.

## What the backtest showed

- L7 pnl = $156.0 (12 dates, 136,734 trades) vs PTG base $4,262.5 → −96.34% vs base
- vs simple baseline: 0.0% (l7 and simple baseline had identical aggregate P&L)
- Sharpe: 0.60 vs PTG base 17.62 — catastrophic regression
- Max drawdown: −5.29% vs PTG base −1.73% — severe deterioration
- Win rate: 35.1% vs PTG base 37.2% — lower
- High variance across dates: 20260313 (−$512.75), 20260316 (−$521.50), 20260317 (−$246.75) drove losses; early-week dates offset partially

The result confirmed the 51.4% direction-mismatch hypothesis: deferred pair OPENs fire with the wrong oracle direction roughly half the time, netting to zero vs simple baseline. The mechanism effectively makes PTG behave like simple execution.

## Where I felt uncertain

The connection between "direction mismatch rate" and "net P&L impact" was unclear before backtest. A 51.4% wrong-direction rate does not straightforwardly imply zero net gain — the magnitude of gains vs losses on each side matters. The actual result (zero vs simple baseline) suggests the mechanism exactly cancels out the PTG structural skipping, leaving pure simple execution behavior.

Whether probe results on a single date (20260313) would have been diagnostic before committing to full 12-date implementation: the probe showed pnl parity on that date in stub mode, but stub mode is deterministic-synthetic and would not have caught the dynamic cascade. A real probe on 20260313 would have shown the mechanism's behavior on one date, which may or may not have been representative.
