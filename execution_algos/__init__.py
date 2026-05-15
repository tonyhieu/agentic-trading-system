"""Execution algorithm package."""

from importlib import import_module
from collections.abc import Callable
from typing import Any

_EXEC_ALGORITHM_FACTORIES: dict[str, tuple[str, str]] = {
    "simple": (
        "execution_algos.simple_execution_strategy",
        "get_execution_algorithm",
    ),
    "streak-spread-tight": (
        "execution_algos.streak-spread-tight",
        "get_execution_algorithm",
    ),
    "ob-imbalance-gate": (
        "execution_algos.ob-imbalance-gate",
        "get_execution_algorithm",
    ),
    "vol-regime-sizer": (
        "execution_algos.vol-regime-sizer",
        "get_execution_algorithm",
    ),
    "microprice-divergence-gate": (
        "execution_algos.microprice-divergence-gate",
        "get_execution_algorithm",
    ),
    "passive-aggressive-ladder": (
        "execution_algos.passive-aggressive-ladder",
        "get_execution_algorithm",
    ),
    "depth-participation-sizer": (
        "execution_algos.depth-participation-sizer",
        "get_execution_algorithm",
    ),
    "session-clock-gate": (
        "execution_algos.session-clock-gate",
        "get_execution_algorithm",
    ),
    "aggressor-flow-gate": (
        "execution_algos.aggressor-flow-gate",
        "get_execution_algorithm",
    ),
    "cooldown-entry-gate": (
        "execution_algos.cooldown-entry-gate",
        "get_execution_algorithm",
    ),
    "position-tier-gate": (
        "execution_algos.position-tier-gate",
        "get_execution_algorithm",
    ),
    "volume-pace-gate": (
        "execution_algos.volume-pace-gate",
        "get_execution_algorithm",
    ),
}


def _resolve_execution_factory(algorithm_name: str) -> Callable[..., Any]:
    module_path, factory_name = _EXEC_ALGORITHM_FACTORIES[algorithm_name]
    module = import_module(module_path)
    return getattr(module, factory_name)


class ExecutionAlgorithmFactory:
    """Factory for creating execution algorithm instances by name."""

    @staticmethod
    def create(algorithm_name: str, *args: Any, **kwargs: Any) -> Any:
        try:
            factory = _resolve_execution_factory(algorithm_name)
        except KeyError as exc:
            available = ", ".join(sorted(_EXEC_ALGORITHM_FACTORIES))
            raise ValueError(
                f"Unknown execution algorithm '{algorithm_name}'. "
                f"Available algorithms: {available}"
            ) from exc

        return factory(*args, **kwargs)

    @staticmethod
    def available() -> tuple[str, ...]:
        return tuple(sorted(_EXEC_ALGORITHM_FACTORIES))


def create_execution_algorithm(algorithm_name: str, *args: Any, **kwargs: Any) -> Any:
    """Create an execution algorithm using the registered algorithm name."""
    return ExecutionAlgorithmFactory.create(algorithm_name, *args, **kwargs)


__all__ = ["ExecutionAlgorithmFactory", "create_execution_algorithm"]
