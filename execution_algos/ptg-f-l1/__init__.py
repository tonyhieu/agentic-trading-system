"""ptg-f-l1 execution algorithm package.

Per-iteration experiment loop-1 variant of `position-tier-gate`
(context mode: full-trace).
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
