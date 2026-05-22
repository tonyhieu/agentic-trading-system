"""ptg-m-l4 execution algorithm package.

Per-iteration experiment loop-4 variant of `position-tier-gate`
(context mode: metrics-only).
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
