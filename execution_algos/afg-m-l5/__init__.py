"""afg-m-l5 execution algorithm package.

Per-iteration experiment loop-5 variant of `aggressor-flow-gate`
(context mode: metrics-only). Starting point: afg-m-l4.
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
