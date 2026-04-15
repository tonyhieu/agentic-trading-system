"""
cloud_loop_runner.py

Entry point for the agentic trading loop.
Orchestrates one full iteration of:
  1. Run backtest
  2. Summarize results
  3. Build prompt
  4. Call Claude for suggestions
  5. Save results to S3 (unused currently)
"""

import boto3
import json
from prompt_builder import summarize_backtest, build_prompt
from claude_api import call_claude


def run_backtest() -> dict:
    """
    Mock backtest result.
    To be replaced with real Nautilus backtest once environment is confirmed.
    """
    return {
        "strategy_name": "EMACrossStrategy",
        "execution_algorithm": "SimpleExecutionAlgorithm",
        "total_return": 10.5,
        "sharpe_ratio": 1.2,
    }


def save_to_s3(response: dict, iteration: int) -> None:
    """
    Save Claude's response to S3 as a snapshot.
    Disabled by default - enable when ready to persist results.
    Requires write permissions on the S3 bucket.
    """
    s3 = boto3.client("s3", region_name="us-east-2")
    key = f"strategies/cloud-loop/iteration-{iteration}/result.json"
    s3.put_object(
        Bucket="agentic-trading-snapshots-uchicago-spring-2026",
        Key=key,
        Body=json.dumps(response),
    )
    print(f"Saved to S3: {key}")


def main(save_snapshot: bool = False) -> None:
    """
    Run one iteration of the agentic trading loop.
    
    Args:
        save_snapshot: Set to True to save results to S3. 
                       Disabled by default to avoid unnecessary costs.
    """
    iteration = 1

    # Step 1: Run backtest
    engine = run_backtest()

    # Step 2: Summarize backtest results
    summary = summarize_backtest(engine)

    # Step 3: Build prompt for Claude
    prompt = build_prompt(summary)

    # Step 4: Call Claude for improvement suggestions
    response = call_claude(prompt)

    # Step 5: Print results
    print("=== BACKTEST SUMMARY ===")
    print(summary)
    print("\n=== PROMPT ===")
    print(prompt)
    print("\n=== CLAUDE RESPONSE ===")
    print(response)

    # Step 6: Optionally save to S3
    if save_snapshot:
        save_to_s3(response, iteration)
    else:
        print("\n[S3 snapshot skipped - set save_snapshot=True to enable]")


if __name__ == "__main__":
    main(save_snapshot=False)