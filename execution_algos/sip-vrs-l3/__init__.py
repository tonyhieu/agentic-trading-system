"""Transient-burst suppression layer (sip-vrs-l3).

Layers an additional skip factor on top of the parent vol-regime-sizer's
gate during fresh volatility bursts (instantaneous vol_ratio meaningfully
above its long-run baseline). Sustained regimes and calm regimes are
unchanged.
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
