import MetaTrader5 as mt5
import pytz
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox

# Initialize connection to MT5
def initialize_mt5():
    if not mt5.initialize():
        print("Failed to initialize MT5, error code =", mt5.last_error())
        quit()

# Connect to account
def connect_account():
    password = "Flashpoint1963#"
    server = "Exness-MT5Trial10"
    account_id = 81142033  # Your MetaTrader account number
    authorized = mt5.login(account_id, password, server)
    if not authorized:
        print("Failed to connect to account #{}, error code: {}".format(account_id, mt5.last_error()))
        quit()

# Retrieve 1-hour price data for 5AM to 8AM in New York time
def get_1hr_candle_data(symbol, date):
    # Define New York timezone
    ny_tz = pytz.timezone('America/New_York')
    
    # Convert the provided date to NY time at 5 AM
    start_datetime = ny_tz.localize(datetime.strptime(date + " 05:00:00", "%Y-%m-%d %H:%M:%S"))
    # Calculate the end time at 8 AM NY time
    end_datetime = start_datetime + timedelta(hours=3)
    
    # Convert to UTC
    utc_from = start_datetime.astimezone(pytz.utc)
    utc_to = end_datetime.astimezone(pytz.utc)

    # Debug output: time conversion
    print(f"Fetching data from {utc_from} to {utc_to} in UTC for {symbol}")

    # Get the candle data for this range from MT5
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, utc_from, utc_to)

    # Debug output: fetched candle data
    print(f"Fetched candle data for {symbol}: {rates}")
    
    return rates

# Calculate the highest high and lowest low from the 1-hour candles
def calculate_high_low(candle_data):
    highest_high = max(candle['high'] for candle in candle_data)
    lowest_low = min(candle['low'] for candle in candle_data)
    print(f"Highest High: {highest_high}, Lowest Low: {lowest_low}")
    return highest_high, lowest_low

# Check breach using historical data within the backtest period and return breach price
def check_breach_historical(symbol, start_time, high, low):
    # Adjust the time after the 8AM candles to check breach later in the day
    ny_tz = pytz.timezone('America/New_York')
    
    # Start scanning from 9 AM NY time
    breach_start_time = ny_tz.localize(datetime.combine(start_time.date(), datetime.strptime("09:00:00", "%H:%M:%S").time()))
    
    # Stop scanning at 5 PM NY time (8 hours after 9 AM)
    breach_end_time = breach_start_time + timedelta(hours=8)
    
    # Convert both times to UTC
    utc_from = breach_start_time.astimezone(pytz.utc)
    utc_to = breach_end_time.astimezone(pytz.utc)
    
    # Debug output: checking breach period
    print(f"Checking breach from {utc_from} to {utc_to} (9AM to 5PM NY time) for {symbol}")
    
    # Fetch historical ticks
    ticks = mt5.copy_ticks_range(symbol, utc_from, utc_to, mt5.COPY_TICKS_ALL)
    
    # Debug output: fetched ticks
    print(f"Fetched ticks for {symbol}: {ticks}")
    
    for tick in ticks:
        price = tick['ask']
        if price > high:
            return f"High breached at {price}"
        elif price < low:
            return f"Low breached at {price}"
    
    # If no breach happens within the 8-hour period
    return "Not breached"



# Backtest over a selected range, skipping weekends
def backtest(symbol, start_date, end_date):
    start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
    end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
    
    current_date = start_datetime
    results = []

    while current_date <= end_datetime:
        # Skip weekends (Saturday and Sunday)
        if current_date.weekday() == 5 or current_date.weekday() == 6:
            current_date += timedelta(days=1)
            continue

        print(f"Running backtest for {current_date.strftime('%Y-%m-%d')}")

        # Get 1-hour candles for the day between 5AM-8AM NY time
        data = get_1hr_candle_data(symbol, current_date.strftime("%Y-%m-%d"))
        
        if data is not None and len(data) == 4:
            # Calculate highest high and lowest low
            highest_high, lowest_low = calculate_high_low(data)

            # Check breach using historical data after the 5AM-8AM period and print breach price
            breach = check_breach_historical(symbol, current_date, highest_high, lowest_low)
            results.append(f"{current_date.strftime('%Y-%m-%d')}: {breach}")
        else:
            print(f"No valid candle data for {current_date.strftime('%Y-%m-%d')}")
            results.append(f"{current_date.strftime('%Y-%m-%d')}: No data for 5AM-8AM")
        
        current_date += timedelta(days=1)
    
    return results

# GUI for user input
def create_gui():
    def on_submit():
        symbol = symbol_entry.get()
        start_date = start_entry.get()
        end_date = end_entry.get()
        
        # Validate input
        if not symbol or not start_date or not end_date:
            messagebox.showerror("Input Error", "Please fill in all fields.")
            return

        try:
            data = get_1hr_candle_data(symbol, start_date)
            if not data:
                messagebox.showerror("Data Error", "No data found for this period.")
                return

            # Calculate highest high and lowest low
            if len(data) == 4:
                high, low = calculate_high_low(data)
                high_label.config(text=f"Highest High: {high}")
                low_label.config(text=f"Lowest Low: {low}")
                breach_result = check_breach_historical(symbol, datetime.strptime(start_date, "%Y-%m-%d"), high, low)
                breach_label.config(text=f"Breach Result: {breach_result}")
            else:
                high_label.config(text="No valid 5AM-8AM data found")
                low_label.config(text="")
                breach_label.config(text="")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to retrieve data: {str(e)}")

    def on_backtest():
        symbol = symbol_entry.get()
        start_date = start_entry.get()
        end_date = end_entry.get()
        
        # Validate input
        if not symbol or not start_date or not end_date:
            messagebox.showerror("Input Error", "Please fill in all fields.")
            return

        try:
            results = backtest(symbol, start_date, end_date)
            result_text = "\n".join(results)
            result_label.config(text=f"Backtest Results:\n{result_text}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run backtest: {str(e)}")

    # GUI setup
    root = tk.Tk()
    root.title("Forex Trading Bot")

    tk.Label(root, text="Currency Pair:").pack()
    symbol_entry = tk.Entry(root)
    symbol_entry.pack()

    tk.Label(root, text="Start Date (YYYY-MM-DD):").pack()
    start_entry = tk.Entry(root)
    start_entry.pack()

    tk.Label(root, text="End Date (YYYY-MM-DD):").pack()
    end_entry = tk.Entry(root)
    end_entry.pack()

    tk.Button(root, text="Submit", command=on_submit).pack()
    tk.Button(root, text="Backtest", command=on_backtest).pack()

    high_label = tk.Label(root, text="Highest High: ")
    high_label.pack()

    low_label = tk.Label(root, text="Lowest Low: ")
    low_label.pack()

    breach_label = tk.Label(root, text="Breach Result: ")
    breach_label.pack()

    result_label = tk.Label(root, text="Backtest Results: ")
    result_label.pack()

    root.mainloop()

# Main function to run the bot
def main():
    initialize_mt5()
    connect_account()
    create_gui()

if __name__ == '__main__':
    main()
