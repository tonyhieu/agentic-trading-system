"""
main.py

Entry point for the CloudLoopAgent.

Usage:
    python main.py

The agent runs one iteration of:
  1. Backtest  →  2. Claude suggestions  →  3. Git push to snapshots/ branch
  GitHub Actions handles the S3 snapshot automatically.

To run multiple iterations, increment the iteration number between runs,
or wrap run_once() in a loop with a sleep/scheduler as needed.
"""

from agent import CloudLoopAgent


if __name__ == "__main__":
    agent = CloudLoopAgent(strategy_name="ema-cross", iteration=1)
    agent.run_once()
