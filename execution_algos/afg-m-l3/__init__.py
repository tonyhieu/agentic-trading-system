"""afg-m-l3 execution algorithm package.

Per-iteration experiment loop-3 variant of `aggressor-flow-gate`
(context mode: metrics-only). Starting point: afg-m-l2.
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
