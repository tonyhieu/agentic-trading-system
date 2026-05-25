"""sip-afg-l8 — clipped-print aggressor-flow-gate.

A variant of ``aggressor-flow-gate`` that clips each individual trade
print's signed contribution to ``max_print_size`` contracts before
adding it to the rolling window. The goal is to ensure the
net-flow signal reflects *broad-based* sustained aggressor pressure
rather than being dominated by a single very large print.
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
