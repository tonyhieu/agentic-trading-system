from decimal import Decimal

from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAPConfig
from nautilus_trader.model import BarType


def get_trading_strategy(instrument_id):
    """
    Configure and instantiate the EMA cross strategy.
    """
    strategy_config = EMACrossTWAPConfig(
        instrument_id=instrument_id,
        bar_type=BarType.from_str("ETHUSDT.BINANCE-250-TICK-LAST-INTERNAL"),
        trade_size=Decimal("0.10"),
        fast_ema_period=10,
        slow_ema_period=20,
        twap_horizon_secs=10.0,
        twap_interval_secs=2.5,
    )
    
    return EMACrossTWAP(config=strategy_config)
