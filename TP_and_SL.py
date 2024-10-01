import MetaTrader5 as mt5
import pandas as pd
import time

# Connect to MT5
if not mt5.initialize():
    print("initialize() failed, error code =", mt5.last_error())
    quit()

def get_lowest_low(symbol, timeframe, n_candles):
    # Get the last n_candles from the current candle
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_candles)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    return df['low'].min()

def get_highest_high(symbol, timeframe, n_candles):
    # Get the last n_candles from the current candle
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_candles)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    return df['high'].max()

def set_sl_tp(ticket, sl_price, tp_price):
    # Modify the order to set stop loss and take profit
    request = {
        'action': mt5.TRADE_ACTION_SLTP,
        'position': ticket,
        'sl': sl_price,
        'tp': tp_price
    }
    result = mt5.order_send(request)
    return result

def has_sl_tp_set(position):
    # Check if both stop loss and take profit are set
    return position.sl != 0.0 and position.tp != 0.0

def main():
    monitored_orders = set()

    while True:
        # Get current open positions
        positions = mt5.positions_get()
        for pos in positions:
            ticket = pos.ticket
            if ticket not in monitored_orders:
                if has_sl_tp_set(pos):
                    monitored_orders.add(ticket)
                    print(f"Order {ticket} already has SL and TP set.")
                    continue

                symbol = pos.symbol
                order_type = pos.type
                price_open = pos.price_open

                if order_type in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT):
                    # Calculate Stop Loss for Buy
                    lowest_low = get_lowest_low(symbol, mt5.TIMEFRAME_H1, 24)
                    if lowest_low is not None:
                        sl_price = lowest_low
                        # Calculate Take Profit
                        risk = price_open - sl_price
                        tp_price = price_open + (risk * 3)

                        # Set SL and TP
                        result = set_sl_tp(ticket, sl_price, tp_price)
                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            monitored_orders.add(ticket)
                            print(f"Set SL={sl_price} and TP={tp_price} for order {ticket}")
                        else:
                            print(f"Failed to set SL/TP for order {ticket}: {result.comment}")
                
                elif order_type in (mt5.ORDER_TYPE_SELL, mt5.ORDER_TYPE_SELL_LIMIT):
                    # Calculate Stop Loss for Sell
                    highest_high = get_highest_high(symbol, mt5.TIMEFRAME_H1, 24)
                    if highest_high is not None:
                        sl_price = highest_high
                        # Calculate Take Profit
                        risk = sl_price - price_open
                        tp_price = price_open - (risk * 3)

                        # Set SL and TP
                        result = set_sl_tp(ticket, sl_price, tp_price)
                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            monitored_orders.add(ticket)
                            print(f"Set SL={sl_price} and TP={tp_price} for order {ticket}")
                        else:
                            print(f"Failed to set SL/TP for order {ticket}: {result.comment}")
        
        # Wait before the next check
        time.sleep(60)

if __name__ == "__main__":
    main()
    mt5.shutdown()
