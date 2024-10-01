import MetaTrader5 as mt5

# Parameters
RISK_AMOUNT = 750  # Risk $750 per trade
symbol = "AUDJPY"  # Replace with your desired trading symbol
entry_price = 98.432  # Replace with actual entry price for USDJPY
stop_loss = 98.577  # Replace with actual stop loss price for USDJPY

# Connect to MetaTrader 5
if not mt5.initialize():
    print("MetaTrader5 initialization failed")
    mt5.shutdown()
else:
    print("MetaTrader5 initialized")

# Get symbol info
symbol_info = mt5.symbol_info(symbol)
if not symbol_info:
    print(f"Failed to get symbol info for {symbol}")
else:
    print(f"Symbol: {symbol}")
    print(f"Trade Contract Size: {symbol_info.trade_contract_size}")
    print(f"Point: {symbol_info.point}")

    # Calculate pip value for JPY pairs
    pip_value = (100000 / entry_price) / 100  # JPY pairs, standard lot (100,000 units)
    print(f"Pip Value (in USD per pip for one standard lot): {pip_value:.2f} USD")

    # Calculate pip risk (number of pips)
    pip_risk = abs(entry_price - stop_loss) / 0.01
    print(f"Pip Risk (Number of pips between entry and stop loss): {pip_risk:.2f} pips")

    # Calculate lot size
    lot_size = RISK_AMOUNT / (pip_risk * pip_value)
    print(f"Calculated Lot Size (before rounding): {lot_size:.2f} lots")

    # Apply minimum and maximum constraints
    min_lot = 0.01  # Minimum lot size
    max_lot = 100.0  # Maximum lot size
    lot_size = max(min(lot_size, max_lot), min_lot)
    print(f"Final Lot Size (after applying constraints): {lot_size:.2f} lots")

# Shutdown connection to MetaTrader 5
mt5.shutdown()
