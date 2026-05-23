"""Position-tier + EMA-imbalance + time-of-day (TOD) gate execution algorithm."""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
