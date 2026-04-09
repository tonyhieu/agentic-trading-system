import pandas as pd

def calculate_implementation_shortfall():
    # 1. Load your execution data
    orders = pd.read_csv('orders_report.csv')

    # 2. Load market data
    # We use trades_df.csv which contains tick trade prices.
    # Columns: timestamp, trade_id, price, quantity, buyer_maker
    market_data = pd.read_csv('trades_df.csv')

    # Ensure consistent datetime types
    # trades_df.csv has strings like '2020-08-14 10:00:00.223000+00:00'
    market_data['timestamp'] = pd.to_datetime(market_data['timestamp'], format='ISO8601')
    
    # orders_report.csv has ts_init in nanoseconds (e.g. 1597400554574000000)
    orders['ts_init_dt'] = pd.to_datetime(orders['ts_init'], unit='ns', utc=True)

    # Ensure both dataframes are sorted by timestamp (Required for merge_asof)
    orders = orders.sort_values('ts_init_dt')
    market_data = market_data.sort_values('timestamp')

    # 3. Perform the 'As Of' Merge
    # This finds the closest market quote BEFORE or EXACTLY AT the ts_init_dt of your order
    merged_data = pd.merge_asof(
        left=orders, 
        right=market_data,
        left_on='ts_init_dt',     # The time your algorithm decided to trade
        right_on='timestamp',     # The market data time
        direction='backward'      # Look backward in time to find the latest valid quote (or trade price)
    )

    # 4. Calculate the Arrival Price
    # Since we are using trades_df (tick data rather than BBO data), 
    # we'll use the last traded price as our arrival price approximation.
    merged_data['arrival_price'] = merged_data['price']

    # 5. Calculate Implementation Shortfall (IS)
    # For BUYS: Cost is how much HIGHER your fill was than the arrival price
    # For SELLS: Cost is how much LOWER your fill was than the arrival price
    merged_data['implementation_shortfall'] = merged_data.apply(
        lambda row: (row['avg_px'] - row['arrival_price']) if row['side'] == 'BUY' 
                    else (row['arrival_price'] - row['avg_px']),
        axis=1
    )

    # Optional: Convert shortfall to basis points (bps) for standardized comparison
    merged_data['shortfall_bps'] = (merged_data['implementation_shortfall'] / merged_data['arrival_price']) * 10000

    results = merged_data[['client_order_id', 'side', 'quantity_x', 'arrival_price', 'avg_px', 'implementation_shortfall', 'shortfall_bps']]
    
    # Clean up column name if quantity overlapped
    if 'quantity_x' in results.columns:
        results = results.rename(columns={'quantity_x': 'quantity'})

    print(results.to_string(index=False))
    
    # Optionally save to file
    results.to_csv('implementation_shortfall.csv', index=False)
    print("\nResults saved to implementation_shortfall.csv")

if __name__ == '__main__':
    calculate_implementation_shortfall()
