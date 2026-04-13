# Data Retrieval MVP Plan (40 GB Datasets)

## Objective

Enable autonomous agents to reliably retrieve only the data they need from AWS S3, iterate on trading strategies, and avoid full 40 GB downloads in normal workflows.

## Scope

### In Scope

- Dataset storage contract (layout, naming, manifest requirements)
- Agent retrieval contract (discover -> metadata -> selective pull)
- Docker-first runtime recommendation
- Validation criteria for a minimum viable workflow

### Out of Scope

- New production services
- New orchestration platform
- Complex data catalog infrastructure

## MVP Architecture

1. **S3 Dataset Store**  
   Versioned datasets under `datasets/{name}/{version}/`.
2. **Manifest-Driven Discovery**  
   Agents fetch `manifest.json` first.
3. **Selective Partition Sync**  
   Agents download only required partitions.
4. **Local Persistent Cache**  
   Reused between runs to reduce transfer and time.

## Core Decisions

- **Runtime model:** Docker-first for agent reproducibility; host CLI fallback supported.
- **Data format:** DBN (Databento binary format) with zstd compression.
- **Partitioning:** date-first; each date is one atomic partition containing all symbols.
- **Versioning:** immutable dataset versions; publish new versions instead of in-place updates.

## Phased Plan

## Phase 1: Contract Finalization

Define and freeze:

- S3 prefix standard
- Manifest required fields
- Naming conventions for dataset and version

Exit criteria:

- Contract documented and internally consistent.
- Example manifest available in docs.

## Phase 2: Operational Playbook

Document command-level workflows:

- Upload new dataset version
- Discover datasets and versions
- Retrieve manifest first
- Retrieve partition subsets
- Resume interrupted sync

Exit criteria:

- A single guide exists with runnable commands for all core paths.

## Phase 3: Validation and Guardrails

Define acceptance checks and failure behavior:

- Agent can complete end-to-end retrieval loop using only AWS CLI.
- Agent can retrieve subset partitions without full-version sync.
- Agent can rerun safely and reuse local cache.

Exit criteria:

- Acceptance criteria checklist is met.
- Common failure modes and mitigations are documented.

## 40 GB Strategy Details

### Why split data

A 40 GB monolithic file increases transfer latency, cost, and failure blast radius. Partitioned storage allows targeted retrieval and faster iteration.

### Recommended partition model

- Primary: `date=YYYY-MM-DD`
- Secondary (optional): `symbol=TICKER`

### Retrieval policy

- Always read `manifest.json` first.
- Select only needed partition prefixes.
- Keep partition cache on persistent disk.

## Risks and Mitigations

- **Risk: Full sync by mistake**  
  Mitigation: enforce metadata-first retrieval in docs and examples.
- **Risk: Schema drift across versions**  
  Mitigation: include `schema.json` and explicit version metadata.
- **Risk: stale cache**  
  Mitigation: compare local version marker with remote manifest before run.
- **Risk: transfer cost growth**  
  Mitigation: selective sync, compression, and partition pruning.

## Acceptance Criteria (MVP)

1. Agent lists available datasets in S3.
2. Agent lists versions for a dataset.
3. Agent downloads and parses `manifest.json`.
4. Agent downloads only selected partition prefixes.
5. Agent reruns retrieval without re-downloading unchanged data.
6. Agent can run inside Docker with mounted workspace/cache.

## Definition of Done

- Documentation exists for upload + retrieval contracts and CLI workflows.
- Docker and host workflows are both specified.
- 40 GB handling strategy is explicit and actionable.
- README links to the new retrieval docs.
