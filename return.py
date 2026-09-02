import os
import pandas as pd
from binance.client import Client

INITIAL_CASH = 1000.0
FEE_RATE = 0.001

# =========================
# DATA DOWNLOAD
# =========================

SYMBOLS = ["ETHUSDT", "BNBUSDT"]
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
START = "2026-02-25"
END = "2026-05-31"

def download_data():
    os.makedirs("data", exist_ok=True)
    client = Client()

    for sym in SYMBOLS:
        path = f"data/{sym}.csv"

        # Skip download if file already exists
        if os.path.exists(path):
            continue

        kl = client.get_historical_klines(
            sym,
            INTERVAL,
            START,
            END
        )

        df = pd.DataFrame(
            kl,
            columns=[
                "open_time", "open", "high", "low", "close",
                "volume", "close_time", "qv", "trades",
                "tb", "tq", "ig"
            ]
        )

        df["time"] = pd.to_datetime(
            df["open_time"],
            unit="ms",
            utc=True
        )

        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)

        df = (
            df[["time", "open", "high", "low", "close", "volume"]]
            .set_index("time")
        )

        df.to_csv(path)


# =========================
# STRATEGY
# =========================

def get_4h_data(symbol):
    df = pd.read_csv(
        f"data/{symbol}.csv",
        index_col="time",
        parse_dates=True
    )

    df = df.resample("4h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last"
    })

    df["ema"] = df["close"].ewm(span=200).mean()

    return df.loc["2026-05-01":"2026-05-30"]


def simulate_swing_strategy():
    # 1. Add suffixes to prevent column name overlaps
    eth_df = get_4h_data("ETHUSDT").add_suffix('_eth')
    bnb_df = get_4h_data("BNBUSDT").add_suffix('_bnb')

    # 2. Join them on their time index to ensure they are perfectly aligned
    df = eth_df.join(bnb_df, how='inner')

    cash = INITIAL_CASH
    pos = 0
    entry_price = 0

    equity_curve = []

    # 3. Loop over the aligned DataFrame
    for i in range(1, len(df)):
        p_eth = df["close_eth"].iloc[i]
        p_bnb = df["close_bnb"].iloc[i]

        eth_bull = p_eth > df["ema_eth"].iloc[i]
        bnb_bull = p_bnb > df["ema_bnb"].iloc[i]

        if pos == 0:
            if eth_bull:
                pos = 1
                entry_price = p_eth
                cash *= (1 - FEE_RATE)

            elif bnb_bull:
                pos = 2
                entry_price = p_bnb
                cash *= (1 - FEE_RATE)

        elif pos == 1:
            if not eth_bull:
                cash = (
                    cash * (p_eth / entry_price)
                ) * (1 - FEE_RATE)
                pos = 0

        elif pos == 2:
            if not bnb_bull:
                cash = (
                    cash * (p_bnb / entry_price)
                ) * (1 - FEE_RATE)
                pos = 0

        if pos == 0:
            curr_val = cash
        elif pos == 1:
            curr_val = cash * (p_eth / entry_price)
        else:
            curr_val = cash * (p_bnb / entry_price)

        equity_curve.append(curr_val)

    return pd.Series(equity_curve, index=df.index[1:])


if __name__ == "__main__":
    download_data()

    equity = simulate_swing_strategy()

    # This will be the only output printed to the terminal
    print(
        f"Swing Trend Return: "
        f"{((equity.iloc[-1] / INITIAL_CASH) - 1) * 100:.2f}%"
    )









# import os
# import pandas as pd
# from binance.client import Client

# # Import the symbols from your config file
# from config import SYMBOLS

# INITIAL_CASH = 1000.0
# FEE_RATE = 0.001

# # =========================
# # DATA DOWNLOAD
# # =========================

# INTERVAL = Client.KLINE_INTERVAL_5MINUTE
# START = "2026-02-25"
# END = "2026-05-31"

# def download_data():
#     os.makedirs("data", exist_ok=True)
#     client = Client()

#     for sym in SYMBOLS:
#         path = f"data/{sym}.csv"

#         # Skip download if file already exists
#         if os.path.exists(path):
#             continue

#         kl = client.get_historical_klines(
#             sym,
#             INTERVAL,
#             START,
#             END
#         )

#         df = pd.DataFrame(
#             kl,
#             columns=[
#                 "open_time", "open", "high", "low", "close",
#                 "volume", "close_time", "qv", "trades",
#                 "tb", "tq", "ig"
#             ]
#         )

#         df["time"] = pd.to_datetime(
#             df["open_time"],
#             unit="ms",
#             utc=True
#         )

#         for c in ["open", "high", "low", "close", "volume"]:
#             df[c] = df[c].astype(float)

#         df = (
#             df[["time", "open", "high", "low", "close", "volume"]]
#             .set_index("time")
#         )

#         df.to_csv(path)


# # =========================
# # STRATEGY
# # =========================

# def get_4h_data(symbol):
#     df = pd.read_csv(
#         f"data/{symbol}.csv",
#         index_col="time",
#         parse_dates=True
#     )

#     df = df.resample("4h").agg({
#         "open": "first",
#         "high": "max",
#         "low": "min",
#         "close": "last"
#     })

#     df["ema"] = df["close"].ewm(span=200).mean()

#     return df.loc["2026-05-01":"2026-05-30"]


# def simulate_swing_strategy():
#     # Dynamically pull the two symbols from the config list
#     sym1 = SYMBOLS[0]
#     sym2 = SYMBOLS[1]

#     # Use generic suffixes so the strategy works for ANY two coins
#     df1 = get_4h_data(sym1).add_suffix('_1')
#     df2 = get_4h_data(sym2).add_suffix('_2')

#     df = df1.join(df2, how='inner')

#     cash = INITIAL_CASH
#     pos = 0
#     entry_price = 0

#     equity_curve = []

#     for i in range(1, len(df)):
#         p1 = df["close_1"].iloc[i]
#         p2 = df["close_2"].iloc[i]

#         bull_1 = p1 > df["ema_1"].iloc[i]
#         bull_2 = p2 > df["ema_2"].iloc[i]

#         if pos == 0:
#             if bull_1:
#                 pos = 1
#                 entry_price = p1
#                 cash *= (1 - FEE_RATE)

#             elif bull_2:
#                 pos = 2
#                 entry_price = p2
#                 cash *= (1 - FEE_RATE)

#         elif pos == 1:
#             if not bull_1:
#                 cash = (
#                     cash * (p1 / entry_price)
#                 ) * (1 - FEE_RATE)
#                 pos = 0

#         elif pos == 2:
#             if not bull_2:
#                 cash = (
#                     cash * (p2 / entry_price)
#                 ) * (1 - FEE_RATE)
#                 pos = 0

#         if pos == 0:
#             curr_val = cash
#         elif pos == 1:
#             curr_val = cash * (p1 / entry_price)
#         else:
#             curr_val = cash * (p2 / entry_price)

#         equity_curve.append(curr_val)

#     return pd.Series(equity_curve, index=df.index[1:])


# if __name__ == "__main__":
#     # Ensure we have exactly two symbols configured for this specific strategy
#     if len(SYMBOLS) != 2:
#         raise ValueError("This specific strategy requires exactly two symbols in config.py")

#     download_data()

#     equity = simulate_swing_strategy()

#     print(
#         f"Swing Trend Return: "
#         f"{((equity.iloc[-1] / INITIAL_CASH) - 1) * 100:.2f}%"
#     )