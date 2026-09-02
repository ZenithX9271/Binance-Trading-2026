"""
STEP 1: Naive EMA Crossover Strategy (The First Attempt)
Uses EMA20/50 crossover on 4H candles — a common beginner approach.
LESSON: Fast crossovers on crypto = death by a thousand cuts (whipsaw + fees).

This is the deliberately-naive BASELINE, so its 20/50 periods stay FIXED
(they are not tuned — the point is to show why fast crossovers fail).
"""
import pandas as pd, numpy as np
from datetime import datetime, timedelta
from binance.client import Client
from config import SYM_A, SYM_B

INITIAL_CASH = 1000.0
FEE_RATE = 0.001
EMA_FAST, EMA_SLOW = 20, 50
client = Client()


def fetch(symbol, start, end):
    warmup = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d")
    kl = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_4HOUR, warmup, end)
    df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol","ct","qv","t","tb","tq","ig"])
    df["time"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
    df["close"] = df["close"].astype(float)
    df = df[["time","close"]].set_index("time")
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    s, e = pd.to_datetime(start).tz_localize("UTC"), pd.to_datetime(end).tz_localize("UTC")
    return df.loc[s:e]


def run(name, start, end):
    df_a = fetch(SYM_A, start, end)
    df_b = fetch(SYM_B, start, end)

    cash, pos, entry, trades, fees = INITIAL_CASH, 0, 0.0, 0, 0.0
    eq = []

    for ts in df_a.index.intersection(df_b.index):
        pa, pb = df_a.loc[ts, "close"], df_b.loc[ts, "close"]
        a_bull = df_a.loc[ts, "ema_fast"] > df_a.loc[ts, "ema_slow"]
        b_bull = df_b.loc[ts, "ema_fast"] > df_b.loc[ts, "ema_slow"]

        if pos == 0:
            if a_bull:
                pos, entry = 1, pa; f = cash * FEE_RATE; cash -= f; fees += f; trades += 1
            elif b_bull:
                pos, entry = 2, pb; f = cash * FEE_RATE; cash -= f; fees += f; trades += 1
        elif pos == 1 and not a_bull:
            v = cash * (pa / entry); f = v * FEE_RATE; cash = v - f; fees += f; pos = 0; trades += 1
        elif pos == 2 and not b_bull:
            v = cash * (pb / entry); f = v * FEE_RATE; cash = v - f; fees += f; pos = 0; trades += 1

        eq.append(cash if pos == 0 else cash * (pa / entry) if pos == 1 else cash * (pb / entry))

    es = pd.Series(eq)
    ret = (es.iloc[-1] / INITIAL_CASH - 1) * 100
    dd = ((es - es.cummax()) / es.cummax()).min() * 100        # <-- fixed stray 'n' typo
    print(f"\n  --- {name} ({start} to {end}) ---")
    print(f"    Return:    {ret:+.2f}%  |  Max DD: {dd:.2f}%  |  Trades: {trades}  |  Fees: ${fees:.2f}")
    return ret


if __name__ == "__main__":
    print("=" * 60)
    print(f"  STEP 1: NAIVE EMA20/50 CROSSOVER — The Beginner's Trap")
    print(f"  Assets: {SYM_A} + {SYM_B} (from volatility screener)")
    print("=" * 60)
    run("Bear Crash",    "2021-11-01", "2022-01-31")
    run("Choppy Summer", "2023-05-01", "2023-08-31")
    run("Multi-Year",    "2021-01-01", "2026-05-30")
    print("\n  LESSON: Fast crossovers generate too many trades.")
    print("  The fee bleed and whipsaw destroy returns in choppy markets.")
    print("  -> We need a SLOWER, more selective trend filter.")
    print("=" * 60)









# """
# STEP 1: Naive EMA Crossover Strategy (The First Attempt)
# Uses EMA20/EMA50 crossover on 4H candles — a common beginner approach.
# LESSON: Fast crossovers on crypto = death by a thousand cuts (whipsaw + fees).
# """
# import pandas as pd, numpy as np
# from datetime import datetime, timedelta
# from binance.client import Client
# from config import SYMBOLS

# INITIAL_CASH = 1000.0
# FEE_RATE = 0.001
# EMA_FAST, EMA_SLOW = 20, 50
# client = Client()

# SYM_A, SYM_B = SYMBOLS[0], SYMBOLS[1]   # from screener (e.g. ETHUSDT, BNBUSDT)


# def fetch(symbol, start, end):
#     warmup = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d")
#     kl = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_4HOUR, warmup, end)
#     df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol","ct","qv","t","tb","tq","ig"])
#     df["time"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
#     df["close"] = df["close"].astype(float)
#     df = df[["time","close"]].set_index("time")
#     df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
#     df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
#     s, e = pd.to_datetime(start).tz_localize("UTC"), pd.to_datetime(end).tz_localize("UTC")
#     return df.loc[s:e]


# def run(name, start, end):
#     df_a = fetch(SYM_A, start, end)
#     df_b = fetch(SYM_B, start, end)

#     cash, pos, entry, trades, fees = INITIAL_CASH, 0, 0.0, 0, 0.0
#     eq = []

#     for ts in df_a.index.intersection(df_b.index):
#         pa, pb = df_a.loc[ts, "close"], df_b.loc[ts, "close"]
#         a_bull = df_a.loc[ts, "ema_fast"] > df_a.loc[ts, "ema_slow"]
#         b_bull = df_b.loc[ts, "ema_fast"] > df_b.loc[ts, "ema_slow"]

#         if pos == 0:
#             if a_bull:
#                 pos, entry = 1, pa; f = cash * FEE_RATE; cash -= f; fees += f; trades += 1
#             elif b_bull:
#                 pos, entry = 2, pb; f = cash * FEE_RATE; cash -= f; fees += f; trades += 1
#         elif pos == 1 and not a_bull:
#             v = cash * (pa / entry); f = v * FEE_RATE; cash = v - f; fees += f; pos = 0; trades += 1
#         elif pos == 2 and not b_bull:
#             v = cash * (pb / entry); f = v * FEE_RATE; cash = v - f; fees += f; pos = 0; trades += 1

#         eq.append(cash if pos == 0 else cash * (pa / entry) if pos == 1 else cash * (pb / entry))

#     es = pd.Series(eq)
#     ret = (es.iloc[-1] / INITIAL_CASH - 1) * 100
#     dd = ((es - es.cummax())n / es.cummax()).min() * 100
#     print(f"\n  --- {name} ({start} to {end}) ---")
#     print(f"    Return:    {ret:+.2f}%  |  Max DD: {dd:.2f}%  |  Trades: {trades}  |  Fees: ${fees:.2f}")
#     return ret


# if __name__ == "__main__":
#     print("=" * 60)
#     print(f"  STEP 1: NAIVE EMA20/50 CROSSOVER — The Beginner's Trap")
#     print(f"  Assets: {SYM_A} + {SYM_B} (from volatility screener)")
#     print("=" * 60)
#     run("Bear Crash",    "2021-11-01", "2022-01-31")
#     run("Choppy Summer", "2023-05-01", "2023-08-31")
#     run("Multi-Year",    "2021-01-01", "2026-05-30")
#     print("\n  LESSON: Fast crossovers generate too many trades.")
#     print("  The fee bleed and whipsaw destroy returns in choppy markets.")
#     print("  → We need a SLOWER, more selective trend filter.")
#     print("=" * 60)