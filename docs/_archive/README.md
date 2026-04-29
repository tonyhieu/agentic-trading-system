# Archived Documentation

These files were superseded during the 2026-04 documentation reorganization.
They are preserved for git-history reference only — **do not link to them
from active docs**.

| Old file | Where its content went |
|---|---|
| `00_START_HERE.md`, `INDEX.md` | Replaced by root `CLAUDE.md` (agent entry) and `README.md` (human entry). The "human vs agent" routing is now handled by those two files plus `docs/operator/`. |
| `README_FOR_HUMANS.md` | Moved to `docs/operator/architecture.md` (slimmed — dataset overview removed because it duplicates `docs/OBJECTIVE.md §2`). |
| `README_FOR_AGENTS.md` | Split: research brief → `docs/OBJECTIVE.md`, data-retrieval API → `docs/skills/data-retrieval.md`. |
| `AGENT_INTEGRATION_GUIDE.md` | Superseded. Canonical info now in `docs/skills/`. The original had a wrong cost model (5–20 MB partitions for the hypothetical us-equities dataset) and a buggy `BacktestEngine.backtest()` example — not migrated. |
| `PROBLEM_DEFINITION.md` | Renamed to `docs/OBJECTIVE.md`. Numeric values pulled out into `research/config.yaml`; data-retrieval CLI block trimmed and replaced with a pointer to `docs/skills/data-retrieval.md`; §9 updated to reflect single-writer append-only commits. |
| `DATA_STORAGE_CONTRACT.md` | Renamed to `docs/data-contract.md`. Production format normalized to `dbn`; partition date format normalized to `date=YYYYMMDD`; schema example replaced with real DBN record types; parquet examples labeled "template only". |
| `SKILLS.md` (was at repo root) | Split into `docs/skills/data-retrieval.md` and `docs/skills/snapshot.md`. Docker section folded into `docs/operator/architecture.md`. |
| `data-contract.md` | Folded into `docs/skills/data-retrieval.md` as the "Reference: Data Contract" section. The contract was almost always read alongside the retrieval CLI commands; one file is simpler. |
| `examples/` (parquet templates) | Archived. The hypothetical us-equities-bars-1m parquet layout was the source of repeated cost-model confusion (5–20 MB partitions vs the live ~330 MB DBN partitions). Not used by the live system. |
| `data-retrieval.md` | Superseded by `docs/skills/backtest.md`. The CLI commands were an implementation detail — `run_backtest()` in `backtest_engine/backtest_low_level.py` wraps `DataRetriever.sync_partition` internally, so the agent never calls the data-retrieval CLI directly. The data contract that lived inside this file is preserved in this archive copy. |
