"""
prompt_builder.py

Utilities for summarizing backtest results and building prompts for Claude.
- summarize_backtest: extracts key metrics from a completed backtest engine
- build_prompt: formats the summary into a prompt for Claude to suggest improvements
"""

def summarize_backtest(engine) -> dict:
    """
    Extract a summary from the backtest engine after a run.
    Currently a placeholder - will be expanded to pull real metrics.
    """
    return {
        "status": "completed",
        "strategy_name": "EMACrossStrategy",
        "execution_algorithm": "SimpleExecutionAlgorithm",
        "notes": "Placeholder summary for first loop test",
    }

def build_prompt(summary: dict) -> str:
    """
    Format the backtest summary into a prompt for Claude.
    Asks Claude to return structured JSON with weaknesses,
    improvements, execution changes, and suggested parameters.
    """
    return f"""
You are improving a trading execution strategy.

Current backtest summary:
{summary}

Return your answer as STRICT JSON with the following structure:

{{
  "weaknesses": ["..."],
  "improvements": ["..."],
  "execution_changes": ["..."],
  "parameters": {{
    "param_name": "suggested_value"
  }}
}}

Rules:
- Do NOT include any explanation
- Do NOT include markdown (no ```json)
- Output ONLY valid JSON
"""