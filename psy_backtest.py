import MetaTrader5 as mt5
import tkinter as tk
from tkinter import messagebox, Toplevel
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import pandas as pd
import pytz
from datetime import datetime

# Connect to MetaTrader 5
if not mt5.initialize():
    print("MetaTrader5 initialization failed")
    mt5.shutdown()

# Function to fetch historical M1 data from MT5
def fetch_historical_data(symbol, start_date, end_date):
    # Convert dates to MetaTrader 5 format (UTC timezone)
    start_date = pd.Timestamp(start_date).tz_localize(pytz.timezone('America/New_York')).tz_convert(pytz.UTC)
    end_date = pd.Timestamp(end_date).tz_localize(pytz.timezone('America/New_York')).tz_convert(pytz.UTC)
    
    # Request M1 historical data
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start_date.to_pydatetime(), end_date.to_pydatetime())
    
    # Create DataFrame
    rates_frame = pd.DataFrame(rates)
    rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')
    
    # Convert time to New York timezone
    ny_tz = pytz.timezone('America/New_York')
    rates_frame['time'] = rates_frame['time'].dt.tz_localize(pytz.UTC).dt.tz_convert(ny_tz)
    
    return rates_frame[['time', 'open', 'high', 'low', 'close']].rename(columns={'time': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})

# Function to approximate the price to the nearest psychological level
def approximate_price(price):
    # Extract the fractional part (e.g., for 1.23158, get .23158)
    fractional = price - int(price)
    
    # Convert fractional part to pips (e.g., 0.23158 becomes 231.58 pips)
    pips = fractional * 10000

    # Determine which range the pips fall into and round accordingly
    if pips % 100 < 40:
        # Round down to the nearest "00" level
        pips = (pips // 100) * 100
    elif 40 <= pips % 100 <= 69:
        # Round to the nearest "50" level
        pips = (pips // 100) * 100 + 50
    else:
        # Round up to the next "00" level
        pips = ((pips // 100) + 1) * 100
    
    # Convert back to price format
    approximated_price = int(price) + (pips / 10000)
    
    return round(approximated_price, 5)


# Function to perform the backtest using actual historical M1 price movements
def run_backtest(symbol, start_date, end_date):
    global cumulative_profit, account_balance
    
    # Fetch historical data
    data = fetch_historical_data(symbol, start_date, end_date)
    
    # Initialize tracking variables
    total_trades = 0
    wins = 0
    losses = 0
    total_RR = 0
    account_balance = 1000  # Starting balance of $1000
    cumulative_profit = []
    trade_details = []  # To store detailed info about each trade

    # Iterate over each 8:00 AM candle within the fetched data
    for i in range(len(data)):
        current_row = data.iloc[i]
        open_price = current_row['Open']
        date = current_row['Date']
        
        # We are only interested in 8:00 AM candles (New York Time)
        if date.hour == 8 and date.minute == 0 and date.weekday() < 5:
            approx_price = approximate_price(open_price)
            
            # Determine levels to watch for a 15-pip move in either direction
            upper_level = round(approx_price + 0.0015, 5)  # 15 pips above the approximated price
            lower_level = round(approx_price - 0.0015, 5)  # 15 pips below the approximated price
            stop_loss = 0.0010  # 10 pips stop loss
            take_profit = 0.0050  # 50 pips take profit (5R)
            
            # Filter data from the current row onwards
            trade_data = data[i:]
            
            # Flags to determine if a trade is opened
            trade_opened = False
            hit_tp = False
            hit_sl = False
            trade_type = ""  # 'BUY' or 'SELL'

            # Monitor price movements for trade setup
            for j, row in trade_data.iterrows():
                if not trade_opened:
                    # Check for a 15-pip move to trigger a trade
                    if row['High'] >= upper_level:  # Price moves up 15 pips -> SELL
                        trade_opened = True
                        trade_type = "SELL"
                        entry_price = upper_level
                        tp_price = round(entry_price - take_profit, 5)  # TP for SELL
                        sl_price = round(entry_price + stop_loss, 5)  # SL for SELL
                    elif row['Low'] <= lower_level:  # Price moves down 15 pips -> BUY
                        trade_opened = True
                        trade_type = "BUY"
                        entry_price = lower_level
                        tp_price = round(entry_price + take_profit, 5)  # TP for BUY
                        sl_price = round(entry_price - stop_loss, 5)  # SL for BUY
                else:
                    # Check if TP or SL is hit after a trade is opened
                    if trade_type == "SELL":
                        if row['Low'] <= tp_price:  # TP hit
                            hit_tp = True
                            break
                        elif row['High'] >= sl_price:  # SL hit
                            hit_sl = True
                            break
                    elif trade_type == "BUY":
                        if row['High'] >= tp_price:  # TP hit
                            hit_tp = True
                            break
                        elif row['Low'] <= sl_price:  # SL hit
                            hit_sl = True
                            break

            # If a trade was opened, calculate the result
            if trade_opened:
                # Calculate risk per trade (5% of current balance)
                risk_per_trade = round(0.05 * account_balance, 5)
                
                if hit_tp:
                    # Win scenario
                    trade_profit = round(5 * risk_per_trade, 5)  # 5R profit
                    wins += 1
                    total_RR += 5  # 5R profit
                    result = "WIN"
                elif hit_sl:
                    # Loss scenario
                    trade_profit = round(-risk_per_trade, 5)  # 1R loss
                    losses += 1
                    total_RR -= 1  # 1R loss
                    result = "LOSS"
                else:
                    # No hit for SL/TP (This shouldn't happen with M1 data)
                    trade_profit = 0
                    result = "NO HIT"

                account_balance = round(account_balance + trade_profit, 5)
                cumulative_profit.append(account_balance)
                total_trades += 1
                trade_details.append(
                    f"Date: {date.date()}, Entry: {round(entry_price, 5)}, TP: {tp_price}, SL: {sl_price}, Result: {result}"
                )
    
    # Calculate win rate
    win_rate = wins / total_trades if total_trades > 0 else 0
    
    # Update GUI with results
    result_text = (
        f"Total Trades: {total_trades}\n"
        f"Wins: {wins} ({win_rate * 100:.2f}%)\n"
        f"Losses: {losses}\n"
        f"Total RR: {total_RR:.2f}\n"
        f"Final Account Balance: ${account_balance:.2f}\n"
        "\nTrade Details:\n"
        + "\n".join(trade_details)
    )
    
    result_label.config(text=result_text)

# Function to display the account growth chart
def display_chart():
    if not cumulative_profit:
        messagebox.showinfo("No Data", "Please run a backtest first.")
        return
    
    # Create a new window for the chart
    chart_window = Toplevel(window)
    chart_window.title("Account Growth Chart")
    
    # Plotting the account growth
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(cumulative_profit, label='Account Balance', color='blue')
    ax.set_title('Account Growth Over Time')
    ax.set_xlabel('Trades')
    ax.set_ylabel('Account Balance ($)')
    ax.grid(True)
    ax.legend()
    
    # Display the plot in the new window
    canvas = FigureCanvasTkAgg(fig, master=chart_window)
    canvas.draw()
    canvas.get_tk_widget().pack()

# Function to handle the backtest button click
def on_backtest_button_click():
    # Retrieve the start and end dates from the entry fields
    start_date = start_date_entry.get()
    end_date = end_date_entry.get()
    
    # Check if input dates are valid
    if not start_date or not end_date:
        messagebox.showwarning("Input Error", "Please enter both start and end dates.")
        return
    
    try:
        # Run the backtest with the provided symbol, start date, and end date
        run_backtest("GBPUSD", start_date, end_date)  # Replace "EURUSD" with desired symbol if needed
    except Exception as e:
        messagebox.showerror("Backtest Error", f"An error occurred during backtesting: {e}")

# GUI Setup
window = tk.Tk()
window.title("Forex Strategy Backtester")
window.geometry("400x600")
window.configure(bg='#f0f0f0')

# Header
header_label = tk.Label(window, text="Forex Strategy Backtester", font=("Arial", 16), bg='#f0f0f0')
header_label.pack(pady=10)

# Input fields
input_frame = tk.Frame(window, bg='#f0f0f0')
input_frame.pack(pady=10)

tk.Label(input_frame, text="Enter start date (YYYY-MM-DD):", bg='#f0f0f0').grid(row=0, column=0, pady=5)
start_date_entry = tk.Entry(input_frame)
start_date_entry.grid(row=0, column=1, pady=5)

tk.Label(input_frame, text="Enter end date (YYYY-MM-DD):", bg='#f0f0f0').grid(row=1, column=0, pady=5)
end_date_entry = tk.Entry(input_frame)
end_date_entry.grid(row=1, column=1, pady=5)

# Backtest button
backtest_button = tk.Button(window, text="Start Backtest", command=on_backtest_button_click, bg='#007acc', fg='white', font=("Arial", 12))
backtest_button.pack(pady=10)

# Chart button
chart_button = tk.Button(window, text="Display Account Growth Chart", command=display_chart, bg='#007acc', fg='white', font=("Arial", 12))
chart_button.pack(pady=10)

# Results display
result_label = tk.Label(window, text="", justify=tk.LEFT, bg='#f0f0f0', font=("Arial", 10), anchor="w")
result_label.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

window.mainloop()

# Shutdown MT5 connection
mt5.shutdown()
