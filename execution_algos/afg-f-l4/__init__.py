"""afg-f-l4 — aggressor-flow gate with halved 5 s look-back window.

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 4. Starting point: `afg-f-l3` (prior loop).
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
