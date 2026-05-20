from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SimpleExecutionAlgorithmConfig(ExecAlgorithmConfig):
    pass


class SimpleExecutionAlgorithm(ExecAlgorithm):
    """
    A custom execution algorithm that demonstrates simple order handling.
    It immediately executes the incoming order in full.
    """

    def on_start(self) -> None:
        self.log.info("SimpleExecutionAlgorithm started.")

    def on_reset(self) -> None:
        pass

    def on_order(self, order) -> None:
        """
        Intercepts incoming orders from strategies.
        """
        self.log.info(
            f"SimpleExecutionAlgorithm handling order: {order.client_order_id} for {order.quantity}"
        )

        # Pass the order directly to the venue backend.
        self.submit_order(order)


def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO"):
    """
    Instantiate and return the custom execution algorithm.
    """
    config = SimpleExecutionAlgorithmConfig(exec_algorithm_id=ExecAlgorithmId(exec_id))
    return SimpleExecutionAlgorithm(config=config)
