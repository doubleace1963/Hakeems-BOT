import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# Load Data
data = pd.read_csv('/mnt/data/forex_data.csv')  # Replace with your file path
data['Date'] = pd.to_datetime(data['Date'])
data.set_index('Date', inplace=True)

# Extract relevant columns
high = data['High'].values
low = data['Low'].values
open_price = data['Open'].values
close = data['Close'].values

# Identify Induced Liquidity Patterns
def identify_highs_lows(high, low, min_window=10, max_window=30):
    highs = []
    lows = []
    for i in range(max_window, len(high) - max_window):
        if high[i] == max(high[i-min_window:i+min_window]) and high[i] == max(high[i-max_window:i+max_window]):
            highs.append((i, high[i]))
        if low[i] == min(low[i-min_window:i+min_window]) and low[i] == min(low[i-max_window:i+max_window]):
            lows.append((i, low[i]))
    return highs, lows

highs, lows = identify_highs_lows(high, low)

# Feature Engineering
def create_features(prices, look_back=60):
    X, y = [], []
    for i in range(look_back, len(prices)-1):
        X.append(prices[i-look_back:i])
        y.append(prices[i+1])
    return np.array(X), np.array(y)

prices = close  # Use close prices for simplicity
X, y = create_features(prices)

# Normalize the data
scaler = MinMaxScaler(feature_range=(0, 1))
X_scaled = scaler.fit_transform(X.reshape(-1, X.shape[1])).reshape(X.shape)
y_scaled = scaler.fit_transform(y.reshape(-1, 1))

# Split the data into training and testing sets
split = int(0.8 * len(X_scaled))
X_train, X_test = X_scaled[:split], X_scaled[split:]
y_train, y_test = y_scaled[:split], y_scaled[split:]

# Convert data to PyTorch tensors
X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
y_train_tensor = torch.tensor(y_train, dtype=torch.float32)
X_test_tensor = torch.tensor(X_test, dtype=torch.float32)
y_test_tensor = torch.tensor(y_test, dtype=torch.float32)

# Create DataLoader
train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
test_dataset = TensorDataset(X_test_tensor, y_test_tensor)

train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

# Define the LSTM model
class LSTMModel(nn.Module):
    def __init__(self, input_size, hidden_size, output_size, num_layers):
        super(LSTMModel, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)
    
    def forward(self, x):
        h_0 = torch.zeros(2, x.size(0), 50).to(x.device)
        c_0 = torch.zeros(2, x.size(0), 50).to(x.device)
        out, _ = self.lstm(x, (h_0, c_0))
        out = self.fc(out[:, -1, :])
        return out

# Model initialization
model = LSTMModel(input_size=1, hidden_size=50, output_size=1, num_layers=2)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Training the model
num_epochs = 20
for epoch in range(num_epochs):
    model.train()
    for X_batch, y_batch in train_loader:
        optimizer.zero_grad()
        output = model(X_batch.unsqueeze(-1))
        loss = criterion(output, y_batch)
        loss.backward()
        optimizer.step()

    print(f'Epoch {epoch+1}/{num_epochs}, Loss: {loss.item()}')

# Model Evaluation
model.eval()
with torch.no_grad():
    y_pred = model(X_test_tensor.unsqueeze(-1)).cpu().numpy()
    y_test_rescaled = scaler.inverse_transform(y_test)
    y_pred_rescaled = scaler.inverse_transform(y_pred)

mse = mean_squared_error(y_test_rescaled, y_pred_rescaled)
print(f'Mean Squared Error: {mse}')

# Plot the results
plt.figure(figsize=(14, 5))
plt.plot(data.index[split + 60:], y_test_rescaled, color='blue', label='Actual Prices')
plt.plot(data.index[split + 60:], y_pred_rescaled, color='red', label='Predicted Prices')
plt.title('Forex Price Prediction with Induced Liquidity Patterns')
plt.xlabel('Date')
plt.ylabel('Price')
plt.legend()
plt.show()
