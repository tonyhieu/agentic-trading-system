"""
main.py

Entry point for the CloudLoopAgent.

Usage:
    python main.py

The agent runs multiple iterations of:
  1. Backtest  →  2. Claude suggestions  →  3. Save versioned strategy
"""

import subprocess
import sys

if __name__ == "__main__":
    NUM_ITERATIONS = 3

    for i in range(1, NUM_ITERATIONS + 1):
        subprocess.run(
            [sys.executable, "-c",
             f"from agent import CloudLoopAgent; "
             f"agent = CloudLoopAgent(strategy_name='databento_naive', iteration={i}); "
             f"agent.run_once()"],
            check=False
        )