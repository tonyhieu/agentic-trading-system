# NautilusTrader — Presentation Reference

> A single reference for the NautilusTrader part of this project. Written as a
> **non-technical overview**: concepts and "why" first, with short code snippets
> only where they make an idea concrete. Use it to build slides; the **Sources**
> section at the end lists every in-repo file and external doc behind each claim.

---

## 0. TL;DR (the one-slide answer)

- **Why NautilusTrader?** It is an open-source, event-driven trading platform
  (fast Rust core, Python on top) that replays real market data tick-by-tick and
  uses the **same code for backtesting and live trading**. It ships a native
  Databento data loader and a built-in *execution-algorithm* abstraction — which
  is exactly the thing this project studies. So it gave us a realistic simulator
  for free and let us focus on the research question.
- **How does backtesting work?** We hand NautilusTrader's `BacktestEngine` a
  market (the CME venue), an instrument (an FX-futures contract), one day of real
  Databento ticks, a fixed trading strategy, and the execution algorithm under
  test. We press "run," it replays the day event-by-event, and it hands back P&L,
  Sharpe, slippage, and trade reports that we boil down to a `metrics.json`.
- **How does the "oracle" strategy work?** It is a **research harness, not a real
  predictor**. Offline, for each moment *T* it peeks 30 seconds ahead in the
  recorded data, takes that future price, optionally blurs it with noise, and
  hands it back as a "signal" stamped at *T*. This gives the system a signal of
  **known, fixed quality**, so the only thing that varies between experiments is
  the execution algorithm.

---

## 1. What is NautilusTrader?

NautilusTrader is an **open-source, production-grade algorithmic-trading
platform**. GitHub describes it as a *"production-grade, Rust-native trading
engine with a deterministic, event-driven architecture."* The performance-
critical core is written in Rust; you write your strategies and tooling in
Python on top of it.

Two ideas matter for this presentation:

1. **Event-driven.** Instead of looping over a table of prices, the engine
   processes a *stream of events* (a new quote, a trade, an order fill) one at a
   time, in timestamp order, calling your code back on each event — just like a
   real market feed would.
2. **Research-to-live parity.** The same strategy and execution-algorithm classes
   you backtest with are the ones you would deploy live. There is no rewrite
   between "it worked in simulation" and "run it on a real account."

**In this project:** `pyproject.toml` pins `nautilus-trader>=1.225.0`. (For
context, the public project was at ~1.227.0 in May 2026 and is still in active
beta development.)

---

## 2. Why was NautilusTrader chosen here?

The project's job is to **research execution algorithms** for CME FX futures:
keep the trading signal fixed, and find a smarter way to *execute* that signal
than a baseline. NautilusTrader fits that job unusually well. Framed as the
trade-offs you'd put on a slide:

| Reason | What it gives us | Where it shows up |
| --- | --- | --- |
| **Event-driven, tick-level simulation** | Decisions react to each market event in time order — matches how the real CME feed behaves | `BacktestEngine` in `backtest_engine/backtest_low_level.py` |
| **Native Databento loader** | Reads the raw market-data files directly — no custom parser to write or maintain | `DatabentoDataLoader` in `backtest_engine/data_loader.py` |
| **Built-in execution-algorithm abstraction** | The exact unit we study (`ExecAlgorithm`) is a first-class concept, cleanly separated from the trading strategy | `execution_algos/` + `ExecAlgorithm` base class |
| **Backtest ↔ live parity** | Research isn't throwaway; a winning algorithm could deploy with the same code | `ExecAlgorithm` / `Strategy` are the live classes too |
| **Netting OMS (one net position per instrument)** | Matches how directional futures actually work — you're long, short, or flat | `OmsType.NETTING` when registering the venue |
| **Realistic reports out of the box** | Orders, fills, positions, and account equity come back as ready-to-use tables | `engine.trader.generate_*_report()` |

**Honest caveat worth saying out loud (good for Q&A credibility):** this
project's simulated fill model reports essentially **zero slippage and zero
commissions by design** — it does not model queue position. That means the
research optimizes **realized P&L**, not microstructure cost recovery; the
"slippage" gate is effectively a guardrail, not the main signal. This is
documented in `research/NOTES.md`.

---

## 3. How backtesting works with NautilusTrader

### 3.1 The pipeline, end to end

```
  Databento DBN file on S3  (one compressed file per trading day, all symbols)
            │
            ▼
  Filter to ONE symbol      (stream-filter so we don't blow up memory)
            │   backtest_engine/dbn_filter.py
            ▼
  DatabentoDataLoader        (decode DBN → Nautilus QuoteTick / TradeTick objects)
            │   backtest_engine/data_loader.py
            ▼
  ┌─────────────────────  BacktestEngine  ──────────────────────┐
  │  add_venue(GLBX, netting, margin, $1,000,000 USD start)     │
  │  add_instrument(MESM6 futures contract)                     │
  │  add_data(ticks)            ← the replayed market           │
  │  add_strategy(oracle)       ← the FIXED trading signal      │
  │  add_exec_algorithm(...)    ← the VARIABLE under study      │
  │  engine.run()               ← replay the whole day          │
  └─────────────────────────────────────────────────────────────┘
            │
            ▼
  generate_*_report()  →  P&L · Sharpe · drawdown · win-rate · slippage · IS
            │   backtest_engine/results.py + arrival_price.py
            ▼
  metrics.json  /  backtest-results.json   (per-day and aggregated)
```

### 3.2 Two ways to run a backtest (and which we use)

NautilusTrader offers two API levels:

- **Low-level `BacktestEngine`** — you wire up the venue, instrument, data, and
  strategies by hand. Best when a day's data fits in memory and you want direct
  control. **This project uses the low-level API.**
- **High-level `BacktestNode`** — driven by configuration objects, orchestrates
  many engine runs, and streams data in batches when it's too big for memory.

### 3.3 Setting up one backtest (concept level)

The function `run_backtest()` in `backtest_engine/backtest_low_level.py` does the
wiring. In plain terms it:

1. Loads one day of one symbol's ticks from Databento.
2. Creates a `BacktestEngine`.
3. Registers the **venue** (the CME Globex market, `GLBX`) with a *netting*
   order-management style, a margin account, and a **$1,000,000 USD** starting
   balance.
4. Registers the **instrument** (e.g. the `MESM6` micro E-mini futures contract).
5. Feeds in the **market data** (`add_data`) and adds the **strategy** and the
   **execution algorithm**.
6. Calls `engine.run()` to replay the day.

### 3.4 How an order actually flows (the key mechanic)

This is the heart of "execution algorithm research," and it's worth one slide:

```
Strategy decides to trade
        │  creates a MarketOrder tagged with exec_algorithm_id
        ▼
NautilusTrader sees the tag and routes the order to the Execution Algorithm
        │  (NOT straight to the market)
        ▼
ExecAlgorithm.on_order(order)   ← the algorithm under study runs here
        │  it can: submit as-is, skip it, delay it, or split it into child orders
        ▼
Order reaches the simulated venue → fills → positions & account update
```

The official docs put it precisely: *"submit_order(...) routes ... to an
ExecAlgorithm when `exec_algorithm_id` is set."* The algorithm receives the
"primary" order via `on_order(self, order)` and may *"keep spawning secondary
orders, submit the remaining primary order, or do both depending on its
design."* The built-in **TWAP** algorithm is the canonical example: it slices one
big order into smaller timed child orders to reduce market impact.

In this project the strategy always sends a simple 1-contract order tagged with
the execution algorithm; the algorithm's job is to decide **whether and how** to
let it through (e.g. skip a trade when the spread is too wide).

### 3.5 What comes out

After the run, NautilusTrader produces ready-made reports — orders, fills,
positions, and an account/equity report. The project turns those into metrics:

- **Realized P&L**, **total return %**, **win rate**, **trade count**
- **Sharpe ratio** (intraday), **max drawdown**
- **Slippage** and **implementation shortfall (IS)** — how far the fill price
  drifted from the price at the moment the decision was made (computed afterward
  in `backtest_engine/arrival_price.py`)

These land in `metrics.json` (per day) and `backtest-results.json` (aggregated).

### 3.6 One process per backtest (a practical detail)

Each day's backtest runs in a **fresh Python subprocess** (`scripts/run_research_backtest.py`).
Because NautilusTrader's core is native (Rust), running many engines back-to-back
in one process can trip a memory abort — so the runner isolates each run, then
pairs the algorithm's results against the baseline across the whole train window.

---

## 4. How the Databento "oracle" strategy works

### 4.1 What it is — and what it is *not*

The oracle is **not** a market predictor and **not** a real-time data oracle. It
is a deliberately constructed **research harness**: a trading signal whose
quality we set on purpose, so that across experiments the signal stays constant
and the **execution algorithm is the only thing that changes**. Its own code
calls it *"a research harness: holds signal quality constant ... so the variable
under study is the execution algorithm."*

### 4.2 The core idea: peek ahead, then stamp it back in time

All the cleverness happens **offline, before the backtest runs**, in
`build_oracle_signals()` (`strategies/databento_oracle_strategy/preprocessing.py`):

```
For each trade at time T:
   look 30 seconds ahead in the recorded ticks  → grab that FUTURE price
   (optionally add Gaussian noise to blur it)
   emit an OracleSignal that carries {current_price, future_price}
   …but STAMP the signal at time T
```

It's an efficient single forward sweep over the day's trades (linear time, which
matters at full CME tick volumes).

### 4.3 Why this doesn't "cheat" (no look-ahead leak)

This is the subtle part worth a slide. Even though the signal *contains* a future
price, the engine never sees data out of order:

- The shift is done **offline**, and each signal is **timestamped at T**.
- So during the backtest the engine still receives a normally-ordered stream and
  delivers the signal to the strategy at T via the normal `on_data` callback —
  *"without any runtime look-ahead"* (from the `OracleSignal` docstring).

In other words: the *strategy* is allowed to know the future (that's the whole
point of a controlled signal), but the *engine and the execution algorithm* run
under honest, in-order replay.

### 4.4 The trading rule

`OracleStrategy` (`strategies/databento_oracle_strategy/oracle_strategy.py`) is
deliberately simple:

```
edge = future_price − current_price
   if edge >  entry_threshold → go long  (or flip from short)
   if edge < −entry_threshold → go short (or flip from long)
   otherwise                  → do nothing
```

Every order it sends is tagged with the `exec_algorithm_id`, so it passes through
the execution algorithm being studied. `OracleSignal` itself is a small custom
data type (`nautilus_trader.core.data.Data`) injected into the engine with
`add_data(..., client_id="ORACLE")` and received via `subscribe_data`.

### 4.5 The "difficulty dial": sigma

The `sigma` parameter controls how good the signal is:

- `sigma = 0` → a **perfect** oracle (it sees the real future price).
- Larger `sigma` → noisier, harder, more realistic.

This project uses **`sigma ≈ 6.0`**, chosen to give roughly **14% R²** — a signal
that's predictive but far from perfect, so there's real room for an execution
algorithm to add or destroy value. The calibration math lives in
`strategies/databento_oracle_strategy/calculate_sigma.py`:

```
R² = Var(ΔP) / ( Var(ΔP) + sigma² )      # ΔP = future_price − current_price
```

A fixed random `seed` (42) makes the noise — and therefore every backtest —
**reproducible**. Current oracle settings (`research/config.yaml`):
`horizon_seconds = 30`, `sigma = 6.0`, `seed = 42`,
`signal_interval_seconds = 1.0` (one signal per second, to tame volume).

---

## 5. Suggested extra topics for the presentation

These round out the story and tend to draw good questions:

1. **The central design idea: separate the *signal* from the *execution*.**
   Strategy is held fixed (the oracle); only the execution algorithm varies. This
   isolates a clean research question and is why NautilusTrader's `ExecAlgorithm`
   abstraction was such a good fit.

2. **Data architecture & cost discipline.** Real Databento DBN files (zstd-
   compressed, ~330 MB per day, all symbols) live on S3, partitioned by date. A
   streaming filter (`backtest_engine/dbn_filter.py`) extracts a single symbol
   *before* decoding, avoiding a ~18 GB memory blow-up. Per-iteration data cost is
   capped (~$0.13 for 10 days).

3. **The autonomous research loop.** An AI agent: reads history → hypothesizes an
   execution improvement → implements an `ExecAlgorithm` → backtests on the
   **train** window → must beat the baseline by a set margin (the "pass gate") →
   on PASS, snapshots to S3 → a **Lambda evaluator** then scores it on a held-out
   **test** window (out-of-sample). See `docs/OBJECTIVE.md` and the
   backtest/snapshot/evaluate skills.

4. **Research integrity / honesty rules.** A fixed train/test split (train:
   2026-03-08→03-21; test: 2026-03-26→04-06), report raw numbers, always show
   trade counts, never cherry-pick dates, and report degradation honestly
   (`docs/OBJECTIVE.md §8`). Good material for "how do you avoid fooling
   yourself?"

5. **Reproducibility & determinism.** Seeded oracle noise, deterministic
   order-ID-based randomness inside execution algorithms, and a `metadata.json`
   reproduction record per run.

6. **NautilusTrader ecosystem / future work.** The same algorithms could go live
   (research-to-live parity); the platform has adapters for many venues and a
   Rust core for speed. A natural "where this could go next" slide.

7. **Honest limitations.** Simplified fill model (no queue/slippage), small-sample
   Sharpe (≈13 trading days → noisy), and a **synthetic** signal (not real alpha).
   Naming these up front builds credibility.

---

## 6. Glossary (one line each)

| Term | Meaning |
| --- | --- |
| **BacktestEngine** | NautilusTrader's low-level simulator that replays data event-by-event |
| **BacktestNode** | The high-level, config-driven runner that orchestrates many engine runs |
| **Strategy** | The component that decides *what* to trade (here: the fixed oracle) |
| **ExecAlgorithm** | The component that decides *how/whether* to execute an order — the unit under study |
| **Venue** | A simulated market/exchange (here `GLBX`, CME Globex) |
| **OMS / netting** | Order-management style; *netting* = one net position per instrument |
| **QuoteTick / TradeTick** | NautilusTrader data objects for a best-bid/ask update and a trade |
| **DBN** | Databento Binary Encoding — the compact, zstd-compressed market-data file format |
| **MBP-1** | "Market by price, top of book" — best bid/ask price & size (plus trades) |
| **Implementation shortfall (IS)** | Gap between the fill price and the price when the decision was made |
| **OOS (out-of-sample)** | Evaluation on the held-out test window the agent never trains on |

---

## 7. Sources

### In-repo (this project)

| Topic | File |
| --- | --- |
| Backtest orchestration (`run_backtest`) | `backtest_engine/backtest_low_level.py` |
| Databento → Nautilus loading | `backtest_engine/data_loader.py` |
| Single-symbol streaming filter | `backtest_engine/dbn_filter.py` |
| Metrics & implementation shortfall | `backtest_engine/results.py`, `backtest_engine/arrival_price.py` |
| Multi-date runner / subprocess isolation | `scripts/run_research_backtest.py` |
| S3 data sync | `scripts/data_retriever.py` |
| Execution-algorithm registry | `execution_algos/__init__.py` |
| Oracle signal (custom data type) | `strategies/databento_oracle_strategy/oracle_signal.py` |
| Oracle strategy (trading rule) | `strategies/databento_oracle_strategy/oracle_strategy.py` |
| Oracle signal generation (offline shift) | `strategies/databento_oracle_strategy/preprocessing.py` |
| Sigma / R² calibration | `strategies/databento_oracle_strategy/calculate_sigma.py` |
| Hyperparameters (dates, sigma, gates) | `research/config.yaml` |
| Research brief & honesty rules | `docs/OBJECTIVE.md` |
| Known assumptions (fill model, etc.) | `research/NOTES.md` |
| System design & cost analysis | `docs/operator/architecture.md` |
| Dependency pin (`nautilus-trader>=1.225.0`) | `pyproject.toml` |

### External (official documentation)

**NautilusTrader**
- Backtesting concept (low-level vs high-level API, event-driven cycle): https://nautilustrader.io/docs/latest/concepts/backtesting/
- Execution & execution algorithms (`exec_algorithm_id` routing, `on_order`, TWAP): https://nautilustrader.io/docs/latest/concepts/execution/
- Databento integration (`DatabentoDataLoader`, DBN, schema→data-type mapping): https://nautilustrader.io/docs/latest/integrations/databento/
- GitHub repository: https://github.com/nautechsystems/nautilus_trader
- Releases (version context): https://github.com/nautechsystems/nautilus_trader/releases

**Databento**
- Databento Binary Encoding (DBN): https://databento.com/docs/standards-and-conventions/databento-binary-encoding
- Schemas & data formats (overview): https://databento.com/docs/schemas-and-data-formats
- MBP-1 (top-of-book) schema: https://databento.com/docs/schemas-and-data-formats/mbp-1
- Trades schema: https://databento.com/docs/schemas-and-data-formats/trades

---

*Note: per `CLAUDE.md`, autonomous research agents are not permitted to read the
`strategies/` folder. The oracle section above was written from that code with
explicit one-time authorization for this presentation document; the restriction
still applies to the research loop itself.*
