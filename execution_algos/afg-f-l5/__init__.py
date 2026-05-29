"""afg-f-l5 — aggressor-flow gate with lengthened 15 s look-back window.

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 5. Starting point: `afg-f-l4` (prior loop).
"""
from .execution_algorithm import get_execution_algorithm

__all__ = ["get_execution_algorithm"]
