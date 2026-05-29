# Algorithm Notes: ptg-f-l1

Per-iteration experiment — base_algo `position-tier-gate`, context mode
`full-trace`, loop 1 (first loop of the arm). Starting point: `position-tier-gate`
base algo.

## Hypothesis

**Context available (full-trace, loop 1)**: no prior loops — context_chars_in = 0.
Starting directly from the base algorithm.

**Mechanism**: The base algorithm (`position-tier-gate`) uses `position_cap=1`,
which completely serializes entry: any open position blocks the next open leg.
The oracle fires at 1-second intervals and can issue multiple same-direction signals
before a position closes. With cap=1, all but the first entry of any directional
run are skipped entirely. Loop 1 explores whether allowing one additional concurrent
position (`position_cap=2`) captures more of the oracle's directional signal when
the oracle is confident (firing multiple times in the same direction).

**Inefficiency exploited**: The base algo's cap=1 may be overly conservative —
if the oracle fires 3 same-direction signals in 3 seconds, cap=1 executes only
the first. The 2nd signal may carry valid directional information that is discarded.
At position_cap=2, the second consecutive same-direction entry is allowed; the third
is still blocked. This is a conservative loosening that preserves most of the
position-management benefit while capturing more of the oracle's multi-signal runs.

**Why it survives costs**: The zero-slippage model means execution cost is zero.
The key risk is that additional concurrent entries compound losses on adverse oracle
signals. However, the base algo's high Sharpe (17.62) and win rate (37.2%) suggest
the oracle signal is reliable at the baseline cap; a small cap increase may extend
rather than degrade performance.

**Builds on**: `position-tier-gate` base algo. Single change: `position_cap` 1 → 2.

**Alternatives considered**:
- `position_cap=0` (submit all opens unconditionally): approaches simple baseline behavior; degrades performance.
- Asymmetric cap (buy/sell different): more complex; deferred until loop 1 establishes the cap sweep's direction.
- Time-in-position filter: add a minimum hold time before re-entry; orthogonal mechanism, deferred.

---

## Implementation Decisions

- **`position_cap` = 2**: single behavioural change. Structure unchanged from base algo.
- **No look-ahead**: `self.cache` at `on_order()` reflects pre-fill state (strictly past).
- **Quantity invariant preserved**: orders are submitted or skipped whole; `order.quantity` never touched.

**Concerns**: position_cap=2 doubles the maximum concurrent exposure vs base. If the
oracle is wrong on consecutive signals, losses compound. However, the oracle's high
base Sharpe (17.62) suggests signal quality is sufficient to tolerate modest cap increase.

---

## Backtest Observations

**Full 12-date train window (2026-03-08 through 2026-03-20):**

| Metric | ptg-f-l1 (cap=2) | base (cap=1) | simple |
|---|---|---|---|
| realized_pnl | $156.00 | $4,262.50 | $156.00 |
| vs_base_pnl_pct | **-96.34%** | — | — |
| sharpe_ratio | 0.600 | 17.619 | 0.600 |
| trade_count | 136,734 | 90,433 | 136,734 |
| win_rate | 35.06% | 37.20% | 35.06% |

**What drove failure**: position_cap=2 is **byte-identical to the simple baseline**.
The oracle fires simultaneous CLOSE+OPEN. When the OPEN arrives, the cache shows
1 existing open position (the one closing, not yet processed). With cap=2, the check
`net_qty (=1) >= cap (=2)` is False, so every OPEN submits unconditionally. This makes
cap=2 equivalent to no gate at all — identical to the simple algo.

**What this teaches**: The position_cap lever is binary for this oracle+MES combination.
cap=1 = serialized entry (best). cap>=2 = simple baseline (worst). There is no gradual
tradeoff — the gate either fires on every concurrent OPEN (cap=1) or never (cap>=1 with
simultaneous CLOSE+OPEN). The oracle's simultaneous-signal structure makes any cap >= 2
a no-op.

**Hypothesis verdict**: FALSIFIED. cap=2 was expected to allow controlled concurrent
exposure; instead it disabled the gate entirely.

**Suggested next attempt**: Since the position_cap lever is binary (1 = best, >=2 = worst),
loop 2 should explore a different mechanism layered ON TOP of the existing cap=1 gate.
Candidates: (a) loss-streak gate — skip re-entry after N consecutive losing closes;
(b) flow-aware combination — only submit when position is flat AND flow is favorable;
(c) time-since-last-close minimum cooldown distinct from cap mechanics.
