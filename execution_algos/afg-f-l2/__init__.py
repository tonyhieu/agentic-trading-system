"""afg-f-l2 — aggressor-flow gate with tightened threshold (1.5).

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 2. Starting point: `afg-f-l1` (prior loop).
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
