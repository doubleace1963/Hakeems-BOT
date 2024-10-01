import MetaTrader5 as mt5
import tim
# Parameters (replace with your actual account details)
account_number = 5551777  # Replace with your account number
password = "Flashpoint1963#"  # Replace with your account password
symbol = "Volatility 25 Index"  # The symbol for Volatility 25 Index
server = "Deriv-Demo"  # Replace with your server name
lot_size = 1.0  # Lot size for the order

# Initialize the MetaTrader 5 terminal
if not mt5.initialize():
    print("initialize() failed, error code =", mt5.last_error())
    quit()

# Log in to the trading account
if not mt5.login(account_number, password, server):
    print("Login failed, error code =", mt5.last_error())
    mt5.shutdown()
    quit()

# Check if the symbol is available in Market Watch
if not mt5.symbol_select(symbol, True):
    print(f"Failed to select {symbol}, error code =", mt5.last_error())
    mt5.shutdown()
    quit()

# Get symbol information
symbol_info = mt5.symbol_info(symbol)
if symbol_info is None:
    print(f"{symbol} not found, cannot call order_check()")
    mt5.shutdown()
    quit()

# Ensure the symbol is available for trading
if not symbol_info.visible:
    if not mt5.symbol_select(symbol, True):
        print(f"Failed to select {symbol} for trading, error code =", mt5.last_error())
        mt5.shutdown()
        quit()

# Get the current ask price
symbol_info_tick = mt5.symbol_info_tick(symbol)
if symbol_info_tick is None:
    print(f"Failed to get {symbol} tick, error code =", mt5.last_error())
    mt5.shutdown()
    quit()


def order_request(action_type, symbol, lotsize, order_type, ):
    action_type = 
# Create a request for a buy order
order_request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": lot_size,
    "type": mt5.ORDER_TYPE_BUY,
    "price": symbol_info_tick.ask,
    "deviation": 10,
    "magic": 234000,
    "comment": "Python script order",

}

# Print the order request for debugging
print("Order Request:", order_request)

# Send the request
result = mt5.order_send(order_request)

# Check the result
if result is None:
    print("Order send failed, result is None, error code =", mt5.last_error())
else:
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("Order failed, retcode =", result.retcode)
        print("Result:", result)
    else:
        print("Order placed successfully")
        print("Result:", result)

# Shut down the connection to the MetaTrader 5 terminal
mt5.shutdown()





