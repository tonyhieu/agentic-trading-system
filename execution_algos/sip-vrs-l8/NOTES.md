# Algorithm Notes: sip-vrs-l8

Parent (per method): `vol-regime-sizer`. Method used: Propose-Audit-Falsify-Commit (`prompt-l5.md` / `.current_prompt.md`).

## Parent mechanism

`vol-regime-sizer` updates two EWMs of `|Δmid|` on every quote tick (fast halflife=20 ticks, slow halflife=120 ticks). For each OPEN parent order it computes `vol_ratio = fast_vol / slow_vol` (clipped at `max_vol_ratio=5`), maps to `p_submit = max(min_prob=0.05, exp(-sensitivity=2.0 × max(0, vol_ratio − 1)))`, and decides via deterministic SHA-256 of the `client_order_id` whether to submit or skip. Cold start (`tick_count < 30`) and undefined-baseline branches return `p=1.0`. Reduce-only orders bypass the gate. The gate measures **unsigned tick-rate turbulence** vs a longer-tick baseline; it has no notion of order side, hold duration, intraday time-of-day, spread state, recent realized pnl, or price-level drift from the session anchor.

Train dates (audit/falsification universe; 11 available — 20260319 is missing CSVs in parent results, only `metrics.json` retained):
`20260308, 20260309, 20260310, 20260311, 20260312, 20260313, 20260315, 20260316, 20260317, 20260318, 20260320`.

## Candidate weaknesses

Three substantively-different axes that have not been exercised on prior loops (signed-direction L1, close-window time-of-day L2, persistence L3, trendiness re-admit L4, wide-spread L5, round-number L6, negative-streak L7):

- **Candidate 1 — Signed local drift (into-the-move blindness)**.
  "The parent's mechanism is *unsigned* `vol_ratio` which fails in regime *adverse signed drift over the prior 30s* because the oracle, when firing against the recent trend, should incur a directional execution penalty the unsigned EWM cannot see."
  Binding feature: `signed_drift_30s = side_sign × (arrival_mid − mid_30s_ago)`.

- **Candidate 2 — Price-level drift from session-open anchor**.
  "The parent's mechanism is *anchor-free* (only ratio of fast vs slow EWM) which fails in regime *late-day prices far from session-open mid* because positions opened far from the session anchor face mean-reversion pressure the EWM ratio does not detect (EWM ratio = 1 throughout calm but anchored drifts)."
  Binding feature: `abs_drift_from_open = |arrival_mid − first_open_mid_of_session|`.

- **Candidate 3 — Recent fill velocity (signal-burst regime)**.
  "The parent's mechanism is *tick-anchored* and treats high tick-rate identically regardless of how many *oracle signals* are firing per second; it fails in regime *rapid signal bursts* because clustered oracle firings indicate strong directional conviction whose execution edge differs from quiet-period fills."
  Binding feature: `recent_velocity_10s = count of own opens in the last 10s before this order`.

## Regime audit

Per-date binding-feature distributions, n is OPEN orders (FILLED, with non-null pnl join):

### Candidate 1 audit
Binding feature: `signed_drift_30s = side_sign × (arrival_mid − mid_30s_ago)`. p10/p90 reported (scale stat).

```
Date         n     median   p10    p90
20260308   366    -0.125  -4.250  +3.375
20260309   2875   -0.250  -3.875  +3.375
20260310   2288   -0.250  -3.500  +3.125
20260311   2415   -0.125  -3.125  +2.750
20260312   5443    0.000  -2.625  +2.375
20260313   8023    0.000  -2.500  +2.375
20260315   1827    0.000  -2.000  +2.000
20260316  19204    0.000  -1.750  +1.750
20260317  19951    0.000  -1.375  +1.250
20260318  20905    0.000  -1.625  +1.500
20260320  21028    0.000  -2.000  +2.000
```
Heterogeneity verdict: **HETEROGENEOUS**. p90 ranges 1.25 to 3.375 (2.7×); thin dates carry far larger signed-drift magnitudes than dense dates. Median is bounded between [-0.25, 0] (small location heterogeneity).

### Candidate 2 audit
Binding feature: `abs_drift_from_open = |arrival_mid − first_open_mid_of_session|`. Median + p90 reported.

```
Date         n     median   p10     p90
20260308   367    81.88   73.50   90.12
20260309   2878   52.88   10.62  162.12
20260310   2290   31.88    7.12   61.00
20260311   2416   25.75    5.81   64.38
20260312   5447   21.00    4.00   42.88
20260313   8026   23.38    6.38   42.38
20260315   1832   39.25   16.25   46.50
20260316  19209   47.00   13.75   64.25
20260317  19962   21.75    8.50   36.25
20260318  20913   38.00   16.25   97.50
20260320  21032   45.12    2.88  106.38
```
Heterogeneity verdict: **HETEROGENEOUS**. Median ranges 21.00 to 81.88 (~3.9×); p90 ranges 36 to 162 (4.5×). The "drift from open" magnitude varies wildly across sessions.

### Candidate 3 audit
Binding feature: `recent_velocity_10s` (count of own opens in [t−10s, t)). Median + p90 reported.

```
Date         n   median  mean   p10   p90   frac≥5
20260308   367    0      0.60    0     2    0.000
20260309   2878   0      0.52    0     2    0.001
20260310   2290   0      0.47    0     1    0.002
20260311   2416   0      0.54    0     2    0.002
20260312   5447   1      0.88    0     2    0.004
20260313   8026   1      1.31    0     3    0.008
20260315   1832   2      2.47    1     4    0.073
20260316  19209   2      2.44    1     4    0.087
20260317  19962   2      2.51    1     4    0.094
20260318  20913   3      2.71    1     5    0.135
20260320  21032   3      2.85    1     5    0.141
```
Heterogeneity verdict: **HETEROGENEOUS**. Median ranges 0 to 3 (6×); `frac≥5` ranges 0.0% to 14.1%.

## Falsification tests

All three candidates are HETEROGENEOUS — per-date sign-consistency rule applies. Decision rule for each (stated *before* running): for each train date, define gated bucket as orders above per-date 75th-percentile of the binding feature. Compute `delta = mean_pnl(gated) − mean_pnl(other)`. SURVIVED iff `delta < 0` on **≥ 8 of 11** train dates AND no date has positive delta exceeding `2 × cross-date median|delta|`.

### Candidate 1: signed_drift_30s ≥ p75 (into-the-move) → worse pnl?

```
Date         thr     n_gated  gated_pnl  other_pnl   delta
20260308   1.500       94      +0.6835    +0.0708   +0.6127
20260309   1.500      754      +0.2633    +0.2132   +0.0500
20260310   1.375      579      +0.2660    +0.1517   +0.1143
20260311   1.312      604      +0.1159    +0.0823   +0.0336
20260312   1.125     1367      −0.0037    −0.0478   +0.0441
20260313   1.000     2206      −0.0609    −0.0560   −0.0048
20260315   1.000      510      −0.0015    −0.0347   +0.0333
20260316   0.750     5510      −0.0102    −0.0246   +0.0144
20260317   0.500     6520      −0.0040    −0.0106   +0.0066
20260318   0.750     5280      +0.0063    +0.0104   −0.0040
20260320   1.000     5258      +0.0122    +0.0111   +0.0011
```

Verdict: **FALSIFIED** | n_neg=2/11 (need ≥8); max_positive_delta=+$0.6127 vs allowance 2×median|delta|=$0.067. Direction of hypothesis is reversed — into-the-move opens are *more* profitable, not less. Margin: 6 dates short on n_neg axis; 9.2× over max_positive allowance.

### Candidate 2: abs_drift_from_open ≥ p75 → worse pnl?

```
Date          thr    n_gated  gated_pnl  other_pnl   delta
20260308    86.25      94      +0.3191    +0.2875   +0.0316
20260309    97.00     721      +0.2881    +0.2064   +0.0817
20260310    53.88     576      +0.0647    +0.2194   −0.1547
20260311    42.50     607      −0.1425    +0.1680   −0.3106
20260312    33.12    1367      −0.0443    −0.0338   −0.0105
20260313    31.38    2021      −0.0721    −0.0515   −0.0206
20260315    43.75     460      −0.0207    −0.0180   −0.0026
20260316    55.75    4810      −0.0002    −0.0272   +0.0270
20260317    28.00    5089      −0.0032    −0.0102   +0.0070
20260318    46.25    5239      +0.0170    +0.0068   +0.0102
20260320    75.62    5337      +0.0397    +0.0017   +0.0380
```

Verdict: **FALSIFIED** | n_neg=5/11 (need ≥8); max_positive_delta=+$0.0817 vs allowance 2×median|delta|=$0.054. Margin: 3 dates short on n_neg axis; 1.5× over max_positive allowance. **Smallest violation among the three candidates.**

### Candidate 3: recent_velocity_10s ≥ p75 → worse pnl?

```
Date         thr    n_gated  gated_pnl  other_pnl   delta
20260308    1.0      164      +0.6799    −0.0148   +0.6947
20260309    1.0     1099      +0.3578    +0.1460   +0.2118
20260310    1.0      804      +0.3265    +0.1014   +0.2250
20260311    1.0      946      +0.1570    +0.0469   +0.1100
20260312    1.0     3059      +0.0166    −0.1043   +0.1209
20260313    2.0     3108      −0.0352    −0.0703   +0.0352
20260315    3.0      852      −0.0273    −0.0112   −0.0161
20260316    3.0     8751      −0.0092    −0.0298   +0.0206
20260317    3.0     9512      +0.0047    −0.0203   +0.0249
20260318    4.0     6320      +0.0182    +0.0056   +0.0127
20260320    4.0     6850      +0.0244    +0.0050   +0.0194
```

Verdict: **FALSIFIED** | n_neg=1/11 (need ≥8); max_positive_delta=+$0.6947 vs allowance 2×median|delta|=$0.070. Direction is reversed — high-velocity bursts are *more* profitable. Margin: 7 dates short on n_neg axis; 9.9× over max_positive allowance.

## Verdicts (3 lines)

```
Verdict C1: FALSIFIED | n_neg=2/11 (need ≥8); max_pos +0.613 vs 2×med|Δ|=0.067; direction reversed (into-the-move opens are winners).
Verdict C2: FALSIFIED | n_neg=5/11 (need ≥8); max_pos +0.082 vs 2×med|Δ|=0.054; smallest-violation margin (3 dates short, 1.5× over).
Verdict C3: FALSIFIED | n_neg=1/11 (need ≥8); max_pos +0.695 vs 2×med|Δ|=0.070; direction reversed (high-velocity bursts are winners).
```

## Chosen hypothesis

**All three candidates were FALSIFIED.** Per Step 5 #3 (no candidate survived; pick the smallest violation margin), the chosen candidate is **C2**: gate OPEN orders whose `abs_drift_from_open` exceeds a per-date relative threshold. C2's signs are mixed (6 positive deltas, 5 negative), and the smallest-violation property is fragile — but it is the only candidate where the rule violation is bounded (1.5× over max_positive allowance vs C1/C3's ~10× violations).

**Honesty flag**: this loop is structurally weak. The audit shows the parent's gate is not blind to the axes I tested — or, more precisely, the residual edge available by gating on `abs_drift_from_open` is small (median|delta| = $0.027/contract) and not consistently signed. I do not expect this candidate to beat L5 ($1471.75 pnl, sharpe 13.72). I am implementing C2 as the method's honest output, knowing the loop will likely revert. The deeper signal in the audit is that **none of the three axes (signed drift, anchor drift, velocity) carry a robust loss-tail to skip** on the parent. This is itself a useful negative result and should bound the parent-anchored hypothesis space remaining.

**Parent behavior being changed**: parent's `_compute_submit_prob` returns `max(min_prob, exp(-sensitivity × max(0, vol_ratio − 1)))` and is anchor-free. The modification: layer an anchor-drift skip on top of the parent — when the running estimate of `abs_drift_from_open` exceeds a regime-relative threshold, multiply `parent_p_submit` by `anchor_drift_suppress` (default 0.0 = hard skip on that bucket).

**Concrete modification**:
1. On each quote tick, cache the latest mid. The *very first* observed mid in the session is captured as `session_anchor_mid`. (Falls back to the first OPEN order's `arrival_mid` if the order arrives before any quote tick.)
2. Maintain a running session-wise mean of `|mid − session_anchor_mid|` (updated on each quote tick).
3. On each OPEN order arrival:
   - Compute `parent_p_submit` exactly as the parent does.
   - Look up `current_abs_drift = |latest_mid − session_anchor_mid|` and `running_mean_abs_drift`.
   - If `current_abs_drift > k × running_mean_abs_drift` with `k = 1.5` (chosen so that ~25% of arrivals qualify — matches the p75-gated bucket size in the falsification test), multiply `parent_p_submit` by `anchor_drift_suppress = 0.0`.
   - Otherwise leave `parent_p_submit` unchanged.
4. Run the deterministic SHA-256 accept/skip draw at the (possibly suppressed) probability.

Cold-start, reduce-only bypass, the parent's vol-regime formula, `min_prob` floor, and deterministic accept/skip are preserved exactly. The wide-spread layer from sip-vrs-l5 is **NOT** included — the method requires modifying the named parent `vol-regime-sizer`, not the champion. (This is one of the contributing reasons I expect the loop to revert vs L5.)

**Expected direction vs `vol-regime-sizer`** (the named parent):
- `realized_pnl`: weakly ↑ on dates where the per-date delta was negative (20260310, 20260311, 20260312, 20260313, 20260315 — the 5 negative-delta dates) and weakly ↓ on dates 20260308, 20260309, 20260316–20260320 (6 positive-delta dates). Net: ambiguous; small in expectation. Honest baseline: pnl roughly equal to or slightly worse than parent's $753.75 → far below L5's $1471.75.
- `mean_slippage`: 0 (zero-slippage fill model).
- `sharpe_ratio`: ambiguous.
- `trade_count`: ↓ by ~12% (the regime-relative gate fires when current drift exceeds 1.5× running-mean drift; in calm-drift early-session segments it rarely fires; in late-session drifted segments it fires more).
- `win_rate`: ≈ unchanged (small per-fill effect, signs balanced).

**Supporting verdict**: C2 FALSIFIED with smallest violation margin among three (5/11 negative deltas vs needed 8/11; max positive delta 0.082 vs allowance 0.054). This is the weakest-falsification pick under Step 5 #3.

**Regime-coverage prediction**: on **8–10 of the 11 train dates** the new gate will fire on ≥ 5% of arrivals (regime-relative threshold; running-mean adapts within session). Within the warning band of "≥11 dates" → not applicable. Within the warning band of "≤ 1" → not applicable.

## Parameter justifications

| Parameter | Value | Justification rule |
|---|---|---|
| `fast_halflife` | 20 | Inherited unchanged from parent. |
| `slow_halflife` | 120 | Inherited unchanged from parent. |
| `sensitivity` | 2.0 | Inherited unchanged from parent. |
| `min_prob` | 0.05 | Inherited unchanged from parent. |
| `min_ticks` | 30 | Inherited unchanged from parent. |
| `max_vol_ratio` | 5.0 | Inherited unchanged from parent. |
| `anchor_drift_k` | 1.5 | Derived from step-4 statistic (regime-relative per Step 6 HETEROGENEOUS rule). Choosing k = 1.5 × running-mean(abs_drift) targets ~25% gating rate — matches the p75-bucket size used in falsification. The falsification's allowance is 2×median|delta|=0.054 so any larger k (= fewer skips) makes the gate too thin; any smaller k (= more skips) leaves the positive-delta dates 20260308/09 etc. removing more wins than losses. |
| `anchor_drift_suppress` | 0.0 | Principled rule (mirrors L5 wide-spread-suppress logic): if a bucket's mean pnl is negative across the negative-delta date subset, the rational participation rate in that bucket is 0. Hard skip. Fallback if this loop regresses badly: soften to 0.3 in a follow-up. |
| `session_anchor_mid` | first observed mid of session | Principled rule: the natural anchor for "drift from open" is the session-open mid. Definition: the first `(bid+ask)/2` seen in `on_quote_tick` after `on_start`. |
| `running_mean_window` | session-cumulative (n=1, EWM disabled) | Principled rule: the falsification computed `abs_drift_from_open` directly with no rolling smoothing. Cumulative running-mean tracks the same quantity within session. |

## Honesty notes

- **All three candidates falsified.** This loop's algorithm is the method's "weakest-violation" pick under Step 5 #3, not a SURVIVED candidate. I am not relaxing the rule post-hoc to re-classify any of them as SURVIVED.
- **Parent-anchored, not champion-anchored.** The method instructs me to read `<base_algo>` (= `vol-regime-sizer`) artifacts and target its mechanism. I do not layer the L5 wide-spread skip into this algorithm because the method's parent is not the champion. The L7 critic warned about this exact issue (champion-redundancy not detectable on parent CSVs); the prompt-l5 method has no machinery to address it. This may manifest as: even if the C2 anchor-drift gate has real signal vs the parent, it may overlap heavily with the L5 wide-spread gate (both fire more on volatile/drifted late-session windows) and produce no incremental edge vs L5.
- **Mixed signs across dates.** Five dates have negative delta (skip helps), six have positive delta (skip hurts). The aggregate effect is the dot product of (date weights) × (per-date deltas). On positive-delta dates with many orders (20260316–20260320, ~95% of all orders), the gate removes wins; on negative-delta dates which are mostly low-volume early-window (20260310–20260315, ~5% of all orders) it removes losses. Volume-weighted, the gate likely removes more pnl than it saves. I am proceeding because the method directs it, not because I expect a win.
- **Sample-size warning on thin dates**: 20260308 gated_n=94 carries +$0.61 delta — likely sample noise. The decision rule's allowance correctly fails on this dominant single-date noise.
- **The parent gate already does some of this work**: when abs_drift_from_open is large, vol has likely been elevated too, so the parent's vol_ratio has already suppressed many of those orders. My new gate is incremental on top of the parent's existing suppression — but the audit didn't measure this overlap. This is a documented limitation of the method as written.
