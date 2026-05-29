"""vrs-pc-r7: sensor-axis pivot — fast_halflife 20 -> 10 ticks atop run-5's
calibration (sensitivity=2.5, min_prob=0.0). Tests whether the sensitivity-axis
plateau (run-5 -> run-6 added only $12) is sensor-speed-limited rather than
addressable-set-exhausted."""

from .execution_algorithm import get_execution_algorithm  # noqa: F401

__all__ = ["get_execution_algorithm"]
