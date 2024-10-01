import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
import tkinter as tk
from tkinter import scrolledtext
import time
import threading

RISK_AMOUNT = 150  # Risk $750 per trade

# Connect to MetaTrader 5
def connect_mt5():
    if not mt5.initialize(login = 81142033, server = "Exness-MT5Trial10", password = "Flashpoint1963#"):
        results_text.insert(tk.END, "MetaTrader5 initialization failed\n")
        mt5.shutdown()
        return False
    else:
        results_text.insert(tk.END, "MetaTrader5 initialized\n")
        return True

# Fetch the most recent data and handle timezone conversion
# Fetch the most recent data and handle timezone conversion
def get_recent_data(symbol):
    try:
        if not mt5.symbol_select(symbol, True):
            results_text.insert(tk.END, f"Failed to select symbol: {symbol}\n")
            return None

        # Fetch the most recent 5-minute candles
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 288)  # Last 24 hours of 5-minute candles
        if rates is None or len(rates) == 0:
            results_text.insert(tk.END, f"Failed to retrieve data for {symbol}\n")
            return None

        data = pd.DataFrame(rates)
        data['time'] = pd.to_datetime(data['time'], unit='s')
        data['time'] = data['time'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
        data.set_index('time', inplace=True)

        # Filter data to only include today's date
        current_day = datetime.now(pytz.timezone('America/New_York')).date()
        data = data[data.index.date == current_day]

        return data
    except Exception as e:
        results_text.insert(tk.END, f"Error retrieving data for {symbol}: {str(e)}\n")
        return None

# Identify the 9:25 AM candle
def find_ny925_candle(data):
    try:
        ny925_candle = data.between_time('09:25', '09:25')
        if not ny925_candle.empty:
            return ny925_candle.iloc[0]
        else:
            results_text.insert(tk.END, "No 9:25AM candle found in the data.\n")
            return None
    except Exception as e:
        results_text.insert(tk.END, f"Error finding 9:25 AM candle: {str(e)}\n")
        return None

# Calculate the lot size based on the risk amount and stop loss
def calculate_lot_size(symbol, entry_price, stop_loss):
    try:
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            results_text.insert(tk.END, f"Failed to get symbol info for {symbol}\n")
            return 0

        # Determine if the symbol is a JPY pair
        is_jpy_pair = symbol.endswith("JPY")

        if is_jpy_pair:
            # Fetch the current USD/JPY price for pip value calculation
            usd_jpy_info = mt5.symbol_info("USDJPY")
            if not usd_jpy_info:
                results_text.insert(tk.END, f"Failed to get symbol info for USDJPY\n")
                return 0
            usd_jpy_price = usd_jpy_info.bid  # Current bid price for USD/JPY
            
            # Calculate pip value using USD/JPY rate
            pip_value = (100000 / usd_jpy_price) / 100  # For standard lot
            pip_risk = abs(entry_price - stop_loss) / 0.01  # Pip risk for JPY pairs
        else:
            # Calculation for non-JPY pairs
            pip_value = symbol_info.point * symbol_info.trade_contract_size
            pip_risk = abs(entry_price - stop_loss) / symbol_info.point

        # Calculate the lot size based on the risk amount
        lot_size = RISK_AMOUNT / (pip_risk * pip_value)

        # Adjust lot size to respect the minimum and maximum constraints
        min_lot = 0.01  # Minimum lot size
        max_lot = 100.0  # Maximum lot size

        # Round lot size to two decimal places
        lot_size = round(lot_size, 2)

        # Ensure the lot size is within the allowed range
        if lot_size < min_lot:
            lot_size = min_lot
        elif lot_size > max_lot:
            lot_size = max_lot

        results_text.insert(tk.END, f"Calculated lot size for {symbol}: {lot_size:.2f}\n")

        return lot_size
    except Exception as e:
        results_text.insert(tk.END, f"Error calculating lot size for {symbol}: {str(e)}\n")
        return 0


# Check if an order already exists
# Check if an order already exists
# Check if an order already exists
def order_exists(symbol, direction, entry_price):
    try:
        orders = mt5.orders_get(symbol=symbol)
        if orders:
            for order in orders:
                # Check the correct attribute for price (e.g., 'price_open' instead of 'price')
                order_price = getattr(order, 'price_open', None)
                if order.symbol == symbol and order_price == entry_price:
                    if (direction == "buy" and order.type == mt5.ORDER_TYPE_BUY_LIMIT) or \
                       (direction == "sell" and order.type == mt5.ORDER_TYPE_SELL_LIMIT):
                        return True
        return False
    except Exception as e:
        results_text.insert(tk.END, f"Error checking existing orders for {symbol}: {str(e)}\n")
        return False


# Apply the strategy using limit orders
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
        trade_invalid_time = ny925_candle.name + timedelta(hours= 6)

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

            # Check if the order already exists
            if not order_exists(symbol, direction, level):
                lot_size = calculate_lot_size(symbol, level, stop_loss)
                place_limit_order(symbol, direction, level, stop_loss, take_profit, trade_invalid_time, lot_size)
                return direction.capitalize(), level, stop_loss, take_profit, f"Limit Order Placed with Lot Size: {lot_size:.2f}"
            else:
                results_text.insert(tk.END, f"Order for {symbol} at {level} already exists. No new order placed.\n")
                return direction.capitalize(), level, stop_loss, take_profit, "Order already exists"

        return "No trade", level, None, None, "No Confirmation"
    except Exception as e:
        results_text.insert(tk.END, f"Error applying strategy for {symbol}: {str(e)}\n")
        return "No trade", None, None, None, f"Error: {str(e)}"

# Place a limit order and monitor it
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
            results_text.insert(tk.END, f"Failed to place limit order. Retcode: {result.retcode}\n")
            return

        results_text.insert(tk.END, f"Limit order placed successfully at {entry_price}.\n")

        while datetime.now(pytz.UTC) < expiry_time:
            orders = mt5.orders_get(symbol=symbol)
            if not orders:
                results_text.insert(tk.END, "Limit order was activated and is no longer pending.\n")
                return
            time.sleep(60)

        cancel_order(result.order)
    except Exception as e:
        results_text.insert(tk.END, f"Error placing limit order for {symbol}: {str(e)}\n")

# Cancel the order if not activated
def cancel_order(order_id):
    try:
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order_id,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            results_text.insert(tk.END, f"Failed to cancel order. Retcode: {result.retcode}\n")
        else:
            results_text.insert(tk.END, f"Order {order_id} canceled due to expiry.\n")
    except Exception as e:
        results_text.insert(tk.END, f"Error canceling order {order_id}: {str(e)}\n")

# Print time before 9:25 AM if current time is before 9:25 AM
def print_time_before_925():
    now = datetime.now(pytz.timezone('America/New_York'))
    ny925 = now.replace(hour=9, minute=25, second=0, microsecond=0)
    
    if now < ny925:
        time_remaining = ny925 - now
        hours, remainder = divmod(time_remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        results_text.insert(tk.END, f"Time remaining before 9:25 AM: {hours} hours, {minutes} minutes\n")

# Function to fetch and display results in the GUI
def display_results_thread():
    if connect_mt5():
        symbols = symbol_entry.get().split(',')

        results_text.delete('1.0', tk.END)

        # Print time before 9:25 AM
        print_time_before_925()

        for symbol in symbols:
            symbol = symbol.strip()  # Trim any whitespace around symbols

            results_text.insert(tk.END, f"Processing symbol: {symbol}\n")
            
            data = get_recent_data(symbol)

            if data is not None:
                ny925_candle = find_ny925_candle(data)
                direction, level, stop_loss, take_profit, trade_result = apply_strategy(data, ny925_candle, symbol)

                results_text.insert(tk.END, f"Symbol: {symbol}\n")
                results_text.insert(tk.END, f"Trade: {direction}\n")
                results_text.insert(tk.END, f"Level: {level}\n")
                results_text.insert(tk.END, f"Stop Loss: {stop_loss}\n")
                results_text.insert(tk.END, f"Take Profit: {take_profit}\n")
                results_text.insert(tk.END, f"Result: {trade_result}\n")
                results_text.insert(tk.END, "-----------------------------------\n")

        mt5.shutdown()

def display_results():
    thread = threading.Thread(target=display_results_thread)
    thread.start()

# Setup the Tkinter window
root = tk.Tk()
root.title("9:25 AM Strategy Results")

# Create labels and entries for symbols
tk.Label(root, text="Symbols (comma-separated):").grid(row=0, column=0, padx=10, pady=5, sticky='e')
symbol_entry = tk.Entry(root)
symbol_entry.grid(row=0, column=1, padx=10, pady=5)

# Create a scrolled text box to display results
results_text = scrolledtext.ScrolledText(root, width=60, height=20, wrap=tk.WORD)
results_text.grid(column=0, row=2, columnspan=3, padx=10, pady=10)

# Create a button to trigger the strategy
run_button = tk.Button(root, text="Run Strategy", command=display_results)
run_button.grid(column=0, row=1, columnspan=3, padx=10, pady=10)

# Run the Tkinter main loop
root.mainloop()
