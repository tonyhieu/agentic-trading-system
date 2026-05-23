"""afg-f-l6 — aggressor-flow gate with 20 s look-back window.

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 6. Starting point: `afg-f-l5` (prior loop).
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
