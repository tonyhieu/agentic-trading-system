"""afg-pc-r1: Flow-Burst Gate execution algorithm (refinement of aggressor-flow-gate)."""

from .execution_algorithm import (
    AFGPCR1Algorithm,
    AFGPCR1Config,
    get_execution_algorithm,
)

__all__ = [
    "AFGPCR1Algorithm",
    "AFGPCR1Config",
    "get_execution_algorithm",
]
