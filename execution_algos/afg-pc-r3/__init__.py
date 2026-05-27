"""afg-pc-r3: Threshold-Lowered AFG with thin-market floor (refinement of aggressor-flow-gate)."""

from .execution_algorithm import (
    AFGPCR3Algorithm,
    AFGPCR3Config,
    get_execution_algorithm,
)

__all__ = [
    "AFGPCR3Algorithm",
    "AFGPCR3Config",
    "get_execution_algorithm",
]
