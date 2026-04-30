# Research Notes — Human Operator Alerts

This file collects ambiguity alerts written by research agents during a run.
When the agent encounters something unclear enough that a human must decide —
an unspecified assumption, a data-quality issue, a possible look-ahead bias,
or a result driven by too few trades — it appends an entry here and prints
an alert.

See `docs/OBJECTIVE.md §8` for the full policy and entry format.

---

## [2026-04-30 22:15] RESULT WARNING: test split for `reduce-only-cooldown` is 1 date only

**Detail**: This iteration evaluated `reduce-only-cooldown` (defer_ms=50)
on the 4 already-cached partitions inside `data_window`: train = 3 dates
(20260309, 20260313, 20260317) and test = 1 date (20260406). The
`pass_gate` decision (FAIL) is based on train aggregation per OBJECTIVE.md
§5 step 6, but the test-side OOS check is only a single day — too thin to
draw a real generalization conclusion from. Reporting train delta_pnl
**−0.77%** and test delta_pnl **+0.09%** as raw numbers; do NOT read the
test number as evidence of OOS robustness.
**Why**: To stay inside the 10-partition iteration budget the agent reused
only the cached partitions instead of downloading more days. Status (FAIL)
would not change with more dates because the train-side delta is far from
the +5% gate, but the per-date variance is large (e.g. day-to-day P&L
deltas of −5%, +3%, +1% on train) so any future refinement should run on
a wider set before drawing conclusions about the mechanism.
**Alternatives**: Future iterations refining this algorithm should expand
the train+test set (download up to 10 fresh partitions) before claiming a
better defer_ms or a different mechanism beats baseline.
**Impact**: Low for THIS iteration's PASS/FAIL decision (FAIL is
unambiguous); high for any follow-up that compares variants.

⚠ NOTE WRITTEN: research/NOTES.md — reduce-only-cooldown test split is 1 date

---

## [2026-04-30 22:15] DATA ISSUE: fill model reports zero slippage and zero commissions on every backtest

**Detail**: Across every run made this iteration (8 runs over 4 dates × 2
algos) `mean_slippage = 0.0`, `max_abs_slippage = 0.0`, and
`total_commissions = 0.0`. This is true for the baseline `simple` algo as
well as the new `reduce-only-cooldown`. Consequence: the gate's slippage
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

## [2026-04-29 18:13] DATA ISSUE: backtest infra unavailable on host shell — iteration aborted before backtest

**Detail**: A test-run invocation of the researcher agent could not execute §5 step 5 (BACKTEST). `scripts/data_retriever.py` shells out to the `aws` CLI, which is not installed on the host (`brew install awscli` not run); `docker`/`docker compose` are also unavailable, so the project's intended `dev`/`agent` services cannot be spun up. `data-cache/glbx-mdp3-market-data/v1.0.0/partitions/` is empty, so no partition is reachable without a working sync path. AWS creds and `S3_BUCKET_NAME` in `.env` are correctly set; `USERNAME`/`PASSWORD` from `.env.example` are unused by the codebase and can be ignored.
**Why**: Operator ran the agent on the bare host instead of inside `docker compose run dev`. The repo's tooling assumes the Docker context where `awscli` is baked in.
**Alternatives**: (a) `brew install awscli` and re-run on host; (b) install Docker and use `docker compose run --rm dev`; (c) pre-seed `data-cache/` from another machine for an offline iteration.
**Impact**: No program_database.json entry was written (no attempt was actually executed). No algorithm code was created. The iteration budget was not consumed. Operator decision required before the next invocation.