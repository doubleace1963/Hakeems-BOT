import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
import tkinter as tk
from tkinter import scrolledtext
import time
import threading
import logging

RISK_AMOUNT = 150  # Risk $150 per trade
CHECK_INTERVAL = 10  # Time interval in seconds to check conditions

# Set up logging
logging.basicConfig(filename='trading_strategy.log', level=logging.INFO)

def log_message(message):
    logging.info(message)
    results_text.insert(tk.END, message + "\n")

def connect_mt5():
    if not mt5.initialize():
        log_message("MetaTrader5 initialization failed")
        mt5.shutdown()
        return False
    log_message("MetaTrader5 initialized")
    return True

def disconnect_mt5():
    mt5.shutdown()
    log_message("MetaTrader5 connection closed.")

def get_recent_data(symbol):
    try:
        if not mt5.symbol_select(symbol, True):
            log_message(f"Failed to select symbol: {symbol}")
            return None

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 288)  # Last 24 hours of 5-minute candles
        if rates is None or len(rates) == 0:
            log_message(f"Failed to retrieve data for {symbol}")
            return None

        data = pd.DataFrame(rates)
        data['time'] = pd.to_datetime(data['time'], unit='s')
        data['time'] = data['time'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
        data.set_index('time', inplace=True)

        current_day = datetime.now(pytz.timezone('America/New_York')).date()
        data = data[data.index.date == current_day]

        return data
    except Exception as e:
        log_message(f"Error retrieving data for {symbol}: {str(e)}")
        return None

def find_ny925_candle(data):
    try:
        ny925_candle = data.between_time('09:25', '09:25')
        if not ny925_candle.empty:
            return ny925_candle.iloc[0]
        else:
            log_message("No 9:25 AM candle found in the data.")
            return None
    except Exception as e:
        log_message(f"Error finding 9:25 AM candle: {str(e)}")
        return None

def calculate_lot_size(symbol, entry_price, stop_loss):
    try:
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            log_message(f"Failed to get symbol info for {symbol}")
            return 0

        is_jpy_pair = symbol.endswith("JPY")

        if is_jpy_pair:
            usd_jpy_info = mt5.symbol_info("USDJPY")
            if not usd_jpy_info:
                log_message(f"Failed to get symbol info for USDJPY")
                return 0
            usd_jpy_price = usd_jpy_info.bid
            pip_value = (100000 / usd_jpy_price) / 100
            pip_risk = abs(entry_price - stop_loss) / 0.01
        else:
            pip_value = symbol_info.point * symbol_info.trade_contract_size
            pip_risk = abs(entry_price - stop_loss) / symbol_info.point

        lot_size = RISK_AMOUNT / (pip_risk * pip_value)

        min_lot = 0.01
        max_lot = 100.0
        lot_size = round(lot_size, 2)

        if lot_size < min_lot:
            lot_size = min_lot
        elif lot_size > max_lot:
            lot_size = max_lot

        log_message(f"Calculated lot size for {symbol}: {lot_size:.2f}")
        return lot_size
    except Exception as e:
        log_message(f"Error calculating lot size for {symbol}: {str(e)}")
        return 0

def order_exists(symbol, direction, entry_price):
    try:
        orders = mt5.orders_get(symbol=symbol)
        if orders:
            for order in orders:
                order_price = getattr(order, 'price_open', None)
                if order.symbol == symbol and order_price == entry_price:
                    if (direction == "buy" and order.type == mt5.ORDER_TYPE_BUY_LIMIT) or \
                       (direction == "sell" and order.type == mt5.ORDER_TYPE_SELL_LIMIT):
                        return True
        return False
    except Exception as e:
        log_message(f"Error checking existing orders for {symbol}: {str(e)}")
        return False

def apply_strategy(data, ny925_candle, symbol):
    try:
        if ny925_candle is None:
            return "No trade", None, None, None, None

        if ny925_candle['close'] > ny925_candle['open']:
            direction = "sell"
            level = round(ny925_candle['low'], 5)
        else:
            direction = "buy"
            level = round(ny925_candle['high'], 5)

        confirmation_found = False
        trade_invalid_time = ny925_candle.name + timedelta(hours=6)

        for i in range(data.index.get_loc(ny925_candle.name) + 1, len(data)):
            current_candle = data.iloc[i]

            if current_candle.name > trade_invalid_time:
                return "No trade", level, None, None, "Invalid (Time Expired)"

            if not confirmation_found:
                if direction == "sell" and current_candle['close'] < level:
                    confirmation_found = True
                elif direction == "buy" and current_candle['close'] > level:
                    confirmation_found = True

        if confirmation_found:
            if direction == "buy":
                stop_loss = round(data.loc[ny925_candle.name:current_candle.name]['low'].min(), 5)
                take_profit = round(level + 4 * (level - stop_loss), 5)
            elif direction == "sell":
                stop_loss = round(data.loc[ny925_candle.name:current_candle.name]['high'].max(), 5)
                take_profit = round(level - 4 * (stop_loss - level), 5)

            if not order_exists(symbol, direction, level):
                lot_size = calculate_lot_size(symbol, level, stop_loss)
                place_limit_order(symbol, direction, level, stop_loss, take_profit, trade_invalid_time, lot_size)
                return direction.capitalize(), level, stop_loss, take_profit, f"Limit Order Placed with Lot Size: {lot_size:.2f}"
            else:
                log_message(f"Order for {symbol} at {level} already exists. No new order placed.")
                return direction.capitalize(), level, stop_loss, take_profit, "Order already exists"

        return "No trade", level, None, None, "No Confirmation"
    except Exception as e:
        log_message(f"Error applying strategy for {symbol}: {str(e)}")
        return "No trade", None, None, None, f"Error: {str(e)}"

def place_limit_order(symbol, direction, entry_price, stop_loss, take_profit, expiry_time, lot_size):
    try:
        order_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == "buy" else mt5.ORDER_TYPE_SELL_LIMIT

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": entry_price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 20,
            "magic": 234000,
            "comment": "9:25 AM Strategy",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log_message(f"Failed to place limit order. Retcode: {result.retcode}")
            return

        log_message(f"Limit order placed successfully at {entry_price}.")
        monitor_trade(symbol, result.order, stop_loss, take_profit, expiry_time)
    except Exception as e:
        log_message(f"Error placing limit order for {symbol}: {str(e)}")

def monitor_trade(symbol, order_id, stop_loss, take_profit, expiry_time):
    try:
        while datetime.now(pytz.UTC) < expiry_time:
            positions = mt5.positions_get(symbol=symbol)
            if positions:
                for position in positions:
                    if position.ticket == order_id:
                        log_message(f"Trade active for {symbol}: SL = {stop_loss}, TP = {take_profit}")
                        if position.price_open >= take_profit:
                            log_message(f"Trade hit Take Profit for {symbol}")
                            return "win"
                        elif position.price_open <= stop_loss:
                            log_message(f"Trade hit Stop Loss for {symbol}")
                            return "loss"
            time.sleep(60)

        log_message(f"Trade expired without hitting TP/SL for {symbol}.")
        cancel_order(order_id)
        return "no outcome"
    except Exception as e:
        log_message(f"Error monitoring trade for {symbol}: {str(e)}")
        return "error"

def cancel_order(order_id):
    try:
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order_id,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log_message(f"Failed to cancel order. Retcode: {result.retcode}")
        else:
            log_message(f"Order {order_id} canceled due to expiry.")
    except Exception as e:
        log_message(f"Error canceling order {order_id}: {str(e)}")

def print_time_before_925():
    now = datetime.now(pytz.timezone('America/New_York'))
    ny925 = now.replace(hour=9, minute=25, second=0, microsecond=0)

    if now < ny925:
        time_remaining = ny925 - now
        hours, remainder = divmod(time_remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        log_message(f"Time remaining before 9:25 AM: {hours} hours, {minutes} minutes")
    else:
        log_message("It's past 9:25 AM. Strategy will run tomorrow.")

stop_flag = False

def continuous_monitoring():
    global stop_flag

    while not stop_flag:
        if connect_mt5():
            symbols = symbol_entry.get().split(',')
            results_text.delete('1.0', tk.END)

            print_time_before_925()

            for symbol in symbols:
                symbol = symbol.strip()

                log_message(f"Processing symbol: {symbol}")
                data = get_recent_data(symbol)

                if data is not None:
                    ny925_candle = find_ny925_candle(data)
                    direction, level, stop_loss, take_profit, trade_result = apply_strategy(data, ny925_candle, symbol)

                    log_message(f"Symbol: {symbol}")
                    log_message(f"Trade: {direction}")
                    log_message(f"Level: {level}")
                    log_message(f"Stop Loss: {stop_loss}")
                    log_message(f"Take Profit: {take_profit}")
                    log_message(f"Result: {trade_result}")
                    log_message("-----------------------------------")

            time.sleep(CHECK_INTERVAL)  # Wait before the next check
        else:
            log_message("Attempting to reconnect to MetaTrader 5...")
            time.sleep(5)  # Retry after a delay

    disconnect_mt5()

def stop_execution():
    global stop_flag
    stop_flag = True
    log_message("Stopping the strategy execution...")

def display_results():
    thread = threading.Thread(target=continuous_monitoring)
    thread.start()

# Setup the Tkinter window
root = tk.Tk()
root.title("9:25 AM Strategy Results")

tk.Label(root, text="Symbols (comma-separated):").grid(row=0, column=0, padx=10, pady=5, sticky='e')
symbol_entry = tk.Entry(root)
symbol_entry.grid(row=0, column=1, padx=10, pady=5)

results_text = scrolledtext.ScrolledText(root, width=60, height=20, wrap=tk.WORD)
results_text.grid(column=0, row=2, columnspan=3, padx=10, pady=10)

run_button = tk.Button(root, text="Run Strategy", command=display_results)
run_button.grid(column=0, row=1, padx=10, pady=10)

stop_button = tk.Button(root, text="Stop", command=stop_execution)
stop_button.grid(column=1, row=1, padx=10, pady=10)

root.mainloop()
