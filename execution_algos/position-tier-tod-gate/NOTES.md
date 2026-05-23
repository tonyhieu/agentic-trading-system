# position-tier-tod-gate (iter-7)

## Hypothesis

Iters 2-6 of this family cluster pnl in $4377-$4503 (≤2.9% spread on N=11), with
five PASS algos all sitting in this narrow band irrespective of which upstream
signal (single-tick imbalance / EMA imbalance / OFI / sym-vol / dir-vol) is
layered on the inherited `position_cap=1` + reduce-only-fast-path stack. The
gate-axis gradient is exhausted; the binding constraint is structural, not
signal-class.

Iter-6 explicitly recommended either (a) time-of-day filter or (b) reduce-only
ladder as the next structurally different mechanism. This iteration probes
(a) because it has the smallest code delta and gives a clean, falsifiable
answer to the structural question: "is the binding constraint actually
intraday-uniform, or is there a session-time axis of unrealised edge?"

**Mechanism**: Inherit iter-2 best (`position-tier-imbalance-ema-gate`)
verbatim and add ONE new gate on OPEN-leg orders: skip when the order
`ts_init` falls inside either

  * the first 30 minutes after the cash-equity session open
    (13:30 UTC ≡ 09:30 ET DST), or
  * the last 30 minutes before the cash-equity session close
    (20:00 UTC ≡ 16:00 ET DST).

Reduce-only orders are NEVER touched by the TOD gate (intraday_flat
compliance: the algorithm must always permit the strategy to close
positions).

**Default justification (not optimised on the train set)**:
30-minute open/close windows are standard ES microstructure literature
defaults (Easley/Lopez-de-Prado VPIN; Bouchaud/Bonart/Donier). I am NOT
sweeping the window length on the train window — the value is picked
once from literature and committed.

**Why structurally different from iters 1-6**: every prior iteration's
gates fire on book-state at decision time (microstructure read at the
quote level). The TOD gate fires on calendar/wall-clock alone and is
orthogonal to the entire book-signal axis the family has been
exploring.

**Falsification path**: if pnl falls (or is unchanged) after the TOD
filter is added on top of iter-2, the binding constraint is genuinely
intraday-uniform within the position_cap=1 + reduce-only-fast-path
regime, and iter-8 should commit to the structurally bigger
restructure (reduce-only ladder). If pnl rises materially, the
session-time axis has unrealised edge and iter-8 can refine it
(asymmetric open vs close skip; finer window).

## Implementation Decisions

- `order.ts_init` (nanoseconds since UNIX epoch) is used as the wall-
  clock reference. `datetime.fromtimestamp(ts/1e9, tz=UTC)` converts
  to UTC HH:MM for the gate decision.
- DST: train window 2026-03-08 .. 2026-03-21 is fully on US EDT
  (DST starts 2026-03-08). 09:30 ET = 13:30 UTC and 16:00 ET = 20:00
  UTC for every train date — no mid-window DST transition.
- The gate fires only on `is_reduce_only == False` orders. Reduce-only
  orders take the fast-path and are submitted immediately. This
  preserves the intraday_flat invariant.
- Quote-tick subscription is identical to iter-2 (no new data
  dependency); the only added per-order work is one
  `datetime.fromtimestamp` call.

## Backtest Plan

Run against the train window 2026-03-08 .. 2026-03-21 one date per
foreground Bash call via `--dates`, using `--use-cached-baseline`. The
2026-03-19 partition will likely hit the same Rust/Nautilus 8 GiB OOM
documented in `research/NOTES.md 2026-05-23` (it reproduces for every
subscribe_quote_ticks algo in this family); aggregate over the 11
successful dates and disclose the exclusion in the program_database
entry.

## Backtest Observations (iter-7, 11 of 12 train dates)

| metric              | iter-7 (TOD)  | iter-2 (best) | iter-6 (dir-vol) | baseline (simple) |
| ------------------- | ------------: | ------------: | ---------------: | ----------------: |
| realized_pnl        |      3,933.50 |      4,503.25 |         4,491.75 |             43.25 |
| trade_count         |        57,989 |        62,220 |           61,886 |           111,489 |
| sharpe (cross-day)  |         21.26 |         20.79 |            21.08 |              0.17 |
| win_rate            |       0.3897  |       0.3929  |          0.3934  |            0.3502 |
| max_drawdown_pct    |       -0.0121 |       -0.0121 |          -0.0121 |           -0.0529 |
| vs baseline pnl_pct |     +8994.80% |    +10312.14% |       +10285.55% |               n/a |

**Verdict vs baseline**: PASS (+8994.80% >> +5.0% gate).

**Refinement axes vs iter-2 (family-best)**:
- pnl_delta_pct: -12.65% — MISSES min_pnl_delta_pct=+2.0 (REGRESSION)
- sharpe_delta:  +0.47   — MISSES min_sharpe_delta=+0.5 (just under)
- winrate_delta_pp: -0.32 — MISSES min_winrate_delta_pp=+2.0
- mdd_delta_pp:  ~0.00  — MISSES min_mdd_delta_pp=-1.0
- trade_count_delta_pct: -6.80% (TOD gate removed ~4.2k entries vs iter-2)

**Honest read**: the TOD gate, layered on iter-2, removes roughly 4,200
OPEN-leg entries that fall inside the open-30min and close-30min windows.
These removed entries were NET POSITIVE on this train window: pnl dropped
by ~$570 while trade count fell by ~6.8%. Sharpe ticked up only because
variance dropped by more than mean — not a structural win.

**Falsification result** (per the hypothesis section above): the binding
constraint of this family IS essentially intraday-uniform within the
position_cap=1 + reduce-only-fast-path regime. The cash-equity open and
close are NOT systematically adverse periods inside this gate stack on
this train window. The position-tier gate is doing the heavy lifting at
both ends of the day just as well as during the cash-equity-quiet
session middle; the +30min open and -30min close windows contain no
unrealised edge that a wall-clock skip can recover.

**Structural takeaway for iter-8**:
- Five gate-axis variations (iter-2 EMA imbalance, iter-3 OFI, iter-5
  sym-vol, iter-6 dir-vol) and now one calendar-axis variation (iter-7
  TOD) all cluster pnl below or near iter-2 ($3933-$4503 across N=11).
  The DECISION-TIME entry-side gate axis is fully exhausted.
- The remaining unexplored mechanism is the *exit-side*: how the
  reduce-only fast-path itself behaves. Today every reduce-only is
  submitted immediately. A reduce-only ladder (defer the close for up
  to K ticks while the book lean still favours the position; close
  immediately on adverse lean) would change the structural shape of
  exits without touching the entry gates at all. That is iter-8's
  candidate.

**Disclosure**:
- N=11 of 12 configured train dates: 2026-03-19 EXCLUDED (subscribe_quote_ticks
  Rust/Nautilus 8 GiB OOM reproduces here exactly as documented in
  `research/NOTES.md 2026-05-23`; verified by an explicit retry this
  iteration).
- Slippage is 0.0 by construction (zero-cost fill model — see
  `research/NOTES.md 2026-04-30`); the slippage gate is uninformative.
- Trade counts are HIGH (57k+), not low-trade-count flagged.
- Verdict robust to the missing 03-19 date: even attributing 0 algo pnl
  on that day while baseline keeps its 03-19 pnl (112.75), vs-baseline
  remains in the +2000% region — well above the +5% gate.

