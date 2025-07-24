import pandas as pd
import ta
import requests
import time

BINANCE_URL = "https://api.binance.com/api/v3/klines"
BB_WINDOW = 20
BB_STD = 2.0
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
MFI_WINDOW = 14
RSI_WINDOW = 14

def fetch_klines(symbol, interval, start_time, end_time, limit=1000):
    """Загрузка исторических свечей с Binance."""
    all_data = []
    while start_time < end_time:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": int(start_time),
            "endTime": int(end_time),
            "limit": limit
        }
        response = requests.get(BINANCE_URL, params=params)
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
    """Получение DataFrame с историей по символу."""
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

def add_indicators(df):
    """Добавляет индикаторы в DataFrame."""
    df["macd"] = ta.trend.macd(df["close"], window_slow=MACD_SLOW, window_fast=MACD_FAST, fillna=True)
    df["macd_signal"] = ta.trend.macd_signal(df["close"], window_slow=MACD_SLOW, window_fast=MACD_FAST, window_sign=MACD_SIGNAL, fillna=True)
    df["mfi"] = ta.volume.money_flow_index(df["high"], df["low"], df["close"], df["volume"], window=MFI_WINDOW, fillna=True)
    df["rsi"] = ta.momentum.rsi(df["close"], window=RSI_WINDOW, fillna=True)
    df["bb_basis"] = ta.trend.sma_indicator(df["close"], window=BB_WINDOW, fillna=True)
    df["bb_dev"] = BB_STD * df["close"].rolling(window=BB_WINDOW, min_periods=1).std()
    df["bb_upper"] = df["bb_basis"] + df["bb_dev"]
    df["bb_lower"] = df["bb_basis"] - df["bb_dev"]
    return df

def add_btc_indicators(df):
    """Добавляет индикаторы для BTCUSDT (1h)."""
    df["bb_basis"] = ta.trend.sma_indicator(df["close"], window=BB_WINDOW, fillna=True)
    df["bb_dev"] = BB_STD * df["close"].rolling(window=BB_WINDOW, min_periods=1).std()
    df["bb_upper"] = df["bb_basis"] + df["bb_dev"]
    return df

def merge_btc_to_ada(ada, btc):
    """Сопоставляет BTCUSDT 1h к ADAUSDT 1m по времени."""
    btc_1h = btc[["close", "open", "bb_upper"]].copy()
    btc_1h.columns = ["btc_close", "btc_open", "btc_upper"]
    ada = ada.merge(btc_1h, left_index=True, right_index=True, how="left")
    ada[["btc_close", "btc_open", "btc_upper"]] = ada[["btc_close", "btc_open", "btc_upper"]].ffill()
    return ada

def add_signals(ada):
    """Добавляет сигнальные столбцы."""
    ada["btc_filter"] = ~((ada["btc_close"] > ada["btc_upper"]) | ((ada["btc_close"] < ada["btc_open"]) & (ada["btc_close"] > ada["btc_upper"] * 0.98)))
    ada["buyCond"] = (
        (ada["macd"] > ada["macd_signal"]).shift(1) & (ada["macd"] <= ada["macd_signal"]) &
        (ada["mfi"] < 40) &
        (ada["close"] < ada["bb_basis"]) &
        (ada["btc_filter"])
    )
    ada["sellCond"] = (ada["rsi"] > 70) & (ada["close"] > ada["bb_upper"])
    return ada

def simulate_trades(ada, max_entries=1):
    """Имитация сделок с max_entries."""
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

def get_strategy_signals(symbol="ADAUSDT", interval="1m", days=7, max_entries=1):
    """Основная функция стратегии."""
    ada = get_df(symbol, interval, days)
    btc = get_df("BTCUSDT", "1h", days)
    ada = add_indicators(ada)
    btc = add_btc_indicators(btc)
    ada = merge_btc_to_ada(ada, btc)
    ada = add_signals(ada)
    ada = simulate_trades(ada, max_entries)
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