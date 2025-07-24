import requests
import pandas as pd
import time

import dash
from dash import dcc, html
import plotly.graph_objects as go
import ta
import plotly.subplots as sp

from dash.dependencies import Output, Input, State
from strategy import get_strategy_signals, backtest_signals

# --- Настройки ---
symbol = "ADAUSDT"
interval = "1m"
days = 10  # Сколько дней загружать

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
        if response.status_code != 200:
            print("Ошибка Binance API:", response.status_code, response.text)
            break
        data = response.json()
        if not data:
            break
        all_data.extend(data)
        start_time = data[-1][0] + 60_000  # +1 минута
        time.sleep(0.2)
    return all_data

def get_candles_df(symbol, interval, days):
    now = int(time.time() * 1000)
    start_time = now - days * 24 * 60 * 60 * 1000
    data = fetch_klines(symbol, interval, start_time, now)
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close",
        "volume", "_", "_", "_", "_", "_", "_"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
    df.set_index("timestamp", inplace=True)
    # print(df.head())
    # print(df.shape)
    return df

# --- Dash app ---
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H2(f"{symbol} — 1m candles (last {days} days)"),
    dcc.Graph(id='tv-like-chart'),
    dcc.Interval(id='interval-update', interval=60*1000, n_intervals=0)  # обновлять каждую минуту
])

@app.callback(
    Output('tv-like-chart', 'figure'),
    Input('interval-update', 'n_intervals'),
    State('tv-like-chart', 'relayoutData')
)
def update_chart(n, relayoutData):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Обновление графика, n_intervals={n}")
    df = get_strategy_signals(symbol=symbol, interval=interval, days=days, max_entries=1)

    fig = sp.make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.5, 0.15, 0.15, 0.15],
        subplot_titles=("Candles", "MFI", "MACD", "RSI")
    )

    # Свечи
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Candles"
        ),
        row=1, col=1
    )

    # Bollinger Bands
    fig.add_trace(
        go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper", line=dict(color="orange", dash="dot")),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["bb_basis"], name="BB Basis", line=dict(color="gray", dash="dot")),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower", line=dict(color="orange", dash="dot")),
        row=1, col=1
    )

    # Buy/Sell сигналы
    fig.add_trace(
        go.Scatter(
            x=df.index, 
            y=df["close"].where(df["buySignal"]), 
            mode="markers", 
            marker=dict(color="lime", size=8), 
            name="Buy Signal"
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, 
            y=df["close"].where(df["sellSignal"]), 
            mode="markers", 
            marker=dict(color="red", size=8), 
            name="Sell Signal"
        ),
        row=1, col=1
    )

    # MFI
    fig.add_trace(
        go.Scatter(x=df.index, y=df["mfi"], name="MFI", line=dict(color="lime")),
        row=2, col=1
    )

    # MACD и Signal
    fig.add_trace(
        go.Scatter(x=df.index, y=df["macd"], name="MACD", line=dict(color="cyan")),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["macd_signal"], name="Signal", line=dict(color="orange")),
        row=3, col=1
    )

    # RSI
    fig.add_trace(
        go.Scatter(x=df.index, y=df["rsi"], name="RSI", line=dict(color="magenta")),
        row=4, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        height=900,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        showlegend=False
    )
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=4, col=1)

    # --- Сохраняем масштаб X/Y если был изменён ---
    if relayoutData is not None:
        # X axis
        if "xaxis.range[0]" in relayoutData and "xaxis.range[1]" in relayoutData:
            fig.update_xaxes(range=[
                relayoutData["xaxis.range[0]"],
                relayoutData["xaxis.range[1]"]
            ])
        elif "xaxis.range" in relayoutData:
            fig.update_xaxes(range=relayoutData["xaxis.range"])
        elif "xaxis.autorange" in relayoutData:
            fig.update_xaxes(autorange=relayoutData["xaxis.autorange"])
        # Y axis (основной график)
        if "yaxis.range[0]" in relayoutData and "yaxis.range[1]" in relayoutData:
            fig.update_yaxes(range=[
                relayoutData["yaxis.range[0]"],
                relayoutData["yaxis.range[1]"]
            ], row=1, col=1)
        elif "yaxis.range" in relayoutData:
            fig.update_yaxes(range=relayoutData["yaxis.range"], row=1, col=1)
        elif "yaxis.autorange" in relayoutData:
            fig.update_yaxes(autorange=relayoutData["yaxis.autorange"], row=1, col=1)
        # Y axis для других субграфиков
        if "yaxis2.range" in relayoutData:
            fig.update_yaxes(range=relayoutData["yaxis2.range"], row=2, col=1)
        if "yaxis3.range" in relayoutData:
            fig.update_yaxes(range=relayoutData["yaxis3.range"], row=3, col=1)
        if "yaxis4.range" in relayoutData:
            fig.update_yaxes(range=relayoutData["yaxis4.range"], row=4, col=1)

    return fig

df = get_strategy_signals(symbol="ADAUSDT", interval="1m", days=10, max_entries=1)
stats = backtest_signals(df)

print(f"Доходность: {stats['total_return_pct']:.2f}%")
print(f"Трейдов: {stats['num_trades']}")
print(f"Макс. просадка: {stats['max_drawdown_pct']:.2f}%")

if __name__ == "__main__":
    app.run(debug=True, port=8051)