import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
import tkinter as tk
from tkinter import scrolledtext, filedialog
import os
import matplotlib.pyplot as plt
from collections import defaultdictC

# Connect to MetaTrader 5
def connect_mt5():
    """
    Initializes MetaTrader 5 and checks for successful connection.
    Returns True if successful, else False.
    """
    if not mt5.initialize():
        print("MetaTrader5 initialization failed")
        mt5.shutdown()
        return False
    else:
        print("MetaTrader5 initialized")
        return True

# Fetch data and handle timezone conversion
def get_data(symbol, timeframe, start, end):
    """
    Fetches historical data for a given symbol and timeframe.
    Converts the data to America/New_York timezone.
    Returns a pandas DataFrame.
    """
    if not mt5.symbol_select(symbol, True):
        print(f"Failed to select symbol: {symbol}")
        return None

    rates = mt5.copy_rates_range(symbol, timeframe, start, end)
    if rates is None or len(rates) == 0:
        print(f"Failed to retrieve data for {symbol}")
        return None

    data = pd.DataFrame(rates)
    data['time'] = pd.to_datetime(data['time'], unit='s')
    data['time'] = data['time'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
    data.set_index('time', inplace=True)

    return data

# Identify the 9:30 AM candle
def find_ny930_candle(data):
    """
    Identifies the 9:30 AM candle in the provided data.
    Returns the 9:30 AM candle as a pandas Series or None if not found.
    """
    ny930_candle = data.between_time('09:25', '09:25')
    if not ny930_candle.empty:
        return ny930_candle.iloc[0]
    else:
        print("No 9:30 AM candle found in the data.")
        return None

def apply_strategy(data, ny930_candle):
    """
    Applies the trading strategy based on the 9:30 AM candle.
    Waits for a confirmation candle to close above/below the 9:30 AM candle's high/low before
    considering a trade, then waits for the market to retest the level before taking a position.
    If no trade is activated within 6 hours of the 9:30 AM candle's close, the trade is invalid.
    Returns a tuple of the trade direction, level, stop loss, take profit, and result (win/loss).
    """
    if ny930_candle is None:
        return "No trade", None, None, None, None

    # Determine the initial direction based on the 9:30 AM candle
    if ny930_candle['close'] > ny930_candle['open']:
        direction = "sell"
        level = round(ny930_candle['low'], 5)
    else:
        direction = "buy"
        level = round(ny930_candle['high'], 5)

    confirmation_found = False
    retest_occurred = False
    entry_signal = False
    trade_invalid_time = ny930_candle.name + timedelta(hours=6)  # Set the trade invalidation time

    # Loop over candles starting from the one after the 9:30 AM candle
    for i in range(data.index.get_loc(ny930_candle.name) + 1, len(data)):
        current_candle = data.iloc[i]

        # Check if we are beyond the 6-hour window
        if current_candle.name > trade_invalid_time:
            return "No trade", level, None, None, "Invalid (Time Expired)"

        if not confirmation_found:
            # Waiting for a confirmation candle to close beyond the 9:30 AM candle's level
            if direction == "sell" and current_candle['close'] < level:
                confirmation_found = True
            elif direction == "buy" and current_candle['close'] > level:
                confirmation_found = True
        else:
            # After confirmation, waiting for the market to retest the 9:30 AM candle's level
            if direction == "sell" and current_candle['high'] >= level:
                retest_occurred = True
            elif direction == "buy" and current_candle['low'] <= level:
                retest_occurred = True

            # If a retest has occurred, look for entry
            if retest_occurred:
                if direction == "sell" and current_candle['low'] <= level:
                    entry_signal = True
                elif direction == "buy" and current_candle['high'] >= level:
                    entry_signal = True

                if entry_signal:
                    # Entry signal confirmed, setting stop loss and take profit
                    if direction == "buy":
                        lowest_low = round(data.loc[ny930_candle.name:current_candle.name]['low'].min(), 5)
                        stop_loss = lowest_low
                        take_profit = round(level + 4 * (level - stop_loss), 5)
                    elif direction == "sell":
                        highest_high = round(data.loc[ny930_candle.name:current_candle.name]['high'].max(), 5)
                        stop_loss = highest_high
                        take_profit = round(level - 4 * (stop_loss - level), 5)

                    trade_result = evaluate_trade(data.iloc[i+1:], level, stop_loss, take_profit, direction)
                    return direction.capitalize(), level, stop_loss, take_profit, trade_result

    # No definitive trade result within the day, continue to evaluate with the next day's data
    return "No trade", level, None, None, "Open"


# Evaluate the trade
def evaluate_trade(data, entry_price, stop_loss, take_profit, direction):
    """
    Evaluates if the trade is a win or loss based on stop loss and take profit levels.
    Continues evaluating across multiple days if needed.
    Returns 'Win', 'Loss', or 'Open'.
    """
    for _, row in data.iterrows():
        if direction == "buy":
            if row['high'] >= take_profit:
                return "Win"
            elif row['low'] <= stop_loss:
                return "Loss"
        elif direction == "sell":
            if row['low'] <= take_profit:
                return "Win"
            elif row['high'] >= stop_loss:
                return "Loss"
    return "Open"  # Trade neither hit TP nor SL within the data range

# Function to calculate monthly R/R
def calculate_monthly_rr(results):
    """
    Calculate the total R/R for each month.
    Args:
        results (list): List of tuples containing trade results.
    Returns:
        dict: Dictionary with the total R/R for each month.
    """
    monthly_rr = defaultdict(int)
    
    for result in results:
        date_str, trade, level, stop_loss, take_profit, trade_result = result
        date = datetime.strptime(date_str, '%Y-%m-%d')
        month = date.strftime('%Y-%m')
        
        if trade_result == "Win":
            monthly_rr[month] += 4  # Each win is +4 R
        elif trade_result == "Loss":
            monthly_rr[month] -= 1  # Each loss is -1 R

    return monthly_rr
# Function to fetch and display results in the GUI

def display_results():
    """
    Connects to MetaTrader 5, retrieves data for the selected time period,
    applies the 9:30 AM strategy, and displays the results in the GUI.
    Also displays the number of wins, losses, total R made, and win ratio.
    """
    global results  # Make results accessible for exporting to CSV and simulating backtest

    if connect_mt5():
        # Get user inputs for symbol and date range
        symbol = symbol_entry.get()
        start_date_str = start_date_entry.get()
        end_date_str = end_date_entry.get()

        # Parse the date inputs
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        except ValueError:
            results_text.insert(tk.END, "Invalid date format. Please use YYYY-MM-DD.\n")
            return

        start_date = start_date.replace(tzinfo=pytz.UTC)
        end_date = end_date.replace(tzinfo=pytz.UTC)

        results_text.delete('1.0', tk.END)  # Clear previous results

        # Fetch data for the specified range
        data = get_data(symbol, mt5.TIMEFRAME_M5, start_date, end_date + timedelta(days=1))

        if data is not None:
            results_text.insert(tk.END, f"9:30 AM Strategy Results for {symbol} from {start_date_str} to {end_date_str}:\n")
            results = []
            wins = 0
            losses = 0

            for day in pd.date_range(start=start_date, end=end_date, freq='B'):  # 'B' excludes weekends
                day_start = datetime(day.year, day.month, day.day, tzinfo=pytz.UTC)
                day_end = day_start + timedelta(hours=23, minutes=59)

                daily_data = data[day_start:day_end]
                if daily_data is not None and not daily_data.empty:
                    ny930_candle = find_ny930_candle(daily_data)
                    result, level, stop_loss, take_profit, trade_result = apply_strategy(data, ny930_candle)
                    if trade_result == "Open":
                        # Continue to check the next day's data if trade is still open
                        next_day_start = day_end + timedelta(minutes=1)
                        next_day_data = data[next_day_start:]
                        trade_result = evaluate_trade(next_day_data, level, stop_loss, take_profit, result)
                    
                    if trade_result == "Win":
                        wins += 1
                    elif trade_result == "Loss":
                        losses += 1
                    
                    results.append((day.strftime('%Y-%m-%d'), result, level, stop_loss, take_profit, trade_result))

            # Display formatted results
            for result in results:
                date, trade, level, stop_loss, take_profit, trade_result = result
                results_text.insert(tk.END, f"Date: {date}\n")
                results_text.insert(tk.END, f"Trade: {trade}\n")
                results_text.insert(tk.END, f"Level: {level}\n")
                results_text.insert(tk.END, f"Stop Loss: {stop_loss}\n")
                results_text.insert(tk.END, f"Take Profit: {take_profit}\n")
                results_text.insert(tk.END, f"Result: {trade_result}\n")
                results_text.insert(tk.END, "-----------------------------------\n")

            # Calculate total R and win ratio
            total_trades = wins + losses
            total_r = (wins * 4) - losses
            win_ratio = (wins / total_trades) * 100 if total_trades > 0 else 0

            # Display summary of wins, losses, total R, and win ratio
            results_text.insert(tk.END, "\nSummary:\n")
            results_text.insert(tk.END, f"Total Wins: {wins}\n")
            results_text.insert(tk.END, f"Total Losses: {losses}\n")
            results_text.insert(tk.END, f"Total R: {total_r}R\n")
            results_text.insert(tk.END, f"Win Ratio: {win_ratio:.2f}%\n")
            
            # If the range spans more than one month, calculate and display monthly R/R
            if (end_date.year > start_date.year) or (end_date.month > start_date.month):
                monthly_rr = calculate_monthly_rr(results)
                results_text.insert(tk.END, "\nMonthly R/R Summary:\n")
                for month, rr in monthly_rr.items():
                    results_text.insert(tk.END, f"{month}: {rr}R\n")

        mt5.shutdown()


# Function to reset the GUI
def reset_fields():
    """
    Resets the input fields and clears the results text box.
    """
    symbol_entry.delete(0, tk.END)
    start_date_entry.delete(0, tk.END)
    end_date_entry.delete(0, tk.END)
    results_text.delete('1.0', tk.END)

# Function to export results to CSV
def export_to_csv():
    """
    Exports the results to a CSV file.
    """
    if not results:
        results_text.insert(tk.END, "No results to export.\n")
        return

    # Ask user where to save the file
    file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])

    if file_path:
        results_df = pd.DataFrame(results, columns=["Date", "Trade", "Level", "Stop Loss", "Take Profit", "Result"])
        results_df.to_csv(file_path, index=False)
        results_text.insert(tk.END, f"Results successfully exported to {file_path}\n")

# Function to simulate backtest and plot account performance
def simulate_backtest():
    """
    Simulates the performance of an account based on the backtest results and plots the account balance over time.
    """
    if not results:
        results_text.insert(tk.END, "No results to simulate.\n")
        return

    initial_balance = 10000
    risk_per_trade = 0.05
    reward_per_win = 2000
    loss_per_trade = 500

    account_balance = initial_balance
    balances = [account_balance]

    for result in results:
        if result[5] == "Win":
            account_balance += reward_per_win
        elif result[5] == "Loss":
            account_balance -= loss_per_trade
        balances.append(account_balance)

    # Plot the account balance over time
    plt.figure(figsize=(10, 6))
    plt.plot(balances, marker='o')
    plt.title('Account Balance Over Time')
    plt.xlabel('Number of Trades')
    plt.ylabel('Account Balance ($)')
    plt.grid(True)
    plt.show()

# Setup the Tkinter window
root = tk.Tk()
root.title("9:30 AM Strategy Results")

# Create labels and entries for symbol and date range
tk.Label(root, text="Symbol:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
symbol_entry = tk.Entry(root)
symbol_entry.grid(row=0, column=1, padx=10, pady=5)

tk.Label(root, text="Start Date (YYYY-MM-DD):").grid(row=1, column=0, padx=10, pady=5, sticky='e')
start_date_entry = tk.Entry(root)
start_date_entry.grid(row=1, column=1, padx=10, pady=5)

tk.Label(root, text="End Date (YYYY-MM-DD):").grid(row=2, column=0, padx=10, pady=5, sticky='e')
end_date_entry = tk.Entry(root)
end_date_entry.grid(row=2, column=1, padx=10, pady=5)

# Create a scrolled text box to display results
results_text = scrolledtext.ScrolledText(root, width=60, height=20, wrap=tk.WORD)
results_text.grid(column=0, row=4, columnspan=3, padx=10, pady=10)

# Create a button to trigger the strategy
run_button = tk.Button(root, text="Run Strategy", command=display_results)
run_button.grid(column=0, row=3, padx=10, pady=10)

# Create a button to reset the fields
reset_button = tk.Button(root, text="Reset", command=reset_fields)
reset_button.grid(column=1, row=3, padx=10, pady=10)

# Create a button to export results to CSV
export_button = tk.Button(root, text="Export to CSV", command=export_to_csv)
export_button.grid(column=2, row=3, padx=10, pady=10)

# Create a button to simulate backtest and plot account performance
simulate_button = tk.Button(root, text="Simulate Backtest", command=simulate_backtest)
simulate_button.grid(column=0, row=5, columnspan=3, padx=10, pady=10)

# Run the Tkinter main loop
root.mainloop()
