from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class ReduceOnlyCooldownConfig(ExecAlgorithmConfig, frozen=True):
    defer_ms: int = 50


class ReduceOnlyCooldownAlgorithm(ExecAlgorithm):
    """
    Defer every is_reduce_only order by ``defer_ms`` milliseconds via a clock
    alert. Non-reduce-only (opening) orders pass through unchanged.

    See ``execution_algos/reduce-only-cooldown/NOTES.md`` for the full
    hypothesis, including the look-ahead-bias check.
    """

    def __init__(self, config: ReduceOnlyCooldownConfig) -> None:
        super().__init__(config=config)
        self._defer_ns: int = int(config.defer_ms) * 1_000_000
        self._deferred: dict[str, object] = {}

    def on_start(self) -> None:
        self.log.info(
            f"ReduceOnlyCooldownAlgorithm started (defer_ms={self._defer_ns // 1_000_000})."
        )

    def on_reset(self) -> None:
        self._deferred.clear()

    def _alert_name(self, order) -> str:
        return f"roc-{order.client_order_id.value}"

    def on_order(self, order) -> None:
        if not order.is_reduce_only:
            self.submit_order(order)
            return

        if self._defer_ns == 0:
            self.submit_order(order)
            return

        deadline_ns = self.clock.timestamp_ns() + self._defer_ns
        name = self._alert_name(order)
        self._deferred[name] = order
        self.clock.set_time_alert_ns(
            name=name,
            alert_time_ns=deadline_ns,
            callback=self._on_alert,
        )

    def _on_alert(self, event) -> None:
        name = getattr(event, "name", None)
        if name is None:
            return
        order = self._deferred.pop(name, None)
        if order is not None:
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    defer_ms: int = 50,
) -> ReduceOnlyCooldownAlgorithm:
    config = ReduceOnlyCooldownConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        defer_ms=defer_ms,
    )
    return ReduceOnlyCooldownAlgorithm(config=config)
