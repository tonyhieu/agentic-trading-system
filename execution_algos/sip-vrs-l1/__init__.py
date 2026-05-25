"""Directional-headwind probabilistic gate (sip-vrs-l1).

Replaces the parent vol-regime-sizer's unsigned vol-ratio gate with a
signed-drift gate that conditions skip probability on whether recent
mid-drift is *against* the order side.
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
