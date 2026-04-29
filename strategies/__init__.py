"""Trading strategy package."""

from importlib import import_module
from collections.abc import Callable
from typing import Any

_STRATEGY_FACTORIES: dict[str, tuple[str, str]] = {
    "ema_cross": ("strategies.ema_strategy", "get_trading_strategy"),
    "momentum": ("strategies.sample_momentum_strategy", "get_trading_strategy"),
    "oracle": ("strategies.databento_oracle_strategy", "get_trading_strategy"),
}


def _resolve_strategy_factory(strategy_name: str) -> Callable[..., Any]:
    module_path, factory_name = _STRATEGY_FACTORIES[strategy_name]
    module = import_module(module_path)
    return getattr(module, factory_name)


class StrategyFactory:
    """Factory for creating strategy instances by name."""

    @staticmethod
    def create(strategy_name: str, *args: Any, **kwargs: Any) -> Any:
        try:
            factory = _resolve_strategy_factory(strategy_name)
        except KeyError as exc:
            available = ", ".join(sorted(_STRATEGY_FACTORIES))
            raise ValueError(
                f"Unknown strategy '{strategy_name}'. Available strategies: {available}"
            ) from exc

        return factory(*args, **kwargs)

    @staticmethod
    def available() -> tuple[str, ...]:
        return tuple(sorted(_STRATEGY_FACTORIES))


def create_strategy(strategy_name: str, *args: Any, **kwargs: Any) -> Any:
    """Create a strategy using the registered strategy name."""
    return StrategyFactory.create(strategy_name, *args, **kwargs)


__all__ = ["StrategyFactory", "create_strategy"]
