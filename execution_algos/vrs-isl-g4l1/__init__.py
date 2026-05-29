"""Chop + rolling-spread + size-asymmetry composed gate sizer (island-2, g4l1).

Single-knob retune of vrs-isl-g3l2: size_asym_ratio 1.5 -> 2.0. Everything else
frozen verbatim.
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
