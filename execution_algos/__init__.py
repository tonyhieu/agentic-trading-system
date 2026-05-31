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
    "vrs-b-l2": (
        "execution_algos.vrs-b-l2",
        "get_execution_algorithm",
    ),
    "vrs-b-l3": (
        "execution_algos.vrs-b-l3",
        "get_execution_algorithm",
    ),
    "vrs-b-l4": (
        "execution_algos.vrs-b-l4",
        "get_execution_algorithm",
    ),
    "vrs-b-l5": (
        "execution_algos.vrs-b-l5",
        "get_execution_algorithm",
    ),
    "vrs-b-l6": (
        "execution_algos.vrs-b-l6",
        "get_execution_algorithm",
    ),
    "vrs-b-l7": (
        "execution_algos.vrs-b-l7",
        "get_execution_algorithm",
    ),
    "vrs-b-l8": (
        "execution_algos.vrs-b-l8",
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
    "ptg-pc-r5": (
        "execution_algos.ptg-pc-r5",
        "get_execution_algorithm",
    ),
    "ptg-pc-r6": (
        "execution_algos.ptg-pc-r6",
        "get_execution_algorithm",
    ),
    "ptg-pc-r7": (
        "execution_algos.ptg-pc-r7",
        "get_execution_algorithm",
    ),
    "ptg-pc-r8": (
        "execution_algos.ptg-pc-r8",
        "get_execution_algorithm",
    ),
    "vrs-pc-r1": (
        "execution_algos.vrs-pc-r1",
        "get_execution_algorithm",
    ),
    "vrs-pc-r2": (
        "execution_algos.vrs-pc-r2",
        "get_execution_algorithm",
    ),
    "vrs-pc-r3": (
        "execution_algos.vrs-pc-r3",
        "get_execution_algorithm",
    ),
    "vrs-pc-r4": (
        "execution_algos.vrs-pc-r4",
        "get_execution_algorithm",
    ),
    "vrs-pc-r5": (
        "execution_algos.vrs-pc-r5",
        "get_execution_algorithm",
    ),
    "vrs-pc-r6": (
        "execution_algos.vrs-pc-r6",
        "get_execution_algorithm",
    ),
    "vrs-pc-r7": (
        "execution_algos.vrs-pc-r7",
        "get_execution_algorithm",
    ),
    "vrs-pc-r8": (
        "execution_algos.vrs-pc-r8",
        "get_execution_algorithm",
    ),
    "ptg-isl-g1l1": (
        "execution_algos.ptg-isl-g1l1",
        "get_execution_algorithm",
    ),
    "ptg-isl-g1l2": (
        "execution_algos.ptg-isl-g1l2",
        "get_execution_algorithm",
    ),
    "ptg-isl-g2l1": (
        "execution_algos.ptg-isl-g2l1",
        "get_execution_algorithm",
    ),
    "ptg-isl-g2l2": (
        "execution_algos.ptg-isl-g2l2",
        "get_execution_algorithm",
    ),
    "ptg-isl-g3l1": (
        "execution_algos.ptg-isl-g3l1",
        "get_execution_algorithm",
    ),
    "ptg-isl-g3l2": (
        "execution_algos.ptg-isl-g3l2",
        "get_execution_algorithm",
    ),
    "afg-isl-g1l1": (
        "execution_algos.afg-isl-g1l1",
        "get_execution_algorithm",
    ),
    "afg-isl-g1l2": (
        "execution_algos.afg-isl-g1l2",
        "get_execution_algorithm",
    ),
    "afg-isl-g2l1": (
        "execution_algos.afg-isl-g2l1",
        "get_execution_algorithm",
    ),
    "afg-isl-g2l2": (
        "execution_algos.afg-isl-g2l2",
        "get_execution_algorithm",
    ),
    "afg-isl-g3l1": (
        "execution_algos.afg-isl-g3l1",
        "get_execution_algorithm",
    ),
    "afg-isl-g3l2": (
        "execution_algos.afg-isl-g3l2",
        "get_execution_algorithm",
    ),
    "vrs-isl-g1l1": (
        "execution_algos.vrs-isl-g1l1",
        "get_execution_algorithm",
    ),
    "vrs-isl-g1l2": (
        "execution_algos.vrs-isl-g1l2",
        "get_execution_algorithm",
    ),
    "vrs-isl-g2l1": (
        "execution_algos.vrs-isl-g2l1",
        "get_execution_algorithm",
    ),
    "vrs-isl-g2l2": (
        "execution_algos.vrs-isl-g2l2",
        "get_execution_algorithm",
    ),
    "vrs-isl-g3l1": (
        "execution_algos.vrs-isl-g3l1",
        "get_execution_algorithm",
    ),
    "vrs-isl-g3l2": (
        "execution_algos.vrs-isl-g3l2",
        "get_execution_algorithm",
    ),
    "ptg-isl-g4l1": (
        "execution_algos.ptg-isl-g4l1",
        "get_execution_algorithm",
    ),
    "ptg-isl-g4l2": (
        "execution_algos.ptg-isl-g4l2",
        "get_execution_algorithm",
    ),
    "afg-isl-g4l1": (
        "execution_algos.afg-isl-g4l1",
        "get_execution_algorithm",
    ),
    "afg-isl-g4l2": (
        "execution_algos.afg-isl-g4l2",
        "get_execution_algorithm",
    ),
    "vrs-isl-g4l1": (
        "execution_algos.vrs-isl-g4l1",
        "get_execution_algorithm",
    ),
    "vrs-isl-g4l2": (
        "execution_algos.vrs-isl-g4l2",
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
    "vrs-f-l1": (
        "execution_algos.vrs-f-l1",
        "get_execution_algorithm",
    ),
    "vrs-f-l2": (
        "execution_algos.vrs-f-l2",
        "get_execution_algorithm",
    ),
    "vrs-f-l3": (
        "execution_algos.vrs-f-l3",
        "get_execution_algorithm",
    ),
    "vrs-f-l4": (
        "execution_algos.vrs-f-l4",
        "get_execution_algorithm",
    ),
    "vrs-f-l5": (
        "execution_algos.vrs-f-l5",
        "get_execution_algorithm",
    ),
    "vrs-f-l6": (
        "execution_algos.vrs-f-l6",
        "get_execution_algorithm",
    ),
    "vrs-f-l7": (
        "execution_algos.vrs-f-l7",
        "get_execution_algorithm",
    ),
    "vrs-f-l8": (
        "execution_algos.vrs-f-l8",
        "get_execution_algorithm",
    ),
    "ptg-b-l1": (
        "execution_algos.ptg-b-l1",
        "get_execution_algorithm",
    ),
    "ptg-b-l2": (
        "execution_algos.ptg-b-l2",
        "get_execution_algorithm",
    ),
    "ptg-b-l3": (
        "execution_algos.ptg-b-l3",
        "get_execution_algorithm",
    ),
    "ptg-b-l4": (
        "execution_algos.ptg-b-l4",
        "get_execution_algorithm",
    ),
    "ptg-b-l5": (
        "execution_algos.ptg-b-l5",
        "get_execution_algorithm",
    ),
    "ptg-b-l6": (
        "execution_algos.ptg-b-l6",
        "get_execution_algorithm",
    ),
    "ptg-b-l7": (
        "execution_algos.ptg-b-l7",
        "get_execution_algorithm",
    ),
    "ptg-b-l8": (
        "execution_algos.ptg-b-l8",
        "get_execution_algorithm",
    ),
    "sip-afg-l1": (
        "execution_algos.sip-afg-l1",
        "get_execution_algorithm",
    ),
    "sip-afg-l2": (
        "execution_algos.sip-afg-l2",
        "get_execution_algorithm",
    ),
    "sip-afg-l3": (
        "execution_algos.sip-afg-l3",
        "get_execution_algorithm",
    ),
    "sip-afg-l4": (
        "execution_algos.sip-afg-l4",
        "get_execution_algorithm",
    ),
    "sip-afg-l5": (
        "execution_algos.sip-afg-l5",
        "get_execution_algorithm",
    ),
    "sip-afg-l6": (
        "execution_algos.sip-afg-l6",
        "get_execution_algorithm",
    ),
    "sip-afg-l7": (
        "execution_algos.sip-afg-l7",
        "get_execution_algorithm",
    ),
    "sip-afg-l8": (
        "execution_algos.sip-afg-l8",
        "get_execution_algorithm",
    ),
    "sip-vrs-l1": (
        "execution_algos.sip-vrs-l1",
        "get_execution_algorithm",
    ),
    "sip-vrs-l2": (
        "execution_algos.sip-vrs-l2",
        "get_execution_algorithm",
    ),
    "sip-vrs-l3": (
        "execution_algos.sip-vrs-l3",
        "get_execution_algorithm",
    ),
    "sip-vrs-l4": (
        "execution_algos.sip-vrs-l4",
        "get_execution_algorithm",
    ),
    "sip-vrs-l5": (
        "execution_algos.sip-vrs-l5",
        "get_execution_algorithm",
    ),
    "sip-vrs-l6": (
        "execution_algos.sip-vrs-l6",
        "get_execution_algorithm",
    ),
    "sip-vrs-l7": (
        "execution_algos.sip-vrs-l7",
        "get_execution_algorithm",
    ),
    "sip-vrs-l8": (
        "execution_algos.sip-vrs-l8",
        "get_execution_algorithm",
    ),
    "sip-ptg-l1": (
        "execution_algos.sip-ptg-l1",
        "get_execution_algorithm",
    ),
    "sip-ptg-l2": (
        "execution_algos.sip-ptg-l2",
        "get_execution_algorithm",
    ),
    "sip-ptg-l3": (
        "execution_algos.sip-ptg-l3",
        "get_execution_algorithm",
    ),
    "sip-ptg-l4": (
        "execution_algos.sip-ptg-l4",
        "get_execution_algorithm",
    ),
    "sip-ptg-l5": (
        "execution_algos.sip-ptg-l5",
        "get_execution_algorithm",
    ),
    "sip-ptg-l6": (
        "execution_algos.sip-ptg-l6",
        "get_execution_algorithm",
    ),
    "sip-ptg-l7": (
        "execution_algos.sip-ptg-l7",
        "get_execution_algorithm",
    ),
    "sip-ptg-l8": (
        "execution_algos.sip-ptg-l8",
        "get_execution_algorithm",
    ),
    "sig-isl-g1l1": (
        "execution_algos.sig-isl-g1l1",
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
