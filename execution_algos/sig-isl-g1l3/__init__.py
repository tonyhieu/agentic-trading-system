"""sig-isl-g1l3 — island-sig, generation 1, loop 3.

Stacks a rolling-spread-p75 OPEN-side SKIP gate ON TOP of sig-isl-g1l2's
opposite-tape (Lipton imbalance + Kolm OFI) AND-gate with OR-skip
composition. G1L2's gate is preserved bit-for-bit; the spread axis is
the only structural change.
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
