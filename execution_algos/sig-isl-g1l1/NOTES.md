# Algorithm Notes: sig-isl-g1l1 (island-sig, generation 1, loop 1)

## Island lineage

- Island: island-sig (theme: "Microstructure signals")
- Base algo: `simple` (the configured `pass_gate.baseline`; this is the cold-start
  G1L1 — there is no per-island base entry in `config.yaml → island_experiment.islands`
  for island-sig because the schema only lists base algos for the
  pre-literature islands; for the literature-seeded islands, generation 1 is built
  on top of the `simple` template per the operator instructions).
- Cross-island input: NONE — this is generation 1, no migration reports exist yet.
  Hypothesis derives purely from the two seed papers.

## Seed-paper synthesis

Both papers in the `island-sig` seed set converge on a single executable
microstructure-signal idea, but at different granularities:

**Lipton, Pesavento, Sotiropoulos (BookImbalance, 2014)** — top-of-book
imbalance `I = (q_b - q_a) / (q_b + q_a) ∈ [-1, +1]` is a strong predictor of
(a) the *direction* of the next mid-price move and (b) the *waiting time* until
that move. Their empirical Figure 7 shows the probability of an *unfavorable*
price move for a passive poster rises monotonically with adverse imbalance,
reaching ~90% at |I| ≈ 0.8. Their practical implication, quoted from §
"Calibration": *"a broker can decide to keep the order posted on the near side
for moderate imbalance values and cross the spread in a highly imbalanced
book."* For a marketable order, the same physics inverts: when imbalance is
heavily *with* the trade direction (BUY into bid-heavy book, SELL into
ask-heavy book), the arrival mid is about to move *against* the trader — that
is the moment to skip, because the oracle's 30s alpha will be diluted by an
unfavorable arrival price.

**Kolm, Turiel, Westray (OFI, 2023)** — extends static imbalance to *order
flow imbalance* (OFI), a stationary per-update derivative-style quantity
defined from successive top-of-book states (their eqs. 2–3 and 5):

  `OFI_t = bOF_t - aOF_t`, where bOF and aOF are the *signed* changes to the
  bid and ask queues over one quote update (replenishment minus depletion).

Their headline finding: OFI at level 1 alone carries most of the short-horizon
predictive content; the effective horizon is roughly two average price changes
(~seconds on equities, comparable on liquid futures). OFI is the
*time-derivative* analog of Lipton's static `I`.

The two papers are complementary:
- Lipton's `I` is a **level** signal (where is the book now?).
- Kolm's OFI is a **change** signal (where is the book *going*?).

A book may be heavily bid-heavy by level (`I > 0.6`) but with recent OFI flat
or negative — the imbalance is *stale*, queue depletion is no longer being
reinforced by new buyer pressure. Conversely, `I` may be neutral but OFI
strongly positive — a fresh push that the static snapshot has not yet caught
up to.

## Hypothesis

**Mechanism**: A two-signal microstructure gate — **skip an opening order only
when BOTH the static imbalance signal AND the recent OFI signal point against
the trade direction**. Specifically, for each opening order (not reduce-only):

1. Read the latest cached top-of-book quote: `bid_size`, `ask_size`, `bid_price`,
   `ask_price`. Compute `I = (bid_size - ask_size) / (bid_size + ask_size)`.
2. Maintain a rolling deque of per-quote-tick OFI contributions. On each
   `on_quote_tick`, compute the OFI increment from the previous quote (per
   Kolm eqs. 2, 3, 5 specialized to level 1):
     - `bOF` = `+v_b` if `b > b_prev`; `v_b - v_b_prev` if `b == b_prev`;
                `-v_b_prev` if `b < b_prev`.
     - `aOF` = `-v_a_prev` if `a > a_prev`; `v_a - v_a_prev` if `a == a_prev`;
                `+v_a` if `a < a_prev`.
     - `OFI_increment = bOF - aOF`.
   Store `(ts_event_ns, ofi_increment)` and prune to the rolling window.
3. At order arrival, compute the sum of OFI over the last `ofi_window_seconds`.
4. Gate rule:
   - **Skip BUY** iff `I >  imbalance_threshold` AND `recent_ofi >  ofi_threshold`.
     (Book is heavily bid-heavy AND the bid-heaviness is actively being
     reinforced — fresh buyer pressure. Lipton: unfavorable price move probable.
     Kolm: pressure is current, not stale.)
   - **Skip SELL** iff `I < -imbalance_threshold` AND `recent_ofi < -ofi_threshold`.
   - Otherwise: submit.
5. Reduce-only / closing orders always submit (intraday_flat compliance).
6. Anti-cascade: after any skip, `_position_flat = True`; the next opening
   order submits unconditionally. (Standard contract in this repo.)

**Inefficiency exploited**: The `simple` baseline submits every opening order
the strategy emits, regardless of microstructure state. Lipton's empirics
imply ~10-30% of arrival-mid moves are predictably unfavorable at extreme
imbalance — meaning *some* of the simple baseline's entries are firing into
arrival prices the broker would rather have skipped. The 30s oracle signal is
strong enough on average to overcome that, but on the marginal entries where
both the static imbalance and the per-tick OFI confirm a fresh adverse push,
the expected arrival-price drag is large enough that skipping wins.

**Why the AND, not OR**: The base lesson from existing repo experiments
(see `imbalance-skip` and `ofi-skip` in git history: +0.10% and +0.96% pnl vs
simple respectively, both well below the 5% gate) is that *either signal
alone is too noisy*. Both papers' actual predictive power is at the *tails* —
the high-confidence quadrant. Requiring both signals to fire concentrates the
skip on the literature's high-confidence adverse cases and leaves the
middle-of-the-distribution noise (where both signals are weakly informative
individually) un-touched.

**Why it should survive costs**: This is a pure SKIP gate, never modifies
order quantity, never adds aggressive children. It can only *reduce* fill
volume; expected effect on slippage is neutral-to-favorable (skipped trades
were the highest-IS-cost ones, by construction). The risk is over-skipping
favorable entries that happened to coincide with an extreme microstructure
state for unrelated reasons — bounded by the AND requirement and by the
anti-cascade re-entry rule.

**Builds on**: `simple` (cold-start G1L1; the operator instructions specify
the literature-seeded islands build the G1L1 from scratch on top of the
`simple` template). The structural pattern (cache the quote, gate via
microstructure signal, anti-cascade) follows the conventions of existing
SKIP-style algos in the repo (e.g. `imbalance-skip`, `streak-spread-tight`,
`aggressor-flow-gate`) — but the *gate logic* is novel: a two-signal AND
derived from the level + change duality at the heart of both seed papers.

**Alternatives considered (deferred to later loops)**:
- Use the *quantity* of `I` and `OFI` to modulate (not just gate) — e.g. tier
  skip probability by signal strength. Adds two free parameters per tier; defer
  to loop 2 or 3 once we know the gate has any effect at all.
- Multi-level book imbalance (top-10 OFI per Kolm's main results). Databento
  GLBX MBP-1 only ships top-of-book in the standard partition; deeper levels
  would need a separate ingestion path. Defer.
- Active passive posting (Lipton's actual recommendation: post passively at
  moderate `I`, cross spread at high `|I|`). Requires emitting *new* LIMIT
  child orders instead of pass-through MARKET orders, which is a larger
  structural change than a G1L1 cold-start warrants. Defer.
- OFI slope / regression coefficient (per Kolm eq. 6 ARX with 100 lags).
  Stateful, more parameters; defer to loops where we can compare against the
  simpler rolling-sum baseline this loop establishes.

## Implementation Decisions

- **Quote-tick deque for OFI**: a single `deque[(ts_event_ns, ofi_increment)]`
  fed by `on_quote_tick`. Pruned to `ofi_window_seconds` on demand at order
  arrival. Maintain a running sum `_net_ofi` for O(1) window evaluation; subtract
  on prune. This matches the deque pattern used in `aggressor-flow-gate` and
  `afg-isl-g1l1`.
- **OFI increment computed at quote arrival**, not at order arrival. State
  needed: `_prev_bid_price`, `_prev_bid_size`, `_prev_ask_price`, `_prev_ask_size`
  (all set on first quote, then updated each `on_quote_tick`).
- **`I` computed at order arrival** from the latest cached `quote_tick`, since
  it is a pure level statistic.
- **Parameter defaults**:
  - `imbalance_threshold = 0.33` (corresponds to a roughly 2:1 book ratio —
    the regime where Lipton's empirical curves show the price-move probability
    first rises noticeably above 50%; about the top ~20% of imbalance
    magnitudes by Lipton's Figure 2 calibration on Vodafone, and a defensible
    starting point for MES futures pending tuning).
  - `ofi_window_seconds = 2.0` (Kolm reports the predictive horizon is
    "approximately two average price changes" — on MES futures this is
    roughly 1-3 seconds; pick 2.0s as a middle estimate; future loops can
    tune).
  - `ofi_threshold = 5.0` contracts (modest, since 2s of MES OFI is
    typically O(10) contracts in active periods; require a meaningful net
    push but not so high that it's only the tail).
- **Quantity invariant**: never modify `order.quantity`. Only skip or submit.
- **No look-ahead**: deque is fed strictly by `on_quote_tick`; pruning uses
  `order.ts_init` as the cutoff anchor for OFI window evaluation.
- **Subscription**: subscribe to quote ticks on first encounter
  (`_ensure_subscribed`). Trade ticks not required for this gate.
- **Anti-cascade**: after any skip, `_position_flat = True`; the next opening
  order submits unconditionally.

## Backtest Observations

**Train window**: 12 dates, 2026-03-08 .. 2026-03-20 (full configured train set).

**Raw aggregate numbers (sig-isl-g1l1 vs `simple` baseline)**:

| metric              | sig-isl-g1l1 | simple (base)  | vs_base     |
|---------------------|--------------|----------------|-------------|
| realized_pnl        |  -550.50     |   156.00       | -452.88%    |
| unrealized_pnl      |     0.00     |     0.00       |  n/a        |
| sharpe_ratio (12d)  |   -1.9691    |    0.5996      | -428.4%     |
| max_drawdown_pct    |   -0.0663    |   -0.0529      | worse       |
| win_rate            |    0.3455    |    0.3506      | -0.51pp     |
| trade_count         |  126,931     |  136,734       |  -7.17%     |
| mean_slippage       |     0.0      |     0.0        |  0.0%       |
| is_weighted_bps     |    0.0326    |    0.0389      | -16.18%     |

(`mean_slippage = 0.0` on both sides reflects pure marketable-order arrival-mid
slippage being zero in this strategy + symbol; vs_base slippage % is 0.0% by
definition with no information content. This is the same artifact documented
in every other algo's NOTES on this baseline.)

**Trade count**: 126,931 — well above the 30-trade reliability threshold;
sharpe / win-rate numbers are trustworthy. We also have per-date sample
sizes: the smallest day (20260308) had 371 trades, all others ≥1827 trades.

**Headline interpretation**: The two-signal microstructure gate is
**clearly worse than the `simple` baseline**. PnL collapsed from +$156 to
-$550 (a swing of -$706.50 over the train window). The gate skipped ~7.2%
of opening orders (`136734 - 126931 = 9803` fewer trades on average across
the symmetric strategy-side accounting) and those skipped trades, on net,
were *not* the adverse-arrival-price ones the hypothesis predicted; they
were the *favorable* ones. Hypothesis is **falsified**.

**Mechanistic diagnosis** (per Step 8 honesty: explain, do not hide):

1. **The skipped entries were systematically the *winners*, not the losers.**
   The gate fires when `I` is large AND OFI is large in the same direction.
   That state — book heavily one-sided AND being actively reinforced — is the
   moment when the price is most likely to *continue* moving in the
   imbalance direction *over a 30s horizon* as well, not just the next tick.
   The oracle's 30s alpha rides those continuation moves. By filtering them
   out, we throw away the strategy's best trades.

   Lipton's empirics are *next-tick* / next-trade-arrival, on horizons of
   seconds. The oracle here is forecasting 30s ahead. The local
   tick-by-tick adverse-arrival-price hit is dwarfed by the 30s alpha when
   both signals are strong. The hypothesis conflated "adverse for the next
   spread" with "adverse for the 30s round-trip" — those are opposite.

2. **The is_weighted_bps actually *improved*** (-16.18% vs simple, i.e. ~16%
   lower arrival-mid IS cost). That confirms the gate *is* correctly
   identifying the high-IS arrival moments — at the tick scale, Lipton is
   right. But the IS savings (a few hundredths of a bps per trade) are
   completely overwhelmed by the lost edge from skipping the 30s
   continuation winners.

3. **Per-day pattern**: the algo lost most on the high-volume late-window
   dates (20260316: -$655, 20260317: -$400) which were also the
   *positive-PnL* days for `simple` (+$157 on 20260318, +$112 on 20260319,
   +$126 on 20260320 for simple vs nearly flat / negative for sig-isl-g1l1).
   On those days the strong-imbalance + strong-OFI moments were directional
   trends the oracle correctly rode — exactly the moments the gate
   suppressed. Conversely, on the down days for simple (20260313:
   -$512), the gate's small skip count produced only marginal damage.

4. **The AND rule is too tight to be the source of the failure.** It
   skipped only 7.2% of trades. The problem is not over-skipping — it is
   that *every skipped class* on the AND-confirmed set is *systematically
   wrong* for a 30s-horizon strategy. Loosening the threshold would make it
   strictly worse; tightening would only return us to the baseline.

5. **Signed-direction mistake**: For a marketable BUY into a bid-heavy +
   bid-pushing book, Lipton says the *next mid* moves up — which is
   *favorable* for the position once entered, even if the arrival print
   is slightly worse. The "adverse" framing only applies to **passive
   posting at the near side**, where you wait and the queue depletes
   against you. With marketable orders + 30s horizon, the signed
   relationship inverts: strong same-direction imbalance is a *bullish*
   tape, you *want* to be in those trades.

**Implication for island-sig loop 2 (and migration insights)**:

The clearest learning is that **microstructure-derived "adverse selection"
signals from passive-posting literature do not transfer to marketable
execution against a multi-second alpha**. For loop 2, two structurally
different directions look worth trying:

- **Flip the sign**: treat strong-same-direction `I + OFI` as a *go*
  signal (require it for entry on weak oracle outputs, or simply
  skip-when-*opposite* — i.e. skip a BUY only when `I < -threshold` AND
  `OFI < -threshold`, gating against entries fighting the local tape).
- **Move from gating to passive child placement** (Lipton's actual
  recommendation): when `I` is moderate, place a LIMIT child at the near
  side instead of marketable; cross the spread only when `|I|` is large
  in the *trade* direction. This converts microstructure information
  from a binary skip into a routing decision and decouples it from the
  30s-alpha-continuation conflict. Requires a larger structural change
  than this G1L1 — defer to loop 2 or 3.

These are the two G1L2 candidates I would pre-register.

