"""
strategy_live.py — EMA + ADX Momentum Strategy on Binance Demo

Places real orders on demo.binance.com using the best-performing strategy:
  ENTER: price > EMA AND ADX > threshold (confirmed strong uptrend)
  EXIT:  price < EMA (trend broken — get out fast)
  CHOOSE: when both assets signal, pick the one with higher ADX

Parameters (EMA period / ADX period / ADX threshold) come from config.py,
which reads tuned_params.json — so the LIVE bot trades the exact parameters
that were tuned on 2017-2020 and validated out-of-sample on 2021-2026.

Run:   python strategy_live.py
Watch: https://demo.binance.com -> Spot -> Orders / Assets
Stop:  Ctrl+C
"""
import os
import time
import numpy as np
import pandas as pd
from decimal import Decimal
from binance.client import Client
from dotenv import load_dotenv

# ================= CONFIGURATION =================
INTERVAL = "4h"
from config import SYMBOLS, SYM_A, SYM_B, EMA_PERIOD, ADX_PERIOD, ADX_THRESHOLD, PARAMS_ARE_TUNED
MIN_TRADE_USD = 15.0
# =================================================

load_dotenv()
client = Client(os.getenv("DEMO_API_KEY"), os.getenv("DEMO_API_SECRET"), demo=True)

# Cache for precision settings to avoid API overload
_symbol_info = {}


def get_step_size(sym):
    """Fetches Binance step size to ensure order quantity is valid."""
    if sym not in _symbol_info:
        info = client.get_symbol_info(sym)
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                _symbol_info[sym] = float(f['stepSize'])
    return _symbol_info[sym]


def _round_down(qty, step):
    """Rounds quantity down to the nearest step size allowed by Binance."""
    return float((Decimal(str(qty)) // Decimal(str(step))) * Decimal(str(step)))


def _calc_adx(df, period):
    """Calculates ADX (Average Directional Index) to measure trend strength."""
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    up = df["high"] - df["high"].shift(1)
    dn = df["low"].shift(1) - df["low"]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / atr
    dx = 100 * (abs(pdi - mdi) / (pdi + mdi))
    return dx.ewm(alpha=1/period, adjust=False).mean()


def get_trend_state():
    """
    For each symbol, returns:
      - above_ema: True if Price > EMA
      - buy_signal: True if above_ema AND ADX > threshold (strong trend)
      - adx_value: the current ADX reading
    """
    states = {}
    for sym in SYMBOLS:
        kl = client.get_klines(symbol=sym, interval=INTERVAL, limit=max(250, EMA_PERIOD + 50))
        df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol",
                                        "ct","qv","t","tb","tq","ig"])
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].astype(float)

        ema = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1]
        adx = _calc_adx(df, ADX_PERIOD).iloc[-1]
        price = df["close"].iloc[-1]

        above_ema = price > ema
        states[sym] = {
            "above_ema": above_ema,
            "buy_signal": above_ema and (adx > ADX_THRESHOLD),
            "adx": adx,
            "price": price,
        }
    return states


def rebalance():
    # 1. Get Trend + Momentum State
    states = get_trend_state()

    # 2. Determine target allocation (EMA + ADX logic)
    a, b = states[SYM_A], states[SYM_B]

    if a["buy_signal"] and b["buy_signal"]:
        # Both trending strongly — pick the stronger one (higher ADX)
        if a["adx"] >= b["adx"]:
            targets = {SYM_A: 1.0, SYM_B: 0.0}
        else:
            targets = {SYM_A: 0.0, SYM_B: 1.0}
    elif a["buy_signal"]:
        targets = {SYM_A: 1.0, SYM_B: 0.0}
    elif b["buy_signal"]:
        targets = {SYM_A: 0.0, SYM_B: 1.0}
    else:
        # Neither has strong trend — sit in cash
        targets = {SYM_A: 0.0, SYM_B: 0.0}

    # Print status
    for sym in SYMBOLS:
        s = states[sym]
        ema_icon = "ABOVE" if s["above_ema"] else "below"
        adx_icon = "STRONG" if s["adx"] > ADX_THRESHOLD else "weak"
        print(f"  {sym}: {ema_icon} EMA  ADX={s['adx']:.1f}({adx_icon})  target={targets[sym]:.0%}")

    # 3. Get current total portfolio equity
    usdt_free = float(client.get_asset_balance(asset="USDT")["free"])
    current_values = {}
    total_equity = usdt_free
    for sym in SYMBOLS:
        base = sym.replace("USDT", "")
        bal = float(client.get_asset_balance(asset=base)["free"])
        price = float(client.get_symbol_ticker(symbol=sym)["price"])
        current_values[sym] = bal * price
        total_equity += current_values[sym]

    print(f"  Equity: ${total_equity:.2f} | USDT: ${usdt_free:.2f}")

    # 4. Execute orders — SELL first (to free up USDT), then BUY
    for sym in SYMBOLS:
        target_val = total_equity * targets[sym]
        curr_val = current_values[sym]
        diff = target_val - curr_val

        if diff < -MIN_TRADE_USD:  # SELL
            price = float(client.get_symbol_ticker(symbol=sym)["price"])
            qty = abs(diff) / price
            step = get_step_size(sym)
            qty = _round_down(qty, step)
            if qty > 0:
                client.order_market_sell(symbol=sym, quantity=qty)
                print(f"  [SELL] {sym} | ${abs(diff):.2f}")

    for sym in SYMBOLS:
        target_val = total_equity * targets[sym]
        curr_val = current_values[sym]
        diff = target_val - curr_val

        if diff > MIN_TRADE_USD:  # BUY
            price = float(client.get_symbol_ticker(symbol=sym)["price"])
            qty = abs(diff) / price
            step = get_step_size(sym)
            qty = _round_down(qty, step)
            if qty > 0:
                client.order_market_buy(symbol=sym, quantity=qty)
                print(f"  [BUY]  {sym} | ${diff:.2f}")


if __name__ == "__main__":
    # Startup: show connection + balance
    acct = client.get_account()
    usdt = float(next(b["free"] for b in acct["balances"] if b["asset"] == "USDT"))
    src = "TUNED" if PARAMS_ARE_TUNED else "DEFAULT"
    print("=" * 55)
    print("  LIVE: EMA + ADX Momentum (Demo)")
    print("=" * 55)
    print(f"  Connected to demo.binance.com | USDT: ${usdt:,.2f}")
    print(f"  EMA{EMA_PERIOD} + ADX{ADX_PERIOD} (threshold={ADX_THRESHOLD})  [{src} params]")
    print(f"  Checking every 1 hour | Ctrl+C to stop")
    print("=" * 55 + "\n")

    while True:
        try:
            rebalance()
            print()
        except Exception as e:
            print(f"  [ERR] {e}")
        # 4H candles — check every hour to catch every close
        time.sleep(30)









# """
# strategy_live.py — EMA200 + ADX Momentum Strategy on Binance Demo

# Places real orders on demo.binance.com using the best-performing strategy:
#   ENTER: price > EMA200 AND ADX > 20 (confirmed strong uptrend)
#   EXIT:  price < EMA200 (trend broken — get out fast)
#   CHOOSE: when both assets signal, pick the one with higher ADX

# Run:   python strategy_live.py
# Watch: https://demo.binance.com -> Spot -> Orders / Assets
# Stop:  Ctrl+C
# """
# import os
# import time
# import numpy as np
# import pandas as pd
# from decimal import Decimal
# from binance.client import Client
# from dotenv import load_dotenv

# # ================= CONFIGURATION =================
# INTERVAL = "4h"
# EMA_PERIOD = 200
# ADX_PERIOD = 14
# ADX_THRESHOLD = 20.0
# from config import SYMBOLS
# SYM_A, SYM_B = SYMBOLS[0], SYMBOLS[1]
# MIN_TRADE_USD = 15.0
# # =================================================

# load_dotenv()
# client = Client(os.getenv("DEMO_API_KEY"), os.getenv("DEMO_API_SECRET"), demo=True)

# # Cache for precision settings to avoid API overload
# _symbol_info = {}


# def get_step_size(sym):
#     """Fetches Binance step size to ensure order quantity is valid."""
#     if sym not in _symbol_info:
#         info = client.get_symbol_info(sym)
#         for f in info['filters']:
#             if f['filterType'] == 'LOT_SIZE':
#                 _symbol_info[sym] = float(f['stepSize'])
#     return _symbol_info[sym]


# def _round_down(qty, step):
#     """Rounds quantity down to the nearest step size allowed by Binance."""
#     return float((Decimal(str(qty)) // Decimal(str(step))) * Decimal(str(step)))


# def _calc_adx(df, period):
#     """Calculates ADX (Average Directional Index) to measure trend strength."""
#     tr = pd.concat([
#         df["high"] - df["low"],
#         (df["high"] - df["close"].shift(1)).abs(),
#         (df["low"] - df["close"].shift(1)).abs()
#     ], axis=1).max(axis=1)
#     up = df["high"] - df["high"].shift(1)
#     dn = df["low"].shift(1) - df["low"]
#     plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
#     minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
#     atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
#     pdi = 100 * pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / atr
#     mdi = 100 * pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / atr
#     dx = 100 * (abs(pdi - mdi) / (pdi + mdi))
#     return dx.ewm(alpha=1/period, adjust=False).mean()


# def get_trend_state():
#     """
#     For each symbol, returns:
#       - above_ema: True if Price > EMA200
#       - buy_signal: True if above_ema AND ADX > threshold (strong trend)
#       - adx_value: the current ADX reading
#     """
#     states = {}
#     for sym in SYMBOLS:
#         kl = client.get_klines(symbol=sym, interval=INTERVAL, limit=250)
#         df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol",
#                                         "ct","qv","t","tb","tq","ig"])
#         for c in ["open", "high", "low", "close"]:
#             df[c] = df[c].astype(float)

#         ema = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1]
#         adx = _calc_adx(df, ADX_PERIOD).iloc[-1]
#         price = df["close"].iloc[-1]

#         above_ema = price > ema
#         states[sym] = {
#             "above_ema": above_ema,
#             "buy_signal": above_ema and (adx > ADX_THRESHOLD),
#             "adx": adx,
#             "price": price,
#         }
#     return states


# def rebalance():
#     # 1. Get Trend + Momentum State
#     states = get_trend_state()

#     # 2. Determine target allocation (EMA200 + ADX logic)
#     eth, bnb = states[SYM_A], states[SYM_B]

#     if eth["buy_signal"] and bnb["buy_signal"]:
#         # Both trending strongly — pick the stronger one (higher ADX)
#         if eth["adx"] >= bnb["adx"]:
#             targets = {SYM_A: 1.0, SYM_B: 0.0}
#         else:
#             targets = {SYM_A: 0.0, SYM_B: 1.0}
#     elif eth["buy_signal"]:
#         targets = {SYM_A: 1.0, SYM_B: 0.0}
#     elif bnb["buy_signal"]:
#         targets = {SYM_A: 0.0, SYM_B: 1.0}
#     else:
#         # Neither has strong trend — sit in cash
#         targets = {SYM_A: 0.0, SYM_B: 0.0}

#     # Print status
#     for sym in SYMBOLS:
#         s = states[sym]
#         ema_icon = "▲" if s["above_ema"] else "▼"
#         adx_icon = "STRONG" if s["adx"] > ADX_THRESHOLD else "weak"
#         print(f"  {sym}: {ema_icon}EMA  ADX={s['adx']:.1f}({adx_icon})  target={targets[sym]:.0%}")

#     # 3. Get current total portfolio equity
#     usdt_free = float(client.get_asset_balance(asset="USDT")["free"])
#     current_values = {}
#     total_equity = usdt_free
#     for sym in SYMBOLS:
#         base = sym.replace("USDT", "")
#         bal = float(client.get_asset_balance(asset=base)["free"])
#         price = float(client.get_symbol_ticker(symbol=sym)["price"])
#         current_values[sym] = bal * price
#         total_equity += current_values[sym]

#     print(f"  Equity: ${total_equity:.2f} | USDT: ${usdt_free:.2f}")

#     # 4. Execute orders — SELL first (to free up USDT), then BUY
#     for sym in SYMBOLS:
#         target_val = total_equity * targets[sym]
#         curr_val = current_values[sym]
#         diff = target_val - curr_val

#         if diff < -MIN_TRADE_USD:  # SELL
#             price = float(client.get_symbol_ticker(symbol=sym)["price"])
#             qty = abs(diff) / price
#             step = get_step_size(sym)
#             qty = _round_down(qty, step)
#             if qty > 0:
#                 client.order_market_sell(symbol=sym, quantity=qty)
#                 print(f"  [SELL] {sym} | ${abs(diff):.2f}")

#     for sym in SYMBOLS:
#         target_val = total_equity * targets[sym]
#         curr_val = current_values[sym]
#         diff = target_val - curr_val

#         if diff > MIN_TRADE_USD:  # BUY
#             price = float(client.get_symbol_ticker(symbol=sym)["price"])
#             qty = abs(diff) / price
#             step = get_step_size(sym)
#             qty = _round_down(qty, step)
#             if qty > 0:
#                 client.order_market_buy(symbol=sym, quantity=qty)
#                 print(f"  [BUY]  {sym} | ${diff:.2f}")


# if __name__ == "__main__":
#     # Startup: show connection + balance
#     acct = client.get_account()
#     usdt = float(next(b["free"] for b in acct["balances"] if b["asset"] == "USDT"))
#     print("=" * 55)
#     print("  LIVE: EMA200 + ADX Momentum (Demo)")
#     print("=" * 55)
#     print(f"  Connected to demo.binance.com | USDT: ${usdt:,.2f}")
#     print(f"  EMA{EMA_PERIOD} + ADX{ADX_PERIOD} (threshold={ADX_THRESHOLD})")
#     print(f"  Checking every 1 hour | Ctrl+C to stop")
#     print("=" * 55 + "\n")

#     while True:
#         try:
#             rebalance()
#             print()
#         except Exception as e:
#             print(f"  [ERR] {e}")
#         # 4H candles — check every hour to catch every close
#         time.sleep(3600)