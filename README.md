# Agentic Trading System

Created for Event Horizon Labs as a part of the University of Chicago Project Lab, Spring 2026.

An iterative feedback loop for autonomous agents to research, develop, and backtest intraday trading strategies on CME GLBX FX futures. Agents iterate in Docker, retrieve market data partitions from S3, and snapshot passing strategies back to S3 via GitHub Actions.

## System Architecture

![System Architecture](./docs/architecture.png)

## Documentation

| Document | Audience | Contents |
|---|---|---|
| [docs/PROBLEM_DEFINITION.md](docs/PROBLEM_DEFINITION.md) | Agents | Metatask, evaluation oracle, research loop, NOTES format |
| [SKILLS.md](SKILLS.md) | Agents | Two executable skills: data retrieval and strategy snapshot |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Humans | Design decisions, cost model, scaling |
| [docs/AWS_SETUP.md](docs/AWS_SETUP.md) | Humans | One-time AWS infrastructure setup |
| [docs/DATA_STORAGE_CONTRACT.md](docs/DATA_STORAGE_CONTRACT.md) | Both | S3 layout, manifest/schema/checksum spec |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Both | Setup, snapshot, and data-retrieval errors |

## Quick Start

- **Agents**: read [docs/PROBLEM_DEFINITION.md](docs/PROBLEM_DEFINITION.md), then [SKILLS.md](SKILLS.md).
- **Setting up AWS**: follow [docs/AWS_SETUP.md](docs/AWS_SETUP.md).
- **Understanding the design**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository Structure

```
agentic-trading-system/
├── backtest_engine/              # Backtester core
├── catalog/                      # Dataset catalog
├── data/                         # Local data scratch
├── execution_algos/              # Reusable execution algorithms
├── strategies/                   # Trading strategy implementations
│   └── sample_momentum_strategy/
├── scripts/
│   ├── data_retriever.py         # CLI for S3 data partitions
│   └── retrieve_snapshot.py      # CLI for snapshot download
├── docs/                         # See Documentation table above
├── .github/workflows/
│   └── snapshot-strategy.yml     # Snapshot → S3 workflow
├── docs/literature/              # Reference papers
├── SKILLS.md                     # Agent runbook
├── Dockerfile
├── docker-compose.yml
├── main.py
├── pyproject.toml
└── README.md
```

## License

Created for Event Horizon Labs — University of Chicago Project Lab, Spring 2026.
