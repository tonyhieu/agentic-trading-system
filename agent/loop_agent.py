"""
agent/loop_agent.py

Autonomous agent for the agentic trading loop.
Orchestrates one full iteration of:
  1. Run backtest
  2. Summarize results
  3. Build prompt
  4. Call Claude for suggestions
  5. Print output
  6. Save results and push to snapshots/ branch
     (GitHub Actions handles S3 upload automatically via SKILLS.md)
"""

import json
import os
import subprocess
from datetime import datetime

from backtest_engine.backtest_low_level import run_backtest
from agent.prompt_builder import summarize_backtest, build_prompt
from agent.claude_api import call_claude


class CloudLoopAgent:
    """
    Autonomous agent that iterates on a trading strategy using Claude.

    Args:
        strategy_name: Base name for the strategy (e.g. "ema-cross")
        iteration: Current iteration number. Increment between runs.
    """

    def __init__(self, strategy_name: str = "ema-cross", iteration: int = 1):
        self.strategy_name = strategy_name
        self.iteration = iteration
        self.engine = None
        self.summary = None
        self.response = None

    def run_once(self) -> dict:
        """
        Run one full agent iteration.
        """
        try:
            print(f"\n{'='*50}")
            print(f"AGENT ITERATION {self.iteration} — {self.strategy_name}")
            print(f"{'='*50}")

            # Step 1: Run backtest
            self._run_backtest()

            # Step 2: Call Claude for improvements
            self._call_claude()

            # Step 3: Save snapshot (disabled by default)
            # self.save_snapshot()

            return self.response

        finally:
            # Cleanup
            if self.engine is not None:
                try:
                    self.engine.dispose()
                except Exception:
                    pass
                self.engine = None

    def _run_backtest(self) -> None:
        print("\n[1/3] Running backtest...")
        self.engine = run_backtest()
        self.summary = summarize_backtest(self.engine)
        print(f"      Sharpe: {self.summary.get('sharpe_ratio')} | "
              f"PnL: {self.summary.get('pnl_total')} | "
              f"Win rate: {self.summary.get('win_rate')}")

    def _call_claude(self) -> None:
        print("\n[2/3] Calling Claude for improvements...")
        prompt = build_prompt(self.summary)
        self.response = call_claude(prompt)
        print(f"      Got {len(self.response.get('improvements', []))} improvement(s) "
              f"and {len(self.response.get('execution_changes', []))} execution change(s)")
        print("\n=== CLAUDE RESPONSE ===")
        print(self.response)

    def save_snapshot(self) -> None:
        """
        Write results to strategies/ directory and push to a snapshots/ branch.
        GitHub Actions will detect the push and upload to S3 automatically.
        See SKILLS.md for the full snapshot system documentation.
        Requires GIT_TOKEN env var with repo write permission.
        """
        print("\n[3/3] Saving snapshot via git push...")

        versioned_name = f"{self.strategy_name}-v{self.iteration}"
        strategy_dir = os.path.join("strategies", versioned_name, "results")
        os.makedirs(strategy_dir, exist_ok=True)

        # Write backtest results
        results_path = os.path.join(strategy_dir, "backtest-results.json")
        with open(results_path, "w") as f:
            json.dump({
                "strategy_name": self.summary.get("strategy_name", self.strategy_name),
                "backtest_date": datetime.utcnow().isoformat() + "Z",
                "iteration": self.iteration,
                "performance": {
                    "sharpe_ratio": self.summary.get("sharpe_ratio"),
                    "pnl_total": self.summary.get("pnl_total"),
                    "win_rate": self.summary.get("win_rate"),
                    "sortino_ratio": self.summary.get("sortino_ratio"),
                    "profit_factor": self.summary.get("profit_factor"),
                    "expectancy": self.summary.get("expectancy"),
                    "total_orders": self.summary.get("total_orders"),
                    "total_positions": self.summary.get("total_positions"),
                },
                "claude_suggestions": self.response,
            }, f, indent=2)

        # Write Claude's suggestions
        suggestions_path = os.path.join(strategy_dir, "claude-suggestions.json")
        with open(suggestions_path, "w") as f:
            json.dump(self.response, f, indent=2)

        # Push to snapshots/ branch — GitHub Actions handles S3 upload
        branch = f"snapshots/{versioned_name}"
        token = os.environ.get("GIT_TOKEN")

        if not token:
            print(f"      [GIT_TOKEN not set — skipping git push]")
            print(f"      Results written locally to: strategies/{versioned_name}/")
            return

        try:
            subprocess.run(["git", "checkout", "-b", branch], check=True, capture_output=True)
            subprocess.run(["git", "add", results_path, suggestions_path], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Agent: iteration {self.iteration} results"],
                           check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", branch], check=True, capture_output=True)
            print(f"      Pushed to branch: {branch}")
            print(f"      GitHub Actions will snapshot to S3 automatically.")
        except subprocess.CalledProcessError as e:
            print(f"      [ERROR] Git push failed: {e.stderr.decode().strip()}")