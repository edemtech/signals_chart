import pandas as pd
import ta
import requests
import time

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
            break
        data = response.json()
        if not data:
            break
        all_data.extend(data)
        start_time = data[-1][0] + 60_000
        time.sleep(0.2)
    return all_data

def get_df(symbol, interval, days):
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
    return df

def get_strategy_signals(symbol="ADAUSDT", interval="1m", days=7, max_entries=1):
    ada = get_df(symbol, interval, days)
    btc = get_df("BTCUSDT", "1h", days)

    # Индикаторы для ADAUSDT
    ada["macd"] = ta.trend.macd(ada["close"], window_slow=26, window_fast=12, fillna=True)
    ada["macd_signal"] = ta.trend.macd_signal(ada["close"], window_slow=26, window_fast=12, window_sign=9, fillna=True)
    ada["mfi"] = ta.volume.money_flow_index(ada["high"], ada["low"], ada["close"], ada["volume"], window=14, fillna=True)
    ada["rsi"] = ta.momentum.rsi(ada["close"], window=14, fillna=True)
    ada["bb_basis"] = ta.trend.sma_indicator(ada["close"], window=20, fillna=True)
    ada["bb_dev"] = 2.0 * ada["close"].rolling(window=20, min_periods=1).std()
    ada["bb_upper"] = ada["bb_basis"] + ada["bb_dev"]
    ada["bb_lower"] = ada["bb_basis"] - ada["bb_dev"]

    # Индикаторы для BTCUSDT (1h)
    btc["bb_basis"] = ta.trend.sma_indicator(btc["close"], window=20, fillna=True)
    btc["bb_dev"] = 2.0 * btc["close"].rolling(window=20, min_periods=1).std()
    btc["bb_upper"] = btc["bb_basis"] + btc["bb_dev"]

    # Сопоставляем BTCUSDT 1h к ADAUSDT 1m по времени
    btc_1h = btc[["close", "open", "bb_upper"]].copy()
    btc_1h.columns = ["btc_close", "btc_open", "btc_upper"]
    ada = ada.merge(btc_1h, left_index=True, right_index=True, how="left")
    ada[["btc_close", "btc_open", "btc_upper"]] = ada[["btc_close", "btc_open", "btc_upper"]].ffill()

    # Фильтр BTC
    ada["btc_filter"] = ~((ada["btc_close"] > ada["btc_upper"]) | ((ada["btc_close"] < ada["btc_open"]) & (ada["btc_close"] > ada["btc_upper"] * 0.98)))

    # Условия входа/выхода
    ada["buyCond"] = (
        (ada["macd"] > ada["macd_signal"]).shift(1) & (ada["macd"] <= ada["macd_signal"]) &
        (ada["mfi"] < 40) &
        (ada["close"] < ada["bb_basis"]) &
        (ada["btc_filter"])
    )
    ada["sellCond"] = (ada["rsi"] > 70) & (ada["close"] > ada["bb_upper"])

    # Имитация сделок с max_entries
    entry_count = 0
    entry_counts = [0]
    buy_signal = [False]
    sell_signal = [False]
    for i in range(1, len(ada)):
        if ada["buyCond"].iloc[i] and entry_count < max_entries:
            entry_count += 1
            buy_signal.append(True)
            sell_signal.append(False)
        elif ada["sellCond"].iloc[i] and entry_count > 0:
            entry_count = 0
            buy_signal.append(False)
            sell_signal.append(True)
        else:
            buy_signal.append(False)
            sell_signal.append(False)
        entry_counts.append(entry_count)
    ada["entry_count"] = entry_counts
    ada["buySignal"] = buy_signal
    ada["sellSignal"] = sell_signal
    ada["position"] = [int(c > 0) for c in entry_counts]

    return ada

# Визуализация только если файл запускается напрямую
if __name__ == "__main__":
    import plotly.subplots as sp
    import plotly.graph_objects as go

    ada = get_strategy_signals()
    # Создание графика
    fig = sp.make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.5, 0.15, 0.15, 0.15],
        subplot_titles=("Candles", "MFI", "MACD", "RSI")
    )
    fig.add_trace(
        go.Candlestick(
            x=ada.index, open=ada["open"], high=ada["high"], low=ada["low"], close=ada["close"], name="Candles"
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["bb_upper"], name="BB Upper", line=dict(color="orange", dash="dot")),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["bb_basis"], name="BB Basis", line=dict(color="gray", dash="dot")),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["bb_lower"], name="BB Lower", line=dict(color="orange", dash="dot")),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["close"].where(ada["buySignal"]), mode="markers", marker=dict(color="lime", size=8), name="Buy Signal"),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["close"].where(ada["sellSignal"]), mode="markers", marker=dict(color="red", size=8), name="Sell Signal"),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["mfi"], name="MFI", line=dict(color="lime")),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["macd"], name="MACD", line=dict(color="cyan")),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["macd_signal"], name="Signal", line=dict(color="orange")),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(x=ada.index, y=ada["rsi"], name="RSI", line=dict(color="magenta")),
        row=4, col=1
    )
    fig.update_layout(
        template="plotly_dark",
        height=900,
        hovermode="x unified",
        showlegend=True
    )
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=4, col=1)
    fig.show()