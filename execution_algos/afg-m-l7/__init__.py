"""afg-m-l7 execution algorithm package.

Per-iteration experiment loop-7 variant of `aggressor-flow-gate`
(context mode: metrics-only). Starting point: afg-m-l6.
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
