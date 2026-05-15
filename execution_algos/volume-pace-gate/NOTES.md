# Algorithm Notes: volume-pace-gate

## Hypothesis

**Mechanism**: Volume-time pacing for entry gating. Maintain a running counter
of total contracts traded (from the TradeTick / on_trade_tick() stream) since
the most recent executed open-leg order. Skip a new open-leg order if fewer
than V contracts have traded since the last open execution; once V contracts
have been observed, the next open order executes normally and the counter
resets. Reduce-only / position-closing orders always execute and do NOT reset
the counter (they are not new entries).

**Inefficiency exploited**: The oracle strategy fires signals at a fixed
1-second wall-clock cadence. Signals that arrive during low-volume intervals
(thin book, thin flow) carry less reliable price information and likely face
larger adverse selection costs. The simple baseline and cooldown-entry-gate
use wall-clock time, but the actual market liquidity regime is better measured
in event-time (cumulative contracts traded). Under heavy trading, V contracts
accumulate in < 1 second and entries fire frequently. During dead intervals
(early morning, midday lull, pre-close), V contracts take much longer to
accumulate, so entries are deferred until the market is genuinely active.

**Why it survives costs**: The mechanism directly targets the activity regime:
high-volume periods = active/liquid market = lower adverse selection; low-volume
periods = thin/slow market = higher adverse selection. Since slippage in the
zero-fill-cost model is 0 regardless, the benefit comes from higher trade P&L
per execution by concentrating entries in more favourable activity regimes.

**Builds on**: none — original hypothesis. Distinguished from cooldown-entry-gate
(wall-clock time) and aggressor-flow-gate (signed net directional flow) by
conditioning on scalar total traded volume (event-time progress), not on clock
time or flow direction.

**Alternatives considered**:
- Wall-clock cooldown (cooldown-entry-gate, 3s): already exists; uses clock time
  not activity level
- Signed aggressor flow gating (aggressor-flow-gate): conditions on direction of
  flow, not on volume magnitude; orthogonal axis
- Order book imbalance gating: conditions on resting-book imbalance, not activity
- A per-second volume EWM threshold: considered, but adds a lookback normalization
  parameter; the raw count is simpler and equally principled

## Calibration note (from EDA on 20260308)

Data: MBP1Msg with Action.TRADE from glbx-mdp3-market-data v1.0.0, date=20260308.
- Total trade records: 81,189 over ~7,200 seconds (2-hour session)
- Total volume: 151,542 contracts
- Average contracts/second: ~21.0
- Median inter-trade time: ~0.002s (sub-millisecond clustering)
- Most common trade size: 1 contract (54,991/81,189 = 67.7%)

Threshold selection:
- V=50 contracts ≈ ~2.4 seconds of average activity
- This is faster than cooldown-entry-gate's 3-second wall clock during normal trading
  but much slower during thin/quiet periods
- Chosen to be meaningfully different from wall-clock cooldown

---

## Implementation Decisions

- Volume counter tracks total unsigned contracts traded (both sides) since last executed
  open. Not directional — we measure activity level, not direction.
- Counter reset only on actual open-leg submission (not on skips, not on closes).
- Reduce-only orders always execute immediately (intraday_flat compliance).
- First open of a session executes unconditionally (no prior open to reset from).
- `on_trade_tick()` subscription obtained via `subscribe_trade_ticks()` on first
  order event — same pattern as aggressor-flow-gate.
- No quote tick subscription needed (not using book state).
- Vol counter is a simple int accumulator; no windowing/decay needed (we want
  total activity since last entry, not recent rate).
- Threshold V=50 contracts (default) — chosen from EDA, can be tuned.

**Concerns**:
- No look-ahead bias: counter only includes trades with ts_event <= order.ts_init
  (Nautilus replay is strictly chronological; on_trade_tick fires before on_order
  for events with the same or earlier timestamp).
- The counter grows unbounded during long skip periods — this is intentional and
  correct: a long pause in the signal means the next open that fires will always
  pass (since vol >> V), which is the desired semantics.
- If `on_trade_tick()` fires after `on_order()` for the same tick event (ordering
  ambiguity), the current tick's volume is NOT included in the counter at decision
  time. This is conservative (slightly under-counts) but avoids look-ahead.

---

## Backtest Observations

**Train window**: 20260308 – 20260320, 12 dates (20260314 and 20260321 have
no data in the partition cache and were excluded consistently with other
algorithms in the database).

**Aggregate results (12 dates)**:
- Algo realized_pnl: $1878.75 / 65,839 trades
- Baseline realized_pnl: $1984.00 / 132,536 trades
- vs_baseline_pnl_pct: -5.30% (FAIL — below +5% gate AND below close margin +3%)
- Sharpe (mean): 1.6901 vs baseline 0.9086 (+86%)
- Win rate: 36.83% vs baseline 35.57% (+1.26pp)
- Max drawdown: -0.0149% vs baseline -0.0377% (improved 60%)
- Trade reduction: 50.3% (66,697 fewer trades)
- Mean slippage: 0.0 (both, zero fill-cost model)
- is_weighted_bps: 0.0413 vs baseline 0.0375 (+0.0038, slightly worse IS)

**Per-date results (key dates)**:
- 20260308: algo $83.50 / 50 trades vs base $140.50 / 351 — trade reduction 85.8%
- 20260309: algo $252.00 / 363 trades vs base $867.75 / 2863 — 87.3% reduction
- 20260310: algo $117.00 / 264 trades vs base $578.50 / 2308 — 88.6% reduction
- 20260312: algo $170.25 / 805 trades vs base $-13.25 / 5484 — turned loser profitable
- 20260313: algo $128.75 / 1496 trades vs base $-327.75 / 8210 — turned loser profitable
- 20260316: algo $-89.00 / 10254 trades vs base $-355.00 / 20211 — reduced loss
- 20260319: algo $418.50 / 14746 trades vs base $284.75 / 24319 — BEAT baseline
- 20260320: algo $407.75 / 12997 trades vs base $306.75 / 21876 — BEAT baseline

**What drove improvement**: Volume pacing correctly identifies low-activity
regimes and defers entries — the algo wins 36.8% vs 35.6% baseline (+1.3pp),
and the per-trade P&L is consistently higher (e.g., $1.67/trade vs $0.40 on
20260308). On days with noisy oracle signals (20260312-20260313), the algo
avoids the worst trades and stays positive while baseline goes deeply negative.
Sharpe nearly doubles vs baseline (1.69 vs 0.91).

**What underperformed**: The trade reduction is too aggressive on early-session
dates (20260308-20260311) where the oracle fires many signals but accumulated
volume is low. On these days, the V=50 threshold gates ~85-88% of entries —
far beyond what's needed — causing the total P&L to lag the baseline even
though quality per trade is higher. The fundamental issue: on low-signal-rate
days, the oracle's profitable trades are already sparse; removing 85% of them
means missing most of the P&L. The volume accumulation rate (~21 contracts/s)
was calibrated on session-average data, but early-session and low-liquidity
periods have much lower rates.

**Hypothesis verdict**: Partially confirmed. Event-time pacing does improve
per-trade quality (higher PnL/trade, better win rate, sharpe improvement). BUT
the total P&L is lower because the V=50 threshold is calibrated to session-wide
average volume and becomes too restrictive on low-volume days and early session
hours. The core hypothesis (activity-gated entries improve trade selection) is
supported; the implementation parameter (V=50 flat threshold) needs adaptation.

**Suggested next attempt**: Use a RATE-ADAPTIVE threshold. Instead of counting
absolute volume since last open, compute the observed volume rate (contracts/s)
over the last N seconds. Skip if the rate falls below some percentile of the
day's observed rate. Alternatively, try a much smaller fixed threshold
(V=10-15 contracts) which is less aggressive about gating on low-volume days.
Or combine volume threshold with time-based maximum skip duration: "skip unless
V contracts traded OR 10 seconds elapsed" to cap the maximum skip delay.
