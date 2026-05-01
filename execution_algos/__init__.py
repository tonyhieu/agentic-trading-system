"""Execution algorithm package."""

from importlib import import_module
from collections.abc import Callable
from typing import Any

_EXEC_ALGORITHM_FACTORIES: dict[str, tuple[str, str]] = {
    "simple": (
        "execution_algos.simple_execution_strategy",
        "get_execution_algorithm",
    ),
}


def _normalize_algorithm_name(algorithm_name: str) -> str:
    return algorithm_name.replace("-", "_")


def _resolve_execution_factory(algorithm_name: str) -> Callable[..., Any]:
    if algorithm_name in _EXEC_ALGORITHM_FACTORIES:
        module_path, factory_name = _EXEC_ALGORITHM_FACTORIES[algorithm_name]
        module = import_module(module_path)
        return getattr(module, factory_name)

    module_name = _normalize_algorithm_name(algorithm_name)
    module_path = f"execution_algos.{module_name}"

    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name == module_path:
            raise KeyError(algorithm_name) from exc
        raise

    try:
        return getattr(module, "get_execution_algorithm")
    except AttributeError as exc:
        raise AttributeError(
            f"Dynamic execution algorithm '{algorithm_name}' was found at "
            f"{module_path}, but it does not expose get_execution_algorithm. "
            f"Add this to execution_algos/{module_name}/__init__.py:\n"
            f"from .execution_algorithm import get_execution_algorithm"
        ) from exc


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
                f"Available algorithms: {available}. "
                f"For dynamic algorithms, create package "
                f"execution_algos/{_normalize_algorithm_name(algorithm_name)}/ "
                f"with get_execution_algorithm exposed in __init__.py."
            ) from exc

        return factory(*args, **kwargs)

    @staticmethod
    def available() -> tuple[str, ...]:
        return tuple(sorted(_EXEC_ALGORITHM_FACTORIES))


def create_execution_algorithm(algorithm_name: str, *args: Any, **kwargs: Any) -> Any:
    """Create an execution algorithm using the registered or dynamic algorithm name."""
    return ExecutionAlgorithmFactory.create(algorithm_name, *args, **kwargs)


__all__ = ["ExecutionAlgorithmFactory", "create_execution_algorithm"]