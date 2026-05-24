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
    "afg-f-l1": (
        "execution_algos.afg-f-l1",
        "get_execution_algorithm",
    ),
    "afg-f-l2": (
        "execution_algos.afg-f-l2",
        "get_execution_algorithm",
    ),
    "afg-f-l3": (
        "execution_algos.afg-f-l3",
        "get_execution_algorithm",
    ),
    "afg-f-l4": (
        "execution_algos.afg-f-l4",
        "get_execution_algorithm",
    ),
    "afg-f-l5": (
        "execution_algos.afg-f-l5",
        "get_execution_algorithm",
    ),
    "afg-f-l6": (
        "execution_algos.afg-f-l6",
        "get_execution_algorithm",
    ),
    "afg-f-l7": (
        "execution_algos.afg-f-l7",
        "get_execution_algorithm",
    ),
    "afg-f-l8": (
        "execution_algos.afg-f-l8",
        "get_execution_algorithm",
    ),
    "vrs-m-l1": (
        "execution_algos.vrs-m-l1",
        "get_execution_algorithm",
    ),
    "vrs-m-l2": (
        "execution_algos.vrs-m-l2",
        "get_execution_algorithm",
    ),
    "vrs-m-l3": (
        "execution_algos.vrs-m-l3",
        "get_execution_algorithm",
    ),
    "vrs-m-l4": (
        "execution_algos.vrs-m-l4",
        "get_execution_algorithm",
    ),
    "vrs-m-l5": (
        "execution_algos.vrs-m-l5",
        "get_execution_algorithm",
    ),
    "vrs-m-l6": (
        "execution_algos.vrs-m-l6",
        "get_execution_algorithm",
    ),
    "vrs-m-l7": (
        "execution_algos.vrs-m-l7",
        "get_execution_algorithm",
    ),
    "vrs-m-l8": (
        "execution_algos.vrs-m-l8",
        "get_execution_algorithm",
    ),
    "vrs-b-l1": (
        "execution_algos.vrs-b-l1",
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
    "ptg-f-l1": (
        "execution_algos.ptg-f-l1",
        "get_execution_algorithm",
    ),
    "ptg-f-l2": (
        "execution_algos.ptg-f-l2",
        "get_execution_algorithm",
    ),
    "ptg-f-l3": (
        "execution_algos.ptg-f-l3",
        "get_execution_algorithm",
    ),
    "ptg-f-l4": (
        "execution_algos.ptg-f-l4",
        "get_execution_algorithm",
    ),
    "ptg-f-l5": (
        "execution_algos.ptg-f-l5",
        "get_execution_algorithm",
    ),
    "ptg-f-l6": (
        "execution_algos.ptg-f-l6",
        "get_execution_algorithm",
    ),
    "ptg-f-l7": (
        "execution_algos.ptg-f-l7",
        "get_execution_algorithm",
    ),
    "ptg-f-l8": (
        "execution_algos.ptg-f-l8",
        "get_execution_algorithm",
    ),
    "afg-b-l1": (
        "execution_algos.afg-b-l1",
        "get_execution_algorithm",
    ),
    "afg-b-l2": (
        "execution_algos.afg-b-l2",
        "get_execution_algorithm",
    ),
    "afg-b-l3": (
        "execution_algos.afg-b-l3",
        "get_execution_algorithm",
    ),
    "afg-b-l4": (
        "execution_algos.afg-b-l4",
        "get_execution_algorithm",
    ),
    "afg-b-l5": (
        "execution_algos.afg-b-l5",
        "get_execution_algorithm",
    ),
    "afg-b-l6": (
        "execution_algos.afg-b-l6",
        "get_execution_algorithm",
    ),
    "afg-b-l7": (
        "execution_algos.afg-b-l7",
        "get_execution_algorithm",
    ),
    "afg-b-l8": (
        "execution_algos.afg-b-l8",
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
