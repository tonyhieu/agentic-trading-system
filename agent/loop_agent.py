"""
agent/loop_agent.py

Autonomous agent for the agentic trading loop.
Orchestrates one full iteration of:
  1. Run backtest with latest strategy version
  2. Summarize results
  3. Build prompt with strategy code and backtest summary
  4. Call Claude for improvements
  5. Validate and save improved strategy as new versioned file
  6. Save results and push to snapshots/ branch (disabled by default)
     (GitHub Actions handles S3 upload automatically via SKILLS.md)
"""

import ast
import importlib.util
import json
import os
import subprocess
from datetime import datetime

from backtest_engine.databento_backtest import run_databento_backtest
from agent.prompt_builder import summarize_backtest, build_prompt
from agent.claude_api import call_claude


class CloudLoopAgent:
    """
    Autonomous agent that iterates on a trading strategy using Claude.

    Args:
        strategy_name: Base name for the strategy (e.g. "databento_naive")
        iteration: Current iteration number. Increment between runs.
        strategy_path: Path to the strategy file to iterate on.
    """

    def __init__(self, strategy_name: str = "databento_naive", iteration: int = 1,
                 strategy_path: str = "strategies/databento_naive_strategy/databento_naive_strategy.py"):
        self.strategy_name = strategy_name
        self.iteration = iteration
        self.strategy_path = strategy_path
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

            # Step 3: Update strategy code with Claude's suggestion
            self._update_strategy()

            # Step 4: Save snapshot (disabled by default)
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

        # Find latest versioned strategy file
        dir_path = os.path.dirname(self.strategy_path)
        base_name = os.path.basename(self.strategy_path).replace(".py", "")
        latest_version_path = os.path.join(dir_path, f"{base_name}_v{self.iteration - 1}.py")

        if self.iteration > 1 and os.path.exists(latest_version_path):
            # Copy latest version to original path so backtest engine picks it up
            with open(latest_version_path, "r") as f:
                latest_code = f.read()
            with open(self.strategy_path, "w") as f:
                f.write(latest_code)
            print(f"      Using strategy version: v{self.iteration - 1}")
        else:
            print(f"      Using original strategy")

        self.engine = run_databento_backtest(strategy_name=self.strategy_name)
        self.summary = summarize_backtest(self.engine)
        self.summary["strategy_name"] = self.strategy_name  # override with actual name
        print(f"      Sharpe: {self.summary.get('sharpe_ratio')} | "
              f"PnL: {self.summary.get('pnl_total')} | "
              f"Win rate: {self.summary.get('win_rate')}")

    def _call_claude(self) -> None:
        print("\n[2/3] Calling Claude for improvements...")
        with open(self.strategy_path, "r") as f:
            strategy_code = f.read()
        prompt = build_prompt(self.summary, strategy_code)
        self.response = call_claude(prompt)
        print(f"      Got {len(self.response.get('improvements', []))} improvement(s) "
              f"and {len(self.response.get('execution_changes', []))} execution change(s)")
        print("\n=== CLAUDE RESPONSE ===")
        print(self.response)

    def _update_strategy(self) -> None:
        """
        Write Claude's improved strategy code to a new versioned file.
        Validates syntax, interface, and importability before saving.
        Original file is never permanently modified.
        """
        print("\n[3/3] Saving new strategy version...")
        new_code = self.response.get("new_strategy_code")

        if not new_code:
            print("      [WARN] No new code returned by Claude, skipping.")
            return

        # Validation 1: syntax check
        try:
            ast.parse(new_code)
        except SyntaxError as e:
            print(f"      [ERROR] Claude returned invalid syntax: {e}, skipping.")
            return

        # Validation 2: check get_trading_strategy still exists
        tree = ast.parse(new_code)
        function_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        if "get_trading_strategy" not in function_names:
            print("      [ERROR] get_trading_strategy missing from new code, skipping.")
            return

        # Validation 3: try dynamic import
        dir_path = os.path.dirname(self.strategy_path)
        base_name = os.path.basename(self.strategy_path).replace(".py", "")
        new_path = os.path.join(dir_path, f"{base_name}_v{self.iteration}.py")

        with open(new_path, "w") as f:
            f.write(new_code)

        try:
            spec = importlib.util.spec_from_file_location(f"{base_name}_v{self.iteration}", new_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, "get_trading_strategy"):
                raise AttributeError("get_trading_strategy not found after import")
            print(f"      Import validation passed.")
        except Exception as e:
            print(f"      [ERROR] Import validation failed: {e}, removing candidate.")
            os.remove(new_path)
            return

        print(f"      New version saved to: {new_path}")

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