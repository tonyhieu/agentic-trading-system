"""afg-f-l7 — aggressor-flow gate with 30 s look-back window.

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 7. Starting point: `afg-f-l6` (prior loop).
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
