import MetaTrader5 as mt5
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta

# Step 1: Initialize MetaTrader 5 connection
if not mt5.initialize():
    print("Initialization failed")
    mt5.shutdown()

# Step 2: Retrieve the last 3 days of XAU/USD data (5-minute intervals)
symbol = "USTEC"
timeframe = mt5.TIMEFRAME_M5

# Calculate the time range for the last 3 days
utc_from = datetime.now() - timedelta(days=5)
utc_to = datetime.now()

# Requesting 5-minute bars for the last 3 days
rates = mt5.copy_rates_range(symbol, timeframe, utc_from, utc_to)

# Shutdown connection after retrieving data
mt5.shutdown()

# Convert the rates to a Pandas DataFrame for easier handling
data = pd.DataFrame(rates)
data['time'] = pd.to_datetime(data['time'], unit='s')

# Step 3: Logic to identify major swings (only major highs and major lows)
def identify_major_swings(prices, major_n=5):
    swings = []

    for i in range(len(prices)):
        high, low = prices[i]

        # Identify Major Highs
        if i >= major_n and i <= len(prices) - major_n - 1:
            if all(high > prices[i - j][0] for j in range(1, major_n+1)) and all(high > prices[i + j][0] for j in range(1, major_n+1)):
                swings.append({'type': 'major_high', 'index': i, 'price': high})

        # Identify Major Lows
        if i >= major_n and i <= len(prices) - major_n - 1:
            if all(low < prices[i - j][1] for j in range(1, major_n+1)) and all(low < prices[i + j][1] for j in range(1, major_n+1)):
                swings.append({'type': 'major_low', 'index': i, 'price': low})

    return swings

# Apply the function to identify swings
swings = identify_major_swings(data[['high', 'low']].values)

# Step 4: Visualize the data with the identified major swings
def plot_major_swings(data, swings):
    indices = np.arange(len(data))
    highs = data['high']
    lows = data['low']

    plt.figure(figsize=(14, 7))
    plt.plot(indices, highs, label="Highs", color='blue')
    plt.plot(indices, lows, label="Lows", color='red')

    # Mark the major swings on the chart
    for swing in swings:
        if swing['type'] == 'major_high':
            plt.plot(swing['index'], swing['price'], 'go', markersize=10, label='Major High')
        elif swing['type'] == 'major_low':
            plt.plot(swing['index'], swing['price'], 'ro', markersize=10, label='Major Low')

    plt.title("XAU/USD Major Highs and Lows Over the Last 3 Days")
    plt.xlabel("Time (5-Minute Intervals)")
    plt.ylabel("Price")
    plt.legend(loc='upper left')
    plt.show()

# Plot the major swings
plot_major_swings(data, swings)
