# 📚 Documentation

Two sections organized by who you are.

## 🎯 Pick Your Path

### I'm a **Human** (Developer, Researcher, Infrastructure)
👉 **[README_FOR_HUMANS.md](README_FOR_HUMANS.md)** (6 min)
- System architecture and design decisions
- Why we chose date-based partitioning
- AWS setup overview
- Cost implications

### I'm an **Autonomous Agent** (Need to retrieve and analyze data)
👉 **[README_FOR_AGENTS.md](README_FOR_AGENTS.md)** (10 min)
- Quick start (5 minutes to first download)
- API reference and CLI commands
- Code examples for data loading
- Troubleshooting

### I'm **Looking for Something Specific**
👉 **[INDEX.md](INDEX.md)** - Navigation guide

---

## Core Documents

| Document | What |
|----------|------|
| **README_FOR_HUMANS.md** | Architecture, design, costs |
| **README_FOR_AGENTS.md** | Integration, quick start, examples |
| **WHY_SELECTIVE_PARTITIONING.md** | Why we save 62% on costs (architectural decision) |
| **AWS_SETUP_GUIDE.md** | How to set up infrastructure |
| **DATA_STORAGE_CONTRACT.md** | S3 file structure and metadata |
| **AGENT_INTEGRATION_GUIDE.md** | Integration workflows and examples |
| **TROUBLESHOOTING.md** | Common issues and fixes |

---

## System at a Glance

- **What**: Autonomous agents retrieve market data from AWS S3
- **Why**: Date-based partitioning saves 62% on typical backtests
- **How**: CLI tool (`data_retriever.py`) downloads only what you need
- **Scale**: 8.99 GB dataset, 26 trading days, 125M records
- **Cost**: ~$5-10/month for typical usage

---

Start with the README for your role above. See [INDEX.md](INDEX.md) if you need help finding something specific.

