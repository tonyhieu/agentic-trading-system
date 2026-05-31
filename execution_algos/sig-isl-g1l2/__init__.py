"""sig-isl-g1l2 — island-sig, generation 1, loop 2.

Sign-flipped fork of sig-isl-g1l1: skip an opening order only when BOTH
Lipton's static imbalance AND Kolm's rolling OFI point AGAINST the trade
direction (opposite-tape gate). G1L1's same-direction predicate was
empirically falsified; this loop tests the mechanism-correct opposite-tape
predicate.
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
