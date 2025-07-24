import requests
import pandas as pd
import time
from datetime import datetime

import plotly.graph_objects as go

def fetch_klines(symbol, interval, start_time, end_time, limit=1000):
    url = "https://api.binance.com/api/v3/klines"
    all_data = []

    while start_time < end_time:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": int(start_time),
            "endTime": int(end_time),
            "limit": limit
        }
        response = requests.get(url, params=params)
        data = response.json()

        if not data:
            break

        all_data.extend(data)
        start_time = data[-1][0] + 60_000  # +1 минута

        time.sleep(0.2)  # защита от бана

    return all_data

# Настройки
symbol = "ADAUSDT"
interval = "1m"
now = int(time.time() * 1000)
days = 30
start_time = now - days * 24 * 60 * 60 * 1000

# Получаем данные
data = fetch_klines(symbol, interval, start_time, now)

# Обработка в DataFrame
df = pd.DataFrame(data, columns=[
    "timestamp", "open", "high", "low", "close",
    "volume", "_", "_", "_", "_", "_", "_"
])
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
df = df.astype({"open": float, "high": float, "low": float, "close": float})
df.set_index("timestamp", inplace=True)

# График с plotly
fig = go.Figure(data=[go.Candlestick(
    x=df.index,
    open=df["open"],
    high=df["high"],
    low=df["low"],
    close=df["close"]
)])

fig.update_layout(
    title=f'{symbol} — 1m candles (last {days} days)',
    xaxis_title='Time',
    yaxis_title='Price',
    xaxis_rangeslider_visible=False,
    template="plotly_dark",
    height=700
)

fig.show()