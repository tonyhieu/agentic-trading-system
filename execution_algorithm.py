from nautilus_trader.execution.algorithm import ExecAlgorithm


class SimpleExecutionAlgorithm(ExecAlgorithm):
    """
    A custom execution algorithm that demonstrates simple order handling.
    Instead of TWAP, it immediately executes the incoming order in full.
    """

    def on_start(self) -> None:
        self.log.info("SimpleExecutionAlgorithm started.")

    def on_reset(self) -> None:
        pass

    def on_order(self, order) -> None:
        """
        Intercepts incoming orders from strategies.
        """
        self.log.info(f"SimpleExecutionAlgorithm handling order: {order.client_order_id} for {order.quantity}")
        
        # In a more complex algorithmic execution, you would use:
        # self.spawn_market(...) or self.spawn_limit(...) to break the order into chunks
        # and manage them with self.clock.set_timer(...)
        
        # Here we just pass the order through directly to the matching engine/venue backend
        self.submit_order(order)


def get_execution_algorithm():
    """
    Instantiate and return the custom execution algorithm.
    """
    return SimpleExecutionAlgorithm()
