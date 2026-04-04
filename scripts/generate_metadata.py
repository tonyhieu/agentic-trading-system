#!/usr/bin/env python3
"""Generate snapshot metadata JSON file"""
import json
import os
import subprocess
from pathlib import Path
import sys

root = os.environ.get('ROOT', 'snapshot-temp')
code_files = len(list(Path(f"{root}/code").glob('*')))
result_files = len(list(Path(f"{root}/results").glob('*')))
total_size = subprocess.run(['du', '-sh', root], capture_output=True, text=True).stdout.split()[0]

backtest_file = Path(f"{root}/results/backtest-results.json")
perf = {}
if backtest_file.exists():
    with open(backtest_file) as f:
        data = json.load(f)
        perf = data.get('performance', {})

metadata = {
    "strategy_name": os.environ.get('STRATEGY_NAME', ''),
    "snapshot_timestamp": os.environ.get('TIMESTAMP', ''),
    "commit_sha": os.environ.get('COMMIT_SHA', ''),
    "commit_sha_full": os.environ.get('COMMIT_SHA_FULL', ''),
    "branch": os.environ.get('BRANCH', ''),
    "repository": os.environ.get('REPOSITORY', ''),
    "triggered_by": os.environ.get('TRIGGERED_BY', ''),
    "actor": os.environ.get('ACTOR', ''),
    "workflow_run_id": os.environ.get('RUN_ID', ''),
    "snapshot_stats": {
        "code_files": code_files,
        "result_files": result_files,
        "total_size": total_size
    },
    "performance_metrics": {
        "total_return": perf.get('total_return', 'N/A'),
        "sharpe_ratio": perf.get('sharpe_ratio', 'N/A'),
        "max_drawdown": perf.get('max_drawdown', 'N/A'),
        "win_rate": perf.get('win_rate', 'N/A')
    },
    "created_at": subprocess.run(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ'], capture_output=True, text=True).stdout.strip()
}

output_file = f"{root}/metadata.json"
with open(output_file, 'w') as f:
    json.dump(metadata, f, indent=2)

print(f"✅ Created {output_file}")
print(json.dumps(metadata, indent=2))
