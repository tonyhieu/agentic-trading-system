"""afg-pc-r2: Persistent-Flow AFG with directional-chain (refinement of aggressor-flow-gate)."""

from .execution_algorithm import (
    AFGPCR2Algorithm,
    AFGPCR2Config,
    get_execution_algorithm,
)

__all__ = [
    "AFGPCR2Algorithm",
    "AFGPCR2Config",
    "get_execution_algorithm",
]
