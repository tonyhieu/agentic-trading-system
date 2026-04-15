"""
cloud_loop_runner.py

Entry point for the agentic trading loop.
Orchestrates one full iteration of:
  1. Run backtest
  2. Summarize results
  3. Build prompt
  4. Call Claude for suggestions
  5. Print output
  6. Optionally save results to S3
"""

import boto3
import json

from backtest_engine.backtest_low_level import run_backtest
from prompt_builder import summarize_backtest, build_prompt
from claude_api import call_claude


def save_to_s3(response: dict, iteration: int) -> None:
    """
    Save Claude's response to S3 as a snapshot.

    Disabled by default in main() unless save_snapshot=True.
    Requires valid AWS credentials and write permission to the bucket.
    """
    s3 = boto3.client("s3", region_name="us-east-2")
    key = f"strategies/cloud-loop/iteration-{iteration}/result.json"

    s3.put_object(
        Bucket="agentic-trading-snapshots-uchicago-spring-2026",
        Key=key,
        Body=json.dumps(response, indent=2),
        ContentType="application/json",
    )
    print(f"\nSaved to S3: {key}")


def main(save_snapshot: bool = False, iteration: int = 1) -> None:
    """
    Run one iteration of the agentic trading loop.

    Args:
        save_snapshot: If True, save Claude's response to S3.
                       Defaults to False.
        iteration: Iteration number used in the S3 key path.
    """
    engine = None

    try:
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

        # Step 6: Optionally save results to S3
        if save_snapshot:
            save_to_s3(response, iteration)
        else:
            print("\n[S3 snapshot skipped - set save_snapshot=True to enable]")

    finally:
        # Cleanup
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main(save_snapshot=False, iteration=1)