import MetaTrader5 as mt5
import pandas as pd
import datetime as dt
import matplotlib.pyplot as plt
import mplfinance as mpf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk

# Connect to MetaTrader 5 terminal
if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()

# Define the symbol and timeframes
symbol = "EURUSD"
timeframes = {
    '1H': mt5.TIMEFRAME_H1,
    '4H': mt5.TIMEFRAME_H4,
    'D': mt5.TIMEFRAME_D1
}

# Define the time range
start_date = dt.datetime.now() - dt.timedelta(days=30)
end_date = dt.datetime.now()

# Function to fetch historical data
def fetch_historical_data(symbol, timeframe, start_date, end_date):
    utc_from = start_date
    utc_to = end_date
    rates = mt5.copy_rates_range(symbol, timeframe, utc_from, utc_to)
    if rates is None:
        print(f"Failed to get rates for {symbol} {timeframe}")
        return pd.DataFrame()
    rates_frame = pd.DataFrame(rates)
    rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')
    rates_frame.set_index('time', inplace=True)
    return rates_frame

# Fetch historical data for each timeframe
data = {}
for tf, mt5_tf in timeframes.items():
    data[tf] = fetch_historical_data(symbol, mt5_tf, start_date, end_date)

# Shutdown connection to MT5 terminal
mt5.shutdown()

# Function to detect major trends
def detect_major_trends(df):
    df['higher_high'] = df['high'] > df['high'].shift(1)
    df['higher_low'] = df['low'] > df['low'].shift(1)
    df['lower_high'] = df['high'] < df['high'].shift(1)
    df['lower_low'] = df['low'] < df['low'].shift(1)
    
    df['uptrend'] = df['higher_high'] & df['higher_low']
    df['downtrend'] = df['lower_high'] & df['lower_low']
    
    return df

# Function to detect minor trends within 6-hour intervals
def detect_minor_trends(df):
    minor_trends = []
    for i in range(0, len(df), 6):
        interval_df = df.iloc[i:i+6]
        highest_high = interval_df['high'].max()
        lowest_low = interval_df['low'].min()
        minor_trends.append((interval_df.index[0], highest_high, lowest_low))
    return minor_trends

# Function to determine the overall trend
def determine_overall_trend(df):
    total_periods = len(df)
    uptrend_periods = df['uptrend'].sum()
    downtrend_periods = df['downtrend'].sum()
    
    if uptrend_periods > downtrend_periods:
        return 'Uptrend'
    elif downtrend_periods > uptrend_periods:
        return 'Downtrend'
    else:
        return 'Sideways'

# Function to detect Judas swings
def detect_judas_swings(df):
    df['judas_swing'] = False
    for i in range(1, len(df)):
        if df['uptrend'].iloc[i-1] and df['close'].iloc[i] < df['close'].iloc[i-1] * 0.5:
            df.at[df.index[i], 'judas_swing'] = True
        elif df['downtrend'].iloc[i-1] and df['close'].iloc[i] > df['close'].iloc[i-1] * 1.5:
            df.at[df.index[i], 'judas_swing'] = True
    return df

# Detect major, minor trends and Judas swings
major_trends = {tf: detect_major_trends(df) for tf, df in data.items()}
minor_trends = {tf: detect_minor_trends(df) for tf, df in data.items()}
judas_swings = {tf: detect_judas_swings(df) for tf, df in major_trends.items()}

# Determine overall trends
overall_trends = {tf: determine_overall_trend(df) for tf, df in major_trends.items()}

# GUI to display the charts
class TrendGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Trend Analysis")
        self.master.geometry("1200x800")
        
        self.fig, self.axs = plt.subplots(len(timeframes), 1, figsize=(12, 10), sharex=True)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.master)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        
        self.plot_data()

    def plot_data(self):
        for idx, (tf, df) in enumerate(major_trends.items()):
            ax = self.axs[idx]
            mpf.plot(df, type='candle', ax=ax, title=f"{symbol} {tf} Timeframe ({overall_trends[tf]})", style='charles',
                     show_nontrading=True, mav=(3,6), volume=False)
            df['judas_swing_marker'] = df['judas_swing'].apply(lambda x: '^' if x else '')
            
            for interval in minor_trends[tf]:
                ax.axvline(x=interval[0], color='y', linestyle='--')
                ax.annotate(f"High: {interval[1]:.2f}", xy=(interval[0], interval[1]), xytext=(interval[0], interval[1]+5),
                            arrowprops=dict(facecolor=KEEM'black', shrink=0.05))
                ax.annotate(f"Low: {interval[2]:.2f}", xy=(interval[0], interval[2]), xytext=(interval[0], interval[2]-5),
                            arrowprops=dict(facecolor='black', shrink=0.05))

        plt.xticks(rotation=45)
        plt.tight_layout()
        self.canvas.draw()

# Initialize the GUI
root = tk.Tk()
app = TrendGUI(root)
root.mainloop()
