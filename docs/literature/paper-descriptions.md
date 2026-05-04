# Curated Papers — Execution Algorithm Research for CME GLBX FX Futures

Project context: develop execution algorithms that better execute a fixed
trading-strategy signal than a registered baseline, on tick-level FX futures
data, subject to top-of-book / participation-cap / intraday-flat constraints.
Pass gate is realized P&L improvement without slippage regression. See
`docs/OBJECTIVE.md` for the full spec.

Papers below are grouped by the role they play in the research loop.

---

## 1. Foundational optimal-execution theory

### OptimalTransactions__Almgren_and_Chriss.md
**Description**: The canonical Almgren–Chriss paper. Derives the efficient
frontier of execution trajectories for a parent order under linear permanent
+ temporary market-impact, balancing expected cost vs. variance via a
quadratic utility. Closed-form static schedule; introduces L-VaR.
**Relevance**: This is the textbook against which any new execution algorithm
will be implicitly compared. The "simple" baseline almost certainly behaves
TWAP-like; AC tells you exactly how trajectory shape should bend with
risk-aversion, time horizon, and impact parameters. Use it to motivate a
risk-aware scheduling improvement, or as a sanity check for the shape of a
proposed algorithm's child-order curve. The temporary-impact intuition maps
directly onto the project's `top_of_book_only` and `participation_cap`
constraints (impact = walking the book).

### LiquidatingBaskets__Cartea.md
**Description**: Cartea–Gan–Jaimungal extend AC-style optimal liquidation to
co-integrated baskets with permanent + temporary impact, exploiting
information from assets *outside* the basket. Closed-form solution; ~4 bps
improvement on Nasdaq data.
**Relevance**: CME GLBX FX futures are highly co-integrated (e.g., EUR/USD
vs. GBP/USD vs. DXY-implied crosses; consecutive-maturity contracts in the
same currency). An execution algorithm that watches a related contract's
order flow as a leading signal for child-order timing is a natural hypothesis
this paper formalizes. Particularly relevant for the project's "conditional
submission" hypothesis class mentioned in §5 step 2 of OBJECTIVE.md.

### OptimalHighFreqQuoting__Avellaneda.md
**Description**: Avellaneda–Stoikov derives optimal bid/ask quote
placement for a liquidity-providing dealer with finite inventory horizon
under exponential utility. Two-step solution: indifference price + LOB
calibration via order-arrival intensities.
**Relevance**: Even though the project's algorithm is a *taker* against a
fixed parent signal, the AS framework gives the right way to think about
*posting* child orders at top-of-book vs. taking — and how inventory urgency
(driven by `intraday_flat`) should widen/tighten the placement. Useful if a
hypothesis involves passive-then-aggressive child-order behaviour.

---

## 2. Microstructure signals for child-order timing

### BookImbalance__Lipton.md
**Description**: Lipton–Pesavento–Sotiropoulos compute price-move and
trade-arrival probabilities conditional on top-of-book bid/ask imbalance,
solved via a 2D Fourier–Laplace expansion. Shows imbalance is a strong
short-horizon predictor of mid-price direction and waiting time.
**Relevance**: The single most actionable execution signal listed here.
Conditional submission ("buy this child slice only when imbalance is in your
favour") is a textbook execution edge that fits inside `top_of_book_only` and
the `participation_cap` ceiling. Direct candidate for a first hypothesis.

### PredictionFromOrderFlowImbalance__Kolm.md
**Description**: Kolm–Turiel–Westray train deep nets (LSTM/CNN-LSTM/MLP) on
Nasdaq order-flow features to forecast multi-horizon high-frequency returns.
Key finding: stationary order-flow inputs beat raw LOB states, and effective
alpha horizon is ~2 price changes.
**Relevance**: If a signal-driven execution algorithm is proposed, this paper
tells you (a) which features to engineer (order flow, not raw LOB) and (b)
what horizons to actually expect alpha at — useful for sizing a holdback
window before submitting a child slice. The "two price changes" finding caps
how stale a timing signal can be before it stops helping.

### MarketBehaviorModel__Farmer.md
**Description**: Mike–Farmer empirical agent-based model of order
placement/cancellation in the LSE. Captures volatility and bid/ask spread
distributions from order-flow regularities; shows price fluctuations on short
timescales are largely a microstructure phenomenon.
**Relevance**: Useful mental model for *why* execution-side improvements over
a naive baseline exist at all — short-horizon volatility is structural, not
random, so timing matters. Calibration recipe is also a template for
writing realistic synthetic-tick tests of a new algorithm before backtesting.

### InvariantsOfOrderSizeByVolm__Kyle.md
**Description**: Kyle–Obizhaeva market microstructure invariance: bet size,
price impact, and bid–ask spread cost scale predictably with volume and
volatility. Slides apply the framework to historical market crashes.
**Relevance**: Gives the right scaling law for sizing child orders against
top-of-book volume. The project caps `order_size_per_tick ≤ floor(participation_cap × top_of_book_qty)`
— invariance theory tells you what fraction of that cap is actually
non-impactful in a given volatility regime. Useful for adaptive
participation-cap usage rather than always running at the ceiling.

---

## 3. FX-specific execution and HFT context

### FXFillRatioAndLatency__Cartea.md
**Description**: Cartea–Sánchez-Betancourt derive a latency-optimal FX
liquidity-taking strategy using market-orders-with-limit-price (MOLP) on
LMAX Exchange data. Frames the trader's choice of price-limit buffer as a
control problem balancing fill-ratio target against walking the book.
**Relevance**: The single most directly applicable paper to this project. It
is FX, it is futures-style top-of-book with a limit-price buffer, and its
optimal-strategy framework solves *exactly* the problem the project's
algorithm faces under `top_of_book_only` (when do you accept a worse price
to fill, vs. defer to a later tick?). The empirical fill-ratio numbers (T1/T2
on USD/JPY) are useful baselines for sanity-checking your own backtest fill
rates.

### HighFreqRaceProfits__Budish.md
**Description**: Aquilina–Budish–O'Neill use exchange message data
(including failed attempts) to quantify latency-arbitrage races on the LSE.
Races are frequent (~1/min for FTSE 100), fast (5–10 µs), and account for
~20% of volume; eliminating them would cut trading costs ~17%.
**Relevance**: Background context for what "winning" looks like at the
millisecond scale. The agent isn't competing in latency races, but the paper
shows that a non-trivial fraction of top-of-book quote updates are stale or
adversarial — motivates an algorithm that withholds child orders briefly
after fast-quote events instead of chasing them. Also a frame for
interpreting the project's fill-vs-slippage tradeoff.

---

## 4. Volatility forecasting for vol-aware execution

### EvalVolaEstimators_Slides__Almgren.md
**Description**: Almgren slide deck (joint with Linwei Shang) on intraday
volatility estimation infrastructure used at Quantitative Brokers — an
agency-execution shop running across CME futures. Covers volume/volatility
forecast curves and arrival-price/VWAP benchmarking.
**Relevance**: Almost a project-readme for what a production execution shop
on CME futures needs in terms of vol forecasting. Several refinement
hypotheses ("slow during high-vol" — exactly the example given in
OBJECTIVE.md §9) need an intraday vol estimator; this is the practitioner
guide for doing it on the same product class as the project.

### TickwiseVolaEstim__Dahlhaus.md
**Description**: Dahlhaus–Neddermeyer build an on-line spot-volatility
estimator for tick data via a particle filter on a nonlinear microstructure
noise state-space model. Updates every transaction; works in transaction
time *and* clock time; includes on-line bias correction.
**Relevance**: Tickwise spot vol is the right input for any vol-aware
participation-cap or scheduling rule that must update intra-tick. The fact
that it's an *online* algorithm matches the per-tick decision loop of an
execution algorithm — no look-ahead bias risk because the estimator only
uses the prior particle state.

### HighFreqPricesSlides__Rosenbaum.md
**Description**: Rosenbaum slide deck on what makes a "good" high-frequency
price model. Covers the order book, mid/last/VWAP variants, durations, and
the gap between macroscopic derivatives models and microscopic execution
models.
**Relevance**: Frame-setting: which "price" the algorithm is benchmarking
against (mid? last? micro-price?) drives how slippage gets measured.
Important for ensuring `mean_slippage` in the pass gate is computed against
the right reference and that improvement claims aren't artifacts of price
definition.

---

## 5. Cross-asset / lead-lag signals

### LeadLagEstimation__Hoffman.md
**Description**: Hoffmann et al. estimator for the lead-lag time between
two asynchronously-traded asset prices. Theoretically grounded with
asymptotic results for tick-level data.
**Relevance**: CME GLBX FX futures pairs have known lead-lag relationships
(USD-major vs. cross-rate, near-month vs. deferred contract). An execution
algorithm that delays a child slice by the empirical lag between a signal
asset and the target can improve fills. This paper gives the rigorous
estimator; pair with the next paper for empirical magnitudes.

### LeadLagRatio__Huth.md
**Description**: Huth–Abergel measure intraday lead-lag empirically using
the Hayashi–Yoshida estimator on tick data. Shows future contracts lead
underlying stocks; lead-lag has intraday seasonality and amplifies around
news/macro events. Naive market-order strategy can't profit due to spread —
but a *taker that is going to trade anyway* can.
**Relevance**: This is the exact framing for execution. The project's
parent orders are going to be sent regardless; the algorithm just chooses
*when* within an allowed window. If a leader contract just moved, defer the
child by the empirical lag — clean execution improvement that respects the
quantity invariant.

---

## 6. Reinforcement-learning execution and regime adaptation

### Diverse_Approaces_Optimal_Execution2026.md
**Description**: de Witt–Pakkanen apply PPO (MLP and CNN feature extractors)
and MAP-Elites (a quality-diversity algorithm) to minute-bar US-equity
execution atop a calibrated transient-impact propagator (exponential decay
× square-root participation, fit on 400+ stocks). PPO-CNN reaches 2.13 bps
arrival slippage vs. 5.23 bps for VWAP on 4,900 out-of-sample orders ($21B
notional). MAP-Elites produces regime-specialist policies indexed by
liquidity-volatility cells; specialists improve 8–10% inside their niche
but degrade outside it, motivating ensemble-with-baseline rather than pure
specialization. Ships open-source `GEO` Gymnasium environment.
**Relevance**: Two design ideas transfer directly to this project. (1) The
action-space architecture — agent emits a discrete multiplicative scaling
`a_t ∈ {-1, -0.75, …, +1}` applied to a baseline VWAP/participation
schedule, with `a_t = -1` pausing — is the right shape for an algorithm
that must respect `participation_cap` and `intraday_flat`: the policy never
chooses raw quantity, only a deviation from a known-completing schedule, so
the quantity invariant is structural rather than learned. The project's
"refinement hypothesis" pattern in OBJECTIVE.md §9 maps onto this
multiplicative-scaling action space cleanly. (2) The MAP-Elites finding
(specialists win in-cell, lose out-of-cell) is a warning that any single
tuned policy is implicitly averaging over regimes; FX-futures sessions
(Asia open / London fix / NY drift) are a natural descriptor axis, but a
solid global single-policy benchmark must come *before* layering
specialization, otherwise an ensemble has no fallback. Also: the
exponential-kernel × √(q/V) propagator is a more realistic simulator core
than AC-style linear impact for the project's tick-resolution backtest, and
the 13-dim observation vector (mid, vol, time-remaining, inventory, ADV%,
σ¹/σ⁵, last fill, immediate/cumulative impact, arrival benchmark) is a
ready template for what the project's algorithm should observe per tick.

