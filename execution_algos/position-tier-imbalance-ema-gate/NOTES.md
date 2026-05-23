# Algorithm Notes: position-tier-imbalance-ema-gate

## Hypothesis

**Builds on**: `position-tier-imbalance-gate` (iter 1 PASS: pnl=4344.50,
sharpe=21.27, win_rate=39.2%, trade_count=62251, vs_baseline_pnl_pct=+9945%
over 11 of 12 train dates; 20260319 excluded due to known Nautilus 8-GiB
Rust OOM — see research/NOTES.md 2026-05-23).

**Mechanism**: Replace the **single-tick** top-of-book imbalance read with
an **exponentially-weighted moving-average (EMA) imbalance** computed on
the most recent quote ticks. All other gates (positional cap = 1,
reduce-only fast-path, thin-book guard `min_total_size = 2`) remain
verbatim.

Concretely, the imbalance gate becomes:

```
imbalance_t = bid_size_t / (bid_size_t + ask_size_t)         in [0,1]
ema_t       = alpha * imbalance_t + (1 - alpha) * ema_{t-1}   (alpha=0.30)

BUY  order: SKIP when ema_t < skip_threshold        (asks dominate)
SELL order: SKIP when ema_t > 1 - skip_threshold    (bids dominate)
```

With `alpha = 0.30`, the EMA's effective half-life is
`log(0.5)/log(0.70) ≈ 1.94` ticks; the equivalent simple-moving-average
window is `(2/alpha) - 1 ≈ 5.67` ticks. So the gate looks at roughly the
last 6 quotes worth of book pressure, smoothed.

**Inefficiency exploited**: Single-tick top-of-book imbalance is noisy at
the quote-by-quote level: bid_size and ask_size can flicker by ±1
contract between adjacent ticks even when the underlying pressure is
stable. The prior algorithm's threshold (0.40) was deliberately moderate
to avoid over-skipping on these flickers — but that moderation came at
the cost of letting some clearly-adverse setups slip through. Smoothing
the imbalance signal with a short-horizon EMA should:

  1. Suppress single-tick noise — fewer false-positive skips on flickery
     books that quickly mean-revert.
  2. Make the **persistent** book lean (the real Lipton predictor) the
     gate's input. The Lipton paper and Kolm/Turiel/Westray both note
     that the alpha horizon of order-flow / book signals is on the order
     of "two price changes" — i.e., not a single tick. Smoothing 5-6
     ticks brings the gate's read closer to that natural horizon.
  3. Preferentially skip entries during persistent adverse-lean episodes
     (more reliably losing) and pass entries during transient-flicker
     episodes (more likely random / breakeven).

The expected effect on metrics: win_rate should rise (better-selected
trades), trade_count may shift slightly in either direction (EMA both
filters out some "luck-of-the-tick" passes and admits some "luck-of-the-
tick" rejections), and realized_pnl should be at least non-regressive
and ideally improve modestly.

**Refinement targets** (from config.yaml § refinement, vs prior algo):
  - `min_sharpe_delta`: +0.5 absolute
  - `min_pnl_delta_pct`: +2.0 pp
  - `max_slippage_delta_pct`: ≤ -1.0 (improvement; slippage is 0/0 today)
  - `min_winrate_delta_pp`: +2.0 pp
  - `min_mdd_delta_pp`: ≤ -1.0 (improvement)

This iteration aims for the win_rate target most directly; sharpe and
pnl deltas follow from the win_rate lift. Slippage axis is moot under
the zero-fill-cost model (research/NOTES.md 2026-04-30 DATA ISSUE).

**Alternatives considered**:
- *Longer EMA window (alpha=0.10, ~19 ticks)*: too slow — the Kolm
  result on alpha decay (~2 price changes) suggests very-long smoothing
  loses the signal. Pick a window short enough to still be responsive.
- *Multi-level (L2) order-book imbalance*: not available — the data
  pipeline currently surfaces only top-of-book quote ticks. A future
  iteration could pull MBP-10 if the operator approves the data path.
- *Order-flow imbalance (OFI) instead of book imbalance*: stronger
  signal per Kolm, but requires tracking deltas across consecutive
  quotes (queue depletion / replenishment events). One-step
  refinement over the single-tick read is the smaller, safer change;
  saving OFI for a follow-up iteration.
- *Lower threshold (0.35)*: that would compound with EMA smoothing —
  too many simultaneous changes. Keep threshold = 0.40, vary only the
  smoothing.
- *Adaptive threshold tied to spread*: out of scope here; introduces
  another tunable.

---

## Implementation Decisions

- `position_cap = 1` — inherited verbatim from prior algo. The
  cascade-protection edge is non-negotiable.
- `skip_threshold = 0.40` — inherited verbatim. Vary only ONE thing per
  iteration (the smoothing).
- `min_total_size = 2.0` — inherited verbatim.
- `ema_alpha = 0.30` — chosen for ~6-tick equivalent window, matching the
  Kolm "two price changes" alpha horizon when ticks come at sub-second
  cadence and prices change every few ticks.
- EMA state is **per-instrument**, stored in `self._ema_imbalance` dict.
- EMA initialization: on the FIRST eligible quote (after `min_total_size`
  is met), seed `ema_imbalance = imbalance_t` (no warm-up artifact).
- EMA update happens on every quote tick that satisfies `min_total_size`,
  via `on_quote_tick()`. We deliberately update from the QUOTE STREAM,
  not from order-arrival times — this lets the EMA carry information
  between orders, which is the whole point of a short-horizon smoother.
- On a thin-book tick (total < min_total_size), we **do not update** the
  EMA — the imbalance reading is too noisy to contribute. This means the
  EMA effectively pauses during thin-book episodes and resumes from the
  last meaningful value.
- At decision time (`on_order()`), we use the **current** `self._ema_imbalance`
  value if it has been seeded; otherwise we fall through to the same
  neutral behavior as the prior algo (no skip).
- Subscribe to quote ticks via `_ensure_subscribed()` on first order,
  same as prior algo. We expect the same OOM on 2026-03-19 (since the
  trigger is the quote-subscription path on that partition).
- No look-ahead: `on_quote_tick(tick)` is called as the engine processes
  each quote in chronological order. At `on_order()` time, the EMA
  reflects only quotes already processed — strictly past relative to
  the order's `ts_init`.
- No quantity modification: every parent order is either submitted
  intact or skipped. Quantity invariant always preserved.

**Concerns**:
- *EMA seed sensitivity*: First-order behavior of an EMA depends on how
  it's seeded. By seeding with the first valid imbalance reading (no
  prior history bias) we avoid imprinting a "neutral 0.5" assumption.
- *Order-event vs quote-event ordering*: Nautilus processes events in
  ts_init order; quote ticks and orders interleave correctly so the
  EMA at `on_order()` time always reflects every prior quote.
- *Overfitting*: `alpha = 0.30` is a design choice, not tuned. We do
  NOT report a sweep over alpha here — that would be overfitting.
- *Trade-count drift*: Smoothing could reduce trade_count further (more
  consistent reads on adverse books) OR raise it (less reactive to
  spikes). Either is acceptable as long as P&L and win-rate improve.
- *Constraints*: `top_of_book_only` is engine-enforced (we never modify
  orders); `participation_cap` is moot (oracle parent size = 1
  contract); `intraday_flat` is preserved (reduce-only fast-path).

---

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-21 (12 trading days configured; 11
days successfully aggregated; 2026-03-19 reproducibly OOM-crashed
exactly as on the prior algorithm's iter 1 — see DATA ISSUE below).

| metric             |   algo (PTI-EMA-G) |  baseline (simple) |    delta_% |
| ------------------ | -----------------: | -----------------: | ---------: |
| realized_pnl       |           4503.25  |              43.25 |  +10312.14 |
| sharpe_ratio       |             20.79  |               0.17 |  +11879.18 |
| max_drawdown_pct   |          -0.01210  |           -0.05290 |     +77.13 |
| win_rate           |             0.3929 |             0.3502 |     +12.21 |
| trade_count        |             62220  |             111489 |     -44.19 |
| mean_slippage      |             0.000  |              0.000 |      +0.00 |
| is_weighted_bps    |             0.0683 |             0.0427 |     +59.95 |

**Verdict (train-only, vs baseline `simple`): PASS.** delta_pnl_pct =
+10312.14 (gate ≥ 5.0); slippage flat (no regression, no information
under the zero-fill-cost model). The pass-gate criterion in §4 of
OBJECTIVE.md is decisively met.

### Comparison to prior iteration (refinement axis)

| metric             | iter 1 (PTIG) | iter 2 (this, PTI-EMA-G) |       delta |
| ------------------ | ------------: | -----------------------: | ----------: |
| realized_pnl       |      4344.50  |                 4503.25  | +158.75 (+3.65%) |
| sharpe_ratio       |        21.27  |                   20.79  |       -0.48 |
| max_drawdown_pct   |       -0.0102 |                 -0.0121  |     -0.19pp |
| win_rate           |        0.3920 |                  0.3929  |     +0.09pp |
| trade_count        |        62251  |                  62220   |   -31 (-0.05%) |
| mean_slippage      |        0.000  |                  0.000   |       +0.00 |

Against the §6 refinement targets (config.yaml refinement.*):
  - `min_sharpe_delta = +0.5`        : got **-0.48**     → MISS
  - `min_pnl_delta_pct = +2.0`       : got **+3.65%**    → meet
  - `max_slippage_delta_pct ≤ -1.0`  : got **0.0**       → MISS (moot)
  - `min_winrate_delta_pp = +2.0pp`  : got **+0.09pp**   → MISS
  - `min_mdd_delta_pp ≤ -1.0pp`      : got **-0.19pp**   → MISS

**Refinement read**: the EMA smoothing at alpha=0.30 is, in this regime,
essentially a no-op vs the single-tick imbalance gate. The reason: the
positional gate (`position_cap=1`) blocks the overwhelming majority of
the prior algorithm's would-be order events — only the flat-state opens
ever reach the imbalance gate, and on those, the single-tick and
6-tick-EMA reads are very highly correlated. Trade-count moves by 31 in
62000+ (0.05%); win_rate moves by 0.09pp. The +3.65% pnl improvement
sits inside what could plausibly be noise across an 11-date sample —
without a larger window or a stronger smoothing change we cannot
discriminate signal from noise on the refinement axis.

**Implication for future iterations**:
- The book-imbalance signal at the *quote* level has been thoroughly
  exploited within the position-cap=1 regime — incremental tweaks
  (smoothing, threshold) are unlikely to move the needle.
- The next high-leverage move is to either (a) replace the directional
  filter with a stronger signal class (order-flow imbalance per
  Cont/Kolm, aggressor-flow, queue-imbalance with depletion) OR (b)
  vary the structural gate (position_cap, reduce-only fast-path
  conditionality). The "stack one more filter on top of the cap" pattern
  is exhausting.
- The +3.65% headline pnl bump is reported as-is — it is below the
  refinement-target threshold for pnl (+2.0%) by margin but above the
  baseline-comparison gate threshold (+5.0% in pnl terms against a much
  weaker baseline). Honesty: I do NOT conclude that EMA-smoothing is a
  reliable improvement; with N=11 dates the result is noise-dominated.

### DATA ISSUE — 2026-03-19 backtest failure (reproduces from iter 1)

The 20260319 backtest reproducibly failed with the same Rust OOM in the
Nautilus backtest subprocess as on the prior iteration's
`position-tier-imbalance-gate`:

  `memory allocation of 8589934592 bytes failed`  (signal 6, SIGABRT)

This confirms the prior iteration's diagnosis (research/NOTES.md
2026-05-23 DATA ISSUE) that the OOM is specific to the interaction
between `subscribe_quote_ticks` on the 2026-03-19 partition and the
algorithm's quote-driven decision path. The EMA addition did NOT change
the symptom — the crash happens before the algorithm's `on_quote_tick`
adds any per-tick overhead. Aggregate metrics above span the 11
successful dates; per §8, the missing date is disclosed.

The same algorithm runs cleanly on every other train date (including
20260320, the next session). Cached `simple` baseline for 20260319
covers it (trades=25,245, pnl=112.75) — so the issue is algorithm-and-
partition-specific, not data-availability.

### Trade-count and win-rate stability

Trade count (62,220) is virtually identical to iter 1 (62,251) — a 31-
trade (0.05%) difference. Win rate is also virtually identical
(0.3929 vs 0.3920). This is consistent with the EMA-vs-single-tick
imbalance gates being highly correlated for short EMA windows. Trade
counts are HIGH — not low-trade-count flagged.

