# Algorithm Notes: position-tier-ofi-gate

## Hypothesis

**Mechanism**: Stack two gates on the OPEN leg of each oracle signal:
(1) positional gate (position_cap=1) blocking the netting-OMS cascade
entry (inherited verbatim from position-tier-imbalance-gate), and
(2) a rolling-window **Order Flow Imbalance (OFI)** gate replacing the
static top-of-book imbalance gate. OFI is computed per
Cont/Kukanov/Stoikov (2014) "The Price Impact of Order Book Events":

    e_n =  +bid_size_n     if  bid_px_n  > bid_px_{n-1}      (bid moved up)
           +(bid_size_n - bid_size_{n-1}) if bid_px_n == bid_px_{n-1}
           -bid_size_{n-1} if bid_px_n  < bid_px_{n-1}      (bid moved down)
        +  -ask_size_n     if  ask_px_n  < ask_px_{n-1}      (ask moved down)
           -(ask_size_n - ask_size_{n-1}) if ask_px_n == ask_px_{n-1}
           +ask_size_{n-1} if ask_px_n  > ask_px_{n-1}      (ask moved up)

Per-tick `e_n` values are accumulated in a deque keyed by ts_event_ns.
At order-decision time, sum the deque over the last `window_seconds`.
  BUY  orders SKIP when OFI <= -flow_threshold (book is bleeding off the bid /
                                              accumulating on the ask = adverse to buying).
  SELL orders SKIP when OFI >=  flow_threshold (book is accumulating on bid /
                                              draining the ask = adverse to selling).
Reduce-only orders are always submitted (intraday_flat compliance).

**Inefficiency exploited**: Static top-of-book imbalance (the iter-1
signal) captures the *level* of bid vs ask size at a single tick — a
noisy point read. OFI captures the *flow* of order-book events
(additions, cancels, price moves) over a short horizon and has been
shown empirically (Cont et al. 2014; Kolm/Turiel/Westray 2021) to be a
substantially stronger short-horizon directional predictor of midprice
than the static ratio. The static-imbalance EMA tried in iter-2
(position-tier-imbalance-ema-gate) was a near-no-op because the
position_cap=1 gate already removes most of the order volume — but it
left the imbalance gate's residual contribution as a single-tick read
of *level*, not *change*. OFI is a structurally different signal:
positive OFI means net buying pressure has been entering the book over
the window, regardless of whether bids currently lead asks in raw size.

**Why it survives costs**: Slippage is zero by construction on this
fill model (see research/NOTES.md 2026-04-30 DATA ISSUE) — the only
cost axis that moves the gate is realized P&L. The decision is to skip
or submit; never inflate quantity. Skipping a high-OFI-adverse entry
costs zero in commissions (zero-cost fill model) and avoids an entry
into a moment when the book is leaning against the trade direction.

**Builds on**: position-tier-imbalance-gate (iter 1 PASS,
+9945% vs baseline). The single targeted change is REPLACING the
static `bid/(bid+ask)` imbalance gate with the OFI gate above. All
other components (position_cap=1, reduce-only fast-path,
min_total_size thin-book guard, exec_algo plumbing) are inherited
verbatim.

**Alternatives considered**:
- *Queue depletion*: skip when bid_size has fallen sharply over the
  window (for a BUY). Promising but very correlated with the
  bid-side component of OFI; OFI subsumes it and is symmetric on
  buys/sells.
- *Microprice gate*: replace mid with size-weighted microprice and
  skip when microprice deviates adversely. Microprice is just a
  smoothed reformulation of imbalance — same signal class, also
  shown to be near-no-op atop position_cap=1 in iter-2.
- *Spread gate*: skip when spread > k * rolling median. Already
  tried indirectly in streak-spread-tight (iter 0); not a microstructure
  *flow* signal.
- *VPIN / toxicity*: rich literature, but requires bucketed volume
  and trade signing — more state and slower to converge in a short
  window than OFI.

OFI was chosen because (a) it is a categorically different signal
class from static imbalance (flow not level), satisfying iter-2's
recommendation; (b) it has a strong empirical track record in the
microstructure literature; (c) it is local — no horizon-mismatch with
the 30-second oracle since we use the OFI signal only as an entry
filter for an already-generated oracle signal, not as a separate
predictor.

---

## Implementation Decisions

**Window**: 10.0 seconds — same default as the existing
aggressor-flow-gate (a related but distinct signal). Short enough to
capture the recent regime but long enough that at typical FX-futures
quote rates several events accumulate.

**flow_threshold**: 2.0 (in "contract-equivalent flow units"). OFI is
in the same units as size; a threshold of 2 contracts requires net
adverse flow of at least 2 contracts in the window before the gate
fires. Matches the aggressor-flow-gate default so the family of flow
gates can be compared on equal footing in follow-up iterations.

**Thin-book guard**: inherited at min_total_size=2.0 — skips updating
OFI when total top-of-book size at either side is below 2 contracts
(the level is too thin to trust the depth read).

**Window prune**: at every quote tick AND at every order decision
time. The deque is keyed by ts_event_ns; we evict from the left while
the head's timestamp is older than (now_ns - window_ns), using the
order's `ts_init` (or the latest quote tick's `ts_event` for the
update path) as `now`. No look-ahead: order's ts_init is strictly the
time the strategy submitted the order; only quote events with
ts_event <= ts_init are in the deque.

**Quote subscription**: subscribe_quote_ticks on first order of an
instrument, exactly like the iter-1 and iter-2 algos. The position
cap=1 OOM hazard from research/NOTES.md 2026-03-19 may reproduce on
this algo too — we will observe and report per the honesty rules
rather than retry.

**No look-ahead bias**: OFI computed only from quote events delivered
by the engine before the order's ts_init. The deque pruning uses the
order's ts_init at decision time, never a future timestamp. EMA-style
smoothing not added — keep this iteration to a single mechanism
change.

**Concerns**:
- The 2026-03-19 OOM hazard noted in research/NOTES.md is shared by
  all `subscribe_quote_ticks` algorithms in this family. If this algo
  also OOMs on that partition, aggregate 11 of 12 dates and disclose
  (same protocol as iter 1 and iter 2).
- Effective contribution of the OFI gate atop position_cap=1 may
  again be small in absolute pnl terms (the positional gate is the
  dominant variance reducer). The honest expected outcome is: PASS vs
  baseline (gate is wide open), but refinement-axis deltas vs iter-2
  modest, similar magnitude to iter-2's +3.65% pnl. The structural
  change is still worth running because OFI is a fundamentally
  different signal class — even a modest delta with a different
  signal class informs future iterations more than another smoothing
  of the same imbalance signal would have.

---

## Backtest Observations

**Aggregated across 11 of 12 configured train dates** (20260308-20260318,
20260320; **2026-03-19 EXCLUDED** — same Rust/Nautilus OOM hazard that
hit iter-1 (position-tier-imbalance-gate) and iter-2
(position-tier-imbalance-ema-gate); see research/NOTES.md 2026-05-23
DATA ISSUE entry. The OFI gate's quote-subscription pattern is shared
with that family, and the partition is the trigger, not the algo
variant. Honesty rule §8: report what was aggregated, not what was
configured).

**Raw aggregate (11 dates)**:
- position-tier-ofi-gate: realized_pnl $2201.75, trade_count 56305,
  sharpe 11.89, win_rate 36.43%, mean_slippage 0.0,
  max_drawdown -1.25%, is_weighted_bps 0.0456.
- simple baseline (same 11 dates): realized_pnl $43.25,
  trade_count 111489, sharpe 0.17, win_rate 35.02%,
  mean_slippage 0.0, max_drawdown -5.29%, is_weighted_bps 0.0427.

**vs baseline**: pnl_delta = +4990.75%, far above the +5.0% PASS gate.
Slippage delta = 0.0% (both sides 0.0 — zero-cost fill model per
research/NOTES.md 2026-04-30). is_weighted_bps delta = +6.88%.
Trade-count drop: 49.5% (56305 vs 111489). Win-rate lift: +1.4pp.
Verdict vs baseline: **PASS**.

**vs prior (iter-2 position-tier-imbalance-ema-gate)**: pnl REGRESSION
of -51.11% ($2201.75 vs $4503.25); trade_count -9.5% (56305 vs 62220);
sharpe regression of -8.90 (11.89 vs 20.79); win-rate -2.86pp
(36.43% vs 39.29%); max_drawdown improved by +0.05pp (-1.25% vs -1.21%).
The OFI gate is **structurally worse** than the static/EMA imbalance
gate within this position_cap=1 stack on this train window. It does
NOT meet any of the refinement-axis targets in config.yaml→refinement.

**Interpretation (no spin)**:
1. OFI is sound microstructure theory but on this oracle strategy +
   intraday fill model, it filters too aggressively in the wrong
   direction relative to the static imbalance read. Possible causes
   (not verified, listed in declining priority for any follow-up):
   (a) the 10s window aliases with the 30s oracle horizon — the
   filter blocks entries during exactly the flow regimes the oracle is
   trying to fade; (b) flow_threshold=2.0 contracts is calibrated for
   the aggressor-flow-gate's trade-tape signal, not for quote-tick OFI
   which accumulates faster and reaches |2| in a noisier regime;
   (c) MES is thin top-of-book — most ticks contribute 0 or 1 to OFI
   and the deque is dominated by 1-2 events, so the "flow" reading is
   barely smoother than a single-tick view.
2. The hypothesis stated this might be a modest delta (similar
   magnitude to iter-2's +3.65%); the realized outcome is a sizeable
   regression instead. Honestly noted: the structural signal-class
   change was the right experiment to run, the answer is negative
   on this train window.
3. Iter-2's own takeaway — that refining the imbalance read further is
   exhausted — is reinforced. Future iterations should explore
   gates that operate on a DIFFERENT order/decision axis (e.g.
   sizing rather than skip/submit, or exit-side gates rather than
   entry-only), not another entry-side signal swap.

**Trade-count flag**: trades=56305 — HIGH, not low-count flagged.
Sharpe and win_rate are reliable at this N.

**Verdict**: PASS vs baseline gate (delta +4990% >> +5% gate, no
slippage regression). FAIL as a refinement of iter-2 on every
refinement axis except max_drawdown_pct (which improves by only
+0.05pp, below the -1.0pp target). Recorded with explicit refinement
regression — do NOT snapshot as an improvement over iter-2.

Config: sigma=6, seed=42, horizon=30s; position_cap=1,
flow_threshold=2.0, window_seconds=10.0, min_total_size=2.0.
