"""
prompt_builder.py

Utilities for summarizing backtest results and building prompts for Claude.
- summarize_backtest: extracts key metrics from a completed backtest engine
- build_prompt: formats the summary into a prompt for Claude to suggest improvements
"""

from nautilus_trader.model.currencies import USDT


def _safe_get(mapping, key: str, default="N/A"):
    """
    Safely get a value from a dict-like object and stringify it.
    """
    try:
        if mapping is None:
            return default
        value = mapping.get(key, default)
        return str(value)
    except Exception:
        return default


def _safe_len(obj, default="N/A"):
    """
    Safely get len(obj).
    """
    try:
        return len(obj)
    except Exception:
        return default


def _get_total_orders(cache):
    """
    Safely get total orders from cache.
    """
    try:
        if hasattr(cache, "orders"):
            return len(cache.orders())
    except Exception:
        pass
    return "N/A"


def _get_total_positions(cache):
    """
    Try to estimate total positions as:
      len(open positions) + len(closed positions)

    Falls back to N/A if the current Nautilus version does not expose
    these methods or the return values are not sized collections.
    """
    try:
        open_positions = cache.positions_open() if hasattr(cache, "positions_open") else []
        closed_positions = cache.positions_closed() if hasattr(cache, "positions_closed") else []
        return len(open_positions) + len(closed_positions)
    except Exception:
        return "N/A"


def summarize_backtest(engine) -> dict:
    """
    Extract a robust summary from a completed backtest engine.
    This function is designed to degrade gracefully if some metrics
    are unavailable in the installed Nautilus Trader version.
    """
    summary = {
        "status": "completed",
        "strategy_name": "EMACrossStrategy",
        "execution_algorithm": "SimpleExecutionAlgorithm",
        "total_orders": "N/A",
        "total_positions": "N/A",
        "pnl_total": "N/A",
        "win_rate": "N/A",
        "sortino_ratio": "N/A",
        "profit_factor": "N/A",
        "expectancy": "N/A",
        "sharpe_ratio": "N/A",
    }

    try:
        cache = engine.cache
        analyzer = engine.portfolio.analyzer

        # Cache-based metrics
        summary["total_orders"] = _get_total_orders(cache)
        summary["total_positions"] = _get_total_positions(cache)

        # Analyzer-based metrics
        try:
            stats = analyzer.get_performance_stats_returns()
        except Exception:
            stats = None

        try:
            pnl_stats = analyzer.get_performance_stats_pnls(currency=USDT)
        except Exception:
            pnl_stats = None

        summary["pnl_total"] = _safe_get(pnl_stats, "PnL (total)")
        summary["win_rate"] = _safe_get(pnl_stats, "Win Rate")
        summary["expectancy"] = _safe_get(pnl_stats, "Expectancy")

        summary["sortino_ratio"] = _safe_get(stats, "Sortino Ratio (252 days)")
        summary["profit_factor"] = _safe_get(stats, "Profit Factor")
        summary["sharpe_ratio"] = _safe_get(stats, "Sharpe Ratio (252 days)")

        return summary

    except Exception as e:
        summary["notes"] = f"Could not fully extract metrics: {e}"
        return summary


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
- Base your answer only on the provided summary
- Do NOT invent metrics that are not present
- Do NOT include any explanation
- Do NOT include markdown (no ```json)
- Output ONLY valid JSON
"""