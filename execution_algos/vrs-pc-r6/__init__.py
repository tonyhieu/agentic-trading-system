"""vrs-pc-r6: sensitivity-3.0 variant of vrs-pc-r5 (continues the 0.5-step
gradient on the sensitivity axis with min_prob=0.0 retained from runs 4-5)."""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
