# Research Notes — Human Operator Alerts

This file collects ambiguity alerts written by research agents during a run.
When the agent encounters something unclear enough that a human must decide —
an unspecified assumption, a data-quality issue, a possible look-ahead bias,
or a result driven by too few trades — it appends an entry here and prints
an alert.

See `docs/OBJECTIVE.md §8` for the full policy and entry format.

---

## [2026-04-30 22:15] DATA ISSUE: fill model reports zero slippage and zero commissions on every backtest

**Detail**: Across every run made this iteration (8 runs over 4 dates × 2
algos) `mean_slippage = 0.0`, `max_abs_slippage = 0.0`, and
`total_commissions = 0.0`. Consequence: the gate's slippage
axis (`max_slippage_regression_pct`) is uninformative — both numerator and
denominator are zero — and any execution algorithm whose only edge is
*reducing slippage* will be invisible to the current pass-gate computation.
Only realized-P&L deltas can move the gate today.
**Why**: The Nautilus backtest setup in `backtest_engine` appears to fill
at top-of-book without queue-position simulation or fee schedule. Top of
book is the post-decision quote, so there is no execution-cost wedge for
the algorithm to recover.
**Alternatives**: (a) Treat the `slippage`-axis test as a no-op and design
algorithms whose edge shows up in P&L (timing, conditional submission,
position sizing). (b) If a future agent wants to research slippage-saving
algorithms, first ask the operator to enable a queue/fee model in the fill
configuration so the metric has signal. (c) Snapshots produced under the
current fill model should explicitly note that slippage was identical to
baseline by construction.
**Impact**: Material for the research direction — narrows the design
space. Does NOT invalidate this iteration's FAIL (the P&L axis carried the
decision), but does invalidate the slippage axis as evidence in either
direction.

⚠ NOTE WRITTEN: research/NOTES.md — fill model reports zero slippage on every run

---

## [2026-05-07 18:52] ASSUMPTION: simple baseline scores from prior iterations used for signal-consensus comparison

**Detail**: The `simple_execution_strategy` module was deleted in git commit
`95e3e20` ("momentum-skip: remove duplicate smoke-test result dirs"). On the
current host (non-Docker), `run_backtest(execution_algorithm_name='simple')`
raises `ModuleNotFoundError: No module named 'execution_algos.simple_execution_strategy'`.
Restoring the module was denied by the permission layer (the action was
classified as unauthorized scope escalation). The baseline comparison for
signal-consensus therefore uses the aggregate baseline metrics recorded in
prior program_database entries:
- Aggregate over 3 train dates (20260308, 20260309, 20260310): simple = $5725.00 / 2301 trades
  (consistent across imbalance-skip and momentum-skip iterations).
- Per-date 20260308: inferred from twap-defer (which ran only 20260309+20260310,
  reporting simple=$5336.00/2161 for those 2 dates): 20260308 simple ≈ $389.00/140 trades.
- 20260309+20260310 simple aggregate: $5336.00 / 2161 trades.
**Why**: The simple_execution_strategy module was inadvertently deleted from the
repository. The oracle strategy with seed=42 is deterministic, so re-running on the
same dates with the same strategy parameters would produce identical results — the
cached numbers are valid for comparison.
**Alternatives**: (a) Restore the simple_execution_strategy module (requires
human authorization). (b) Use a fresh baseline run if the module is restored.
**Impact**: The aggregate baseline comparison is reliable (deterministic oracle,
same data). The per-date breakdown for 20260309 and 20260310 individually is
not available from prior records, so per-date deltas for those two dates cannot
be computed separately. Aggregate delta is computed from reliable aggregate numbers.

⚠ NOTE WRITTEN: research/NOTES.md — simple baseline scores from prior iterations used for signal-consensus comparison

---

## [2026-05-07 18:52] DATA ISSUE: simple_execution_strategy module deleted from repository

**Detail**: Commit `95e3e20` deleted `execution_algos/simple_execution_strategy/`
(the `__init__.py` and `execution_algorithm.py`). The module is still registered
in `execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES["simple"]` pointing to
`"execution_algos.simple_execution_strategy"`. Any host that runs outside Docker
(where the module apparently was available during prior iterations) cannot run
the baseline. This prevents all future research iterations from running paired
baseline comparisons unless the module is restored.
**Why**: The deletion appears unintentional — the commit message says "remove
duplicate smoke-test result dirs" not "remove baseline algo."
**Alternatives**: Restore the simple_execution_strategy code (identical to what
was in the repo before commit 95e3e20, recoverable via git show 95e3e20^:<path>).
**Impact**: HIGH — every future research iteration on this host is blocked from
running the baseline. Human action required to restore the module.

⚠ NOTE WRITTEN: research/NOTES.md — simple_execution_strategy module deleted from repository

---

## [2026-05-09 22:25] DATA ISSUE: oracle sigma changed from 0.5 to 5 in config.yaml commit ab2360b

**Detail**: Commit `ab2360b` (2026-05-09, "minor fixes") changed `config.yaml` `strategy.kwargs.sigma` from
`0.5` to `5`. This changes the oracle noise level by 10×. Prior iterations (cap-boost through
signal-consensus) ran with sigma=0.5 yielding ~84-85% win rate. Current iteration (spread-filter)
and all future iterations run with sigma=5 yielding ~48% win rate (near-random). The oracle
at sigma=5 is essentially a noisy signal with only marginal edge over random.
**Why**: The commit message says "minor fixes" with no explanation of the sigma change. It may
have been an intentional difficulty-increase by the human operator, or an accidental edit.
**Alternatives**: (a) Restore sigma=0.5 to match prior iterations (requires human authorization).
(b) Continue with sigma=5 — the research problem becomes: "how does an exec algo improve P&L when
the underlying signal is near-random?" (c) Compare results across sigma values by noting the config
hash in each program_database entry.
**Impact**: HIGH — all prior program_database entries are INCOMPARABLE to current and future entries
because they used sigma=0.5. The pass gate ($5725 baseline at sigma=0.5) no longer applies; the new
baseline is ~$1587 over 3 train dates with sigma=5. The research direction is fundamentally different:
with ~48% oracle win rate, the execution algorithm's impact is measured against a near-random signal
rather than a highly-accurate one. The 5% gate means the algo must beat ~$1587 × 1.05 = ~$1666, which
the spread-filter nearly achieved ($1622.50, +2.25%).

⚠ NOTE WRITTEN: research/NOTES.md — oracle sigma changed 0.5 → 5 in commit ab2360b; all prior entries incomparable

---

## [2026-04-29 18:13] DATA ISSUE: backtest infra unavailable on host shell — iteration aborted before backtest

**Detail**: A test-run invocation of the researcher agent could not execute §5 step 5 (BACKTEST). `scripts/data_retriever.py` shells out to the `aws` CLI, which is not installed on the host (`brew install awscli` not run); `docker`/`docker compose` are also unavailable, so the project's intended `dev`/`agent` services cannot be spun up. `data-cache/glbx-mdp3-market-data/v1.0.0/partitions/` is empty, so no partition is reachable without a working sync path. AWS creds and `S3_BUCKET_NAME` in `.env` are correctly set; `USERNAME`/`PASSWORD` from `.env.example` are unused by the codebase and can be ignored.
**Why**: Operator ran the agent on the bare host instead of inside `docker compose run dev`. The repo's tooling assumes the Docker context where `awscli` is baked in.
**Alternatives**: (a) `brew install awscli` and re-run on host; (b) install Docker and use `docker compose run --rm dev`; (c) pre-seed `data-cache/` from another machine for an offline iteration.
**Impact**: No program_database.json entry was written (no attempt was actually executed). No algorithm code was created. The iteration budget was not consumed. Operator decision required before the next invocation.

---

## [2026-05-21 01:20] RESULT WARNING: streak-spread-multi-skip catastrophic failure from streak side-effect bug

**Detail**: `_streak_triggered()` in the streak-spread family of algorithms has a side effect: it updates `_prev_pnl_1` and `_prev_pnl_2` on EVERY call, regardless of whether an order is actually submitted. In `streak-spread-tight`, this was mitigated because the `_position_flat=True` re-entry guarantee bypassed the streak check on the first order after a skip. In `streak-spread-multi-skip`, the multi-skip logic allows up to 3 consecutive skips, calling `_streak_triggered()` on each — each call updates the PnL history with a quote-based estimate from the same real position, creating artificial streak persistence.
**Why**: The side effect was inherited from the original streak implementation without being identified as a design flaw. It works in `streak-spread-tight` because the `_position_flat` flag causes the re-entry to skip the streak check entirely.
**Alternatives**: (a) Move the PnL history update to `_record_open()` only, so it fires exactly once per actual submission. (b) Separate the evaluation function (returns triggered bool without side effects) from the update function (call only on actual submissions). Either approach would fix the bug for future multi-skip variants.
**Impact**: The multi-skip concept is not inherently flawed — the idea of allowing 2-3 consecutive skips to let spread autocorrelation decay before re-entering is sound. The implementation failed due to the side-effect bug. A fixed implementation (update streak history only on actual submissions) is a high-value next attempt.

⚠ NOTE WRITTEN: research/NOTES.md — streak-spread-multi-skip catastrophic failure from streak side-effect bug