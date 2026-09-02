"""
STEP 2: EMA Trend Filter (The First Real Improvement)
Only holds an asset when price > EMA (confirmed uptrend), otherwise sits in cash.
LESSON: Slower filter = fewer trades = less fee bleed + catches big trends.

The EMA period comes from config.py (tuned on pre-2021 data). Falls back to 200.
"""
import pandas as pd, numpy as np
from datetime import datetime, timedelta
from binance.client import Client
from config import SYM_A, SYM_B, EMA_PERIOD, PARAMS_ARE_TUNED

INITIAL_CASH = 1000.0
FEE_RATE = 0.001
client = Client()


def fetch(symbol, start, end):
    warmup = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=70)).strftime("%Y-%m-%d")
    kl = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_4HOUR, warmup, end)
    df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol","ct","qv","t","tb","tq","ig"])
    df["time"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
    df["close"] = df["close"].astype(float)
    df = df[["time","close"]].set_index("time")
    df["ema"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    s, e = pd.to_datetime(start).tz_localize("UTC"), pd.to_datetime(end).tz_localize("UTC")
    return df.loc[s:e]


def run(name, start, end):
    df_a, df_b = fetch(SYM_A, start, end), fetch(SYM_B, start, end)
    cash, pos, entry, trades, fees = INITIAL_CASH, 0, 0.0, 0, 0.0
    eq = []
    for ts in df_a.index.intersection(df_b.index):
        pa, pb = df_a.loc[ts,"close"], df_b.loc[ts,"close"]
        a_bull = pa > df_a.loc[ts,"ema"]
        b_bull = pb > df_b.loc[ts,"ema"]
        if pos == 0:
            if a_bull and not b_bull:
                pos, entry = 1, pa
            elif b_bull and not a_bull:
                pos, entry = 2, pb
            elif a_bull and b_bull:
                ad = (pa - df_a.loc[ts,"ema"])/df_a.loc[ts,"ema"]
                bd = (pb - df_b.loc[ts,"ema"])/df_b.loc[ts,"ema"]
                pos, entry = (1, pa) if ad >= bd else (2, pb)
            if pos > 0:
                f = cash*FEE_RATE; cash -= f; fees += f; trades += 1
        elif pos == 1 and not a_bull:
            v = cash*(pa/entry); f = v*FEE_RATE; cash = v-f; fees += f; pos = 0; trades += 1
        elif pos == 2 and not b_bull:
            v = cash*(pb/entry); f = v*FEE_RATE; cash = v-f; fees += f; pos = 0; trades += 1
        eq.append(cash if pos==0 else cash*(pa/entry) if pos==1 else cash*(pb/entry))
    es = pd.Series(eq)
    ret = (es.iloc[-1]/INITIAL_CASH - 1)*100
    dd = ((es - es.cummax())/es.cummax()).min()*100
    print(f"\n  --- {name} ({start} to {end}) ---")
    print(f"    Return:    {ret:+.2f}%  |  Max DD: {dd:.2f}%  |  Trades: {trades}  |  Fees: ${fees:.2f}")
    return ret


if __name__ == "__main__":
    src = "tuned" if PARAMS_ARE_TUNED else "default"
    print("="*60)
    print(f"  STEP 2: EMA{EMA_PERIOD} TREND FILTER — Catching Big Moves ({src})")
    print(f"  Assets: {SYM_A} + {SYM_B} (from volatility screener)")
    print("="*60)
    run("Bear Crash",   "2021-11-01", "2022-01-31")
    run("Choppy Summer","2023-05-01", "2023-08-31")
    r = run("Multi-Year",   "2021-01-01", "2026-05-30")
    years = 5.4
    cagr = ((1 + r/100)**(1/years) - 1)*100
    print(f"\n  Multi-Year CAGR: ~{cagr:.0f}% annualized")
    print("\n  IMPROVEMENT: Dramatically fewer trades vs Step 1.")
    print("  Bear markets: sits in cash. Bull markets: rides the trend.")
    print("  Weakness: Still enters some weak/choppy trends.")
    print("  -> Can we FILTER for trend STRENGTH, not just direction? (Step 4)")
    print("="*60)









# """
# STEP 2: EMA200 Trend Filter (The First Real Improvement)
# Only holds assets when price > EMA200 (confirmed uptrend), otherwise sits in cash.
# LESSON: Slower filter = fewer trades = less fee bleed + catches big trends.
# """
# import pandas as pd, numpy as np
# from datetime import datetime, timedelta
# from binance.client import Client
# from config import SYMBOLS

# INITIAL_CASH = 1000.0
# FEE_RATE = 0.001
# EMA_PERIOD = 200
# client = Client()

# SYM_A, SYM_B = SYMBOLS[0], SYMBOLS[1]


# def fetch(symbol, start, end):
#     warmup = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=40)).strftime("%Y-%m-%d")
#     kl = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_4HOUR, warmup, end)
#     df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol","ct","qv","t","tb","tq","ig"])
#     df["time"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
#     df["close"] = df["close"].astype(float)
#     df = df[["time","close"]].set_index("time")
#     df["ema"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
#     s, e = pd.to_datetime(start).tz_localize("UTC"), pd.to_datetime(end).tz_localize("UTC")
#     return df.loc[s:e]


# def run(name, start, end):
#     df_a, df_b = fetch(SYM_A, start, end), fetch(SYM_B, start, end)
#     cash, pos, entry, trades, fees = INITIAL_CASH, 0, 0.0, 0, 0.0
#     eq = []
#     for ts in df_a.index.intersection(df_b.index):
#         pa, pb = df_a.loc[ts,"close"], df_b.loc[ts,"close"]
#         a_bull = pa > df_a.loc[ts,"ema"]
#         b_bull = pb > df_b.loc[ts,"ema"]
#         if pos == 0:
#             if a_bull and not b_bull:
#                 pos, entry = 1, pa
#             elif b_bull and not a_bull:
#                 pos, entry = 2, pb
#             elif a_bull and b_bull:
#                 ad = (pa - df_a.loc[ts,"ema"])/df_a.loc[ts,"ema"]
#                 bd = (pb - df_b.loc[ts,"ema"])/df_b.loc[ts,"ema"]
#                 pos, entry = (1, pa) if ad >= bd else (2, pb)
#             if pos > 0:
#                 f = cash*FEE_RATE; cash -= f; fees += f; trades += 1
#         elif pos == 1 and not a_bull:
#             v = cash*(pa/entry); f = v*FEE_RATE; cash = v-f; fees += f; pos = 0; trades += 1
#         elif pos == 2 and not b_bull:
#             v = cash*(pb/entry); f = v*FEE_RATE; cash = v-f; fees += f; pos = 0; trades += 1
#         eq.append(cash if pos==0 else cash*(pa/entry) if pos==1 else cash*(pb/entry))
#     es = pd.Series(eq)
#     ret = (es.iloc[-1]/INITIAL_CASH - 1)*100
#     dd = ((es - es.cummax())/es.cummax()).min()*100
#     print(f"\n  --- {name} ({start} to {end}) ---")
#     print(f"    Return:    {ret:+.2f}%  |  Max DD: {dd:.2f}%  |  Trades: {trades}  |  Fees: ${fees:.2f}")
#     return ret2


# if __name__ == "__main__":
#     print("="*60)
#     print(f"  STEP 2: EMA200 TREND FILTER — Catching Big Moves")
#     print(f"  Assets: {SYM_A} + {SYM_B} (from volatility screener)")
#     print("="*60)
#     run("Bear Crash",   "2021-11-01", "2022-01-31")
#     run("Choppy Summer","2023-05-01", "2023-08-31")
#     r = run("Multi-Year",   "2021-01-01", "2026-05-30")
#     years = 5.4
#     cagr = ((1 + r/100)**(1/years) - 1)*100
#     print(f"\n  Multi-Year CAGR: ~{cagr:.0f}% annualized")
#     print("\n  IMPROVEMENT: Dramatically fewer trades vs Step 1.")
#     print("  Bear markets: sits in cash. Bull markets: rides the trend.")
#     print("  Weakness: Still enters some weak/choppy trends.")
#     print("  → Can we FILTER for trend STRENGTH, not just direction?")
#     print("="*60)