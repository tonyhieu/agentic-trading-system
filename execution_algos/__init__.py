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
    "position-tier-gate": (
        "execution_algos.position-tier-gate",
        "get_execution_algorithm",
    ),
    "aggressor-flow-gate": (
        "execution_algos.aggressor-flow-gate",
        "get_execution_algorithm",
    ),
    "vol-regime-sizer": (
        "execution_algos.vol-regime-sizer",
        "get_execution_algorithm",
    ),
    "afg-m-l1": (
        "execution_algos.afg-m-l1",
        "get_execution_algorithm",
    ),
    "afg-m-l2": (
        "execution_algos.afg-m-l2",
        "get_execution_algorithm",
    ),
    "afg-m-l3": (
        "execution_algos.afg-m-l3",
        "get_execution_algorithm",
    ),
    "afg-m-l4": (
        "execution_algos.afg-m-l4",
        "get_execution_algorithm",
    ),
    "afg-m-l5": (
        "execution_algos.afg-m-l5",
        "get_execution_algorithm",
    ),
    "afg-m-l6": (
        "execution_algos.afg-m-l6",
        "get_execution_algorithm",
    ),
    "afg-m-l7": (
        "execution_algos.afg-m-l7",
        "get_execution_algorithm",
    ),
    "afg-m-l8": (
        "execution_algos.afg-m-l8",
        "get_execution_algorithm",
    ),
    "vrs-m-l1": (
        "execution_algos.vrs-m-l1",
        "get_execution_algorithm",
    ),
    "ptg-m-l1": (
        "execution_algos.ptg-m-l1",
        "get_execution_algorithm",
    ),
    "ptg-m-l2": (
        "execution_algos.ptg-m-l2",
        "get_execution_algorithm",
    ),
    "ptg-m-l3": (
        "execution_algos.ptg-m-l3",
        "get_execution_algorithm",
    ),
    "ptg-m-l4": (
        "execution_algos.ptg-m-l4",
        "get_execution_algorithm",
    ),
    "ptg-m-l5": (
        "execution_algos.ptg-m-l5",
        "get_execution_algorithm",
    ),
    "ptg-m-l6": (
        "execution_algos.ptg-m-l6",
        "get_execution_algorithm",
    ),
    "ptg-m-l7": (
        "execution_algos.ptg-m-l7",
        "get_execution_algorithm",
    ),
    "ptg-m-l8": (
        "execution_algos.ptg-m-l8",
        "get_execution_algorithm",
    ),
    "afg-pc-r1": (
        "execution_algos.afg-pc-r1",
        "get_execution_algorithm",
    ),
    "afg-pc-r2": (
        "execution_algos.afg-pc-r2",
        "get_execution_algorithm",
    ),
    "afg-pc-r3": (
        "execution_algos.afg-pc-r3",
        "get_execution_algorithm",
    ),
    "afg-pc-r4": (
        "execution_algos.afg-pc-r4",
        "get_execution_algorithm",
    ),
    "afg-pc-r5": (
        "execution_algos.afg-pc-r5",
        "get_execution_algorithm",
    ),
    "afg-pc-r6": (
        "execution_algos.afg-pc-r6",
        "get_execution_algorithm",
    ),
    "afg-pc-r7": (
        "execution_algos.afg-pc-r7",
        "get_execution_algorithm",
    ),
    "afg-pc-r8": (
        "execution_algos.afg-pc-r8",
        "get_execution_algorithm",
    ),
    "ptg-pc-r1": (
        "execution_algos.ptg-pc-r1",
        "get_execution_algorithm",
    ),
    "ptg-pc-r2": (
        "execution_algos.ptg-pc-r2",
        "get_execution_algorithm",
    ),
    "ptg-pc-r3": (
        "execution_algos.ptg-pc-r3",
        "get_execution_algorithm",
    ),
    "ptg-pc-r4": (
        "execution_algos.ptg-pc-r4",
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
