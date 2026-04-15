"""
Sample Momentum Trading Strategy
A simple momentum-based trading strategy for testing the snapshot system.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class MomentumStrategy:
    """
    Simple momentum strategy that buys when price momentum is positive
    and sells when momentum is negative.
    """
    
    def __init__(self, lookback_period=20, holding_period=5):
        """
        Initialize the momentum strategy.
        
        Args:
            lookback_period: Number of days to calculate momentum (default: 20)
            holding_period: Number of days to hold positions (default: 5)
        """
        self.lookback_period = lookback_period
        self.holding_period = holding_period
        self.positions = []
        
    def calculate_momentum(self, prices):
        """
        Calculate price momentum over the lookback period.
        
        Args:
            prices: Series of historical prices
            
        Returns:
            float: Momentum score (percentage change)
        """
        if len(prices) < self.lookback_period:
            return 0.0
        
        current_price = prices.iloc[-1]
        past_price = prices.iloc[-self.lookback_period]
        momentum = (current_price - past_price) / past_price
        
        return momentum
    
    def generate_signal(self, prices):
        """
        Generate trading signal based on momentum.
        
        Args:
            prices: Series of historical prices
            
        Returns:
            str: 'BUY', 'SELL', or 'HOLD'
        """
        momentum = self.calculate_momentum(prices)
        
        if momentum > 0.02:  # 2% positive momentum threshold
            return 'BUY'
        elif momentum < -0.02:  # 2% negative momentum threshold
            return 'SELL'
        else:
            return 'HOLD'
    
    def backtest(self, price_data, initial_capital=100000):
        """
        Run backtest on historical price data.
        
        Args:
            price_data: DataFrame with 'date' and 'close' columns
            initial_capital: Starting capital in dollars
            
        Returns:
            dict: Backtest results including metrics and trade history
        """
        capital = initial_capital
        shares = 0
        trades = []
        equity_curve = []
        
        for i in range(self.lookback_period, len(price_data)):
            current_date = price_data.iloc[i]['date']
            current_price = price_data.iloc[i]['close']
            prices = price_data.iloc[:i+1]['close']
            
            signal = self.generate_signal(prices)
            
            # Execute trade based on signal
            if signal == 'BUY' and shares == 0:
                shares = capital / current_price
                trades.append({
                    'date': current_date,
                    'action': 'BUY',
                    'price': current_price,
                    'shares': shares,
                    'capital': 0
                })
                capital = 0
                
            elif signal == 'SELL' and shares > 0:
                capital = shares * current_price
                trades.append({
                    'date': current_date,
                    'action': 'SELL',
                    'price': current_price,
                    'shares': 0,
                    'capital': capital
                })
                shares = 0
            
            # Track equity
            total_equity = capital + (shares * current_price)
            equity_curve.append({
                'date': current_date,
                'equity': total_equity
            })
        
        # Calculate final equity
        final_price = price_data.iloc[-1]['close']
        final_equity = capital + (shares * final_price)
        
        # Calculate performance metrics
        total_return = (final_equity - initial_capital) / initial_capital
        
        # Calculate Sharpe ratio (simplified)
        equity_df = pd.DataFrame(equity_curve)
        returns = equity_df['equity'].pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if len(returns) > 0 else 0
        
        # Calculate max drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Calculate win rate
        winning_trades = sum(1 for i in range(1, len(trades)) 
                           if trades[i]['action'] == 'SELL' 
                           and trades[i]['capital'] > trades[i-1]['capital'])
        total_trades = len([t for t in trades if t['action'] == 'SELL'])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        return {
            'total_return': round(total_return * 100, 2),  # as percentage
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_drawdown': round(max_drawdown * 100, 2),  # as percentage
            'win_rate': round(win_rate * 100, 2),  # as percentage
            'total_trades': total_trades,
            'final_equity': round(final_equity, 2),
            'initial_capital': initial_capital,
            'trades': trades[:10],  # First 10 trades for sample
            'equity_curve': equity_curve[:10]  # First 10 points for sample
        }


def generate_sample_data(days=365):
    """Generate sample price data for testing."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # Generate random walk with drift
    returns = np.random.normal(0.0005, 0.02, days)
    prices = 100 * (1 + returns).cumprod()
    
    return pd.DataFrame({
        'date': dates,
        'close': prices
    })


if __name__ == '__main__':
    # Example usage
    print("Running Sample Momentum Strategy Backtest...")
    
    # Generate sample data
    data = generate_sample_data(365)
    
    # Initialize strategy
    strategy = MomentumStrategy(lookback_period=20, holding_period=5)
    
    # Run backtest
    results = strategy.backtest(data, initial_capital=100000)
    
    print(f"\nBacktest Results:")
    print(f"Total Return: {results['total_return']}%")
    print(f"Sharpe Ratio: {results['sharpe_ratio']}")
    print(f"Max Drawdown: {results['max_drawdown']}%")
    print(f"Win Rate: {results['win_rate']}%")
    print(f"Total Trades: {results['total_trades']}")
    print(f"Final Equity: ${results['final_equity']:,.2f}")
    
    print("\nBacktest complete!")


def get_trading_strategy():
    """
    Factory function to create a MomentumStrategy instance.
    """
    return MomentumStrategy()
