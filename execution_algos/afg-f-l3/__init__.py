"""afg-f-l3 — aggressor-flow gate with threshold tightened across integer boundary (1.0).

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 3. Starting point: `afg-f-l2` (prior loop).
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
