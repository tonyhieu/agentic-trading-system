"""ptg-m-l5 execution algorithm package.

Per-iteration experiment loop-5 variant of `position-tier-gate`
(context mode: metrics-only).
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
