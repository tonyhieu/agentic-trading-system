"""Session-close-suppress wrapper on vol-regime-sizer (sip-vrs-l2).

Layers a session-close gate on top of the parent vol-regime-sizer's
existing volatility-regime submission probability. In the final
`close_window` seconds before the configured session-end UTC time,
open-leg orders are suppressed (hard skip). Reduce-only orders are
exempt (intraday_flat compliance).
"""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
