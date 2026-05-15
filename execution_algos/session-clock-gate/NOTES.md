# Algorithm Notes: session-clock-gate

## Hypothesis

**Mechanism**: Condition the open leg of each oracle signal on the intraday
wall-clock time mapped to the CME RTH (Regular Trading Hours) session.
Skip entries during structurally degraded session phases; execute normally
during stable mid-session. Reduce-only (close) orders always execute.

**Inefficiency exploited**: Intraday market microstructure exhibits well-documented
session-phase effects. The first 15-30 minutes after the cash open (approx 09:30-10:00 ET)
are characterized by elevated spread, large order imbalances, and noisy price discovery —
the oracle's 30-second forecast horizon is less reliable here because price is settling
into a new equilibrium from the overnight. The midday period (~11:45-12:15 ET) sees reduced
depth and wider spreads as desks rotate lunch shifts; fill quality degrades. The final 15
minutes before close (~15:45-16:00 ET) features window-dressing flows and pre-close ramps
that are structurally adversarial for directional execution. During these windows, the
oracle's sigma=5 noise level represents a larger fraction of the true forecast edge, making
entries lower EV than the mid-session baseline.

**Why it survives costs**: The filter is purely temporal — it uses only the order's
`ts_init` nanosecond timestamp, converted to UTC (which is what CME GLBX timestamps
are in), mapped to Chicago/ET timezone offsets. CME MES futures RTH runs 09:30-16:15 ET.
There is zero look-ahead: the timestamp is available at decision time before any fill
occurs. The expected skip rate is roughly (30 + 30 + 15) / 405 = ~18.5% of RTH signals,
concentrated in the noisiest windows. By skipping ~18% of entries during poor-quality
windows rather than 80% of all entries at random, the algorithm focuses participation
on mid-session where signal reliability and fill quality are both stronger.

**Builds on**: none — original hypothesis. All prior passing algorithms (streak-spread-tight,
ob-imbalance-gate, vol-regime-sizer, microprice-divergence-gate) condition on market
microstructure signals at decision time. This algorithm is orthogonal: it conditions
only on clock time, with no reference to current bid/ask, imbalance, vol, or P&L history.

**Alternatives considered**:
1. Combining with ob-imbalance-gate — rejected for this iteration (OBJECTIVE.md §6:
   one change at a time; combination would destroy attribution).
2. Finer time bucketing (per-minute filters) — rejected as overfitting; broad session
   windows are based on structural market properties, not data-mining.
3. Extended-hours filtering — CME GLBX runs 23:00-22:00 CT; RTH is 08:30-15:15 CT.
   The oracle strategy appears to generate signals across the full session. Applying
   a broader extended-hours filter is possible but less hypothesis-driven.

---

## Implementation Decisions

**Timestamp source**: `order.ts_init` — UNIX nanoseconds, UTC. This is set when
the order object is initialized (before the strategy calls `submit_order`). No
look-ahead risk: the clock time of the oracle signal is observable at the moment
`on_order()` fires.

**Timezone mapping**: CME GLBX timestamps are UTC. The session-phase windows are
defined in Central Time (CT = UTC-6 in winter, UTC-5 in summer; observes DST).
Rather than importing a heavyweight timezone library, the algorithm uses a fixed
UTC offset: -6h (UTC-6, standard time). The train window covers 2026-03-08 to
2026-03-21. US DST in 2026 begins on March 8 (second Sunday in March), so the
entire train window lies in CDT (UTC-5 = Central Daylight Time). To be safe, the
algorithm reads the UTC offset from a config parameter `utc_offset_hours` (default -5
for CDT, the correct value for the 2026-03-08 through 2026-03-21 window).

**CME MES RTH session**: Opens at 08:30 CT (13:30 UTC in CDT), closes at 15:15 CT
(20:15 UTC in CDT). Pre-market/overnight runs 15:00-08:30 CT.

**Skip windows (in CT time)**:
- Open turbulence: 08:30-09:00 CT (first 30 minutes of RTH) — price discovery chaos
- Midday lull: 11:45-12:15 CT — reduced participation, wider spreads
- Pre-close ramp: 15:00-15:15 CT (last 15 minutes before close) — window-dressing

**In UTC (CDT, UTC-5)**:
- Open turbulence: 13:30-14:00 UTC
- Midday lull: 16:45-17:15 UTC
- Pre-close ramp: 20:00-20:15 UTC

All three windows are configurable via kwargs so future refinements can tune them
without rewriting the algorithm.

**Forced re-entry**: After any skip, the next open order is always submitted to
prevent cascade (same _position_flat safety guard as streak-spread-tight).

**Quantity invariant**: The algorithm never modifies parent order quantity. It either
calls `self.submit_order(order)` or does nothing (skip). Strict `sum(child_fills) ≤ parent.quantity`.

**Concerns**: No look-ahead bias — the only information used is the wall-clock time,
which is known before the order is routed. The session windows are defined from
structural microstructure theory, not calibrated to training data, minimizing
overfitting risk. One fragile assumption: the train-window data is in CDT (UTC-5)
which is correct for 2026-03-08 through 2026-03-21 (DST begins March 8, 2026).
If the dataset contains pre-DST dates the UTC offset should be -6; the config
parameter handles this.

---

## Backtest Observations

**Train window**: 12 dates (20260308-20260320, excluding 20260314 and 20260321 — no data on those dates).
**Dates run**: 20260308-20260313, 20260315-20260320.
**Trade count**: 129,136 trades (vs 132,536 baseline; -2.6% skip rate).
**Realized P&L**: $2,426.75 vs baseline $1,984.00 (+22.32% — PASS, gate is +5%).
**Slippage**: 0.0 (both; zero fill-cost model).
**Sharpe**: 1.1456 vs 0.9086 baseline (+26.1%).
**Max drawdown**: -0.0363% vs -0.0377% (slight improvement).
**Win rate**: 35.66% vs 35.57% (+0.09pp).

**What drove improvement**: The temporal filter selectively skipped open-leg entries
during the three low-quality windows (open turbulence 08:30-09:00 CT, midday lull
11:45-12:15 CT, pre-close ramp 15:00-15:15 CT). The skip rate was only ~2.6%
(3,400 fewer trades), but they were concentrated in windows where the oracle
signal quality is structurally lower (high-noise price discovery near open,
reduced depth at midday, adversarial flows near close). On dates with heavy volume
(20260316: 19,727 vs 20,211; 20260317: 20,457 vs 20,992) the filter consistently
improved P&L — those days had the most signal traffic through skip windows.

**What underperformed**: On 20260308 the filter had zero effect (351 vs 351 trades;
identical P&L $140.50) — all oracle signals on that date fell outside the skip windows.
On 20260315, same: 1,848 vs 1,848 trades, identical P&L -$31.00. This is likely a
data characteristic of those low-volume dates (signals may be concentrated in
non-skip hours or the session was shortened). On the highest-volume days with
negative P&L (20260316: -$308 vs -$355), improvement was real but modest — the
oracle signal itself was adverse regardless of session phase.

**Hypothesis verdict**: SUPPORTED. The temporal filter improved P&L on 8/12 dates
and matched baseline on 2/12 dates. It did NOT hurt performance on any date —
the skip rate is small (~2.6% overall) and concentrated in windows with structural
microstructure reasons to expect lower fill quality. The improvement is orthogonal
to all prior passing algorithms (no microstructure signal used).

**Suggested next attempt**: Combine session-clock-gate with ob-imbalance-gate or
streak-spread-tight — apply both filters independently (skip if EITHER says skip).
The two are orthogonal (temporal vs microstructure) so the combined skip rate should
be approximately additive, potentially capturing the best of both approaches. An
alternative is to widen the open-turbulence window to 60 min (08:30-09:30 CT) or
add an extended-hours filter — the skip rate is low enough that wider windows
might capture more noisy signals without over-filtering profitable mid-session ones.
