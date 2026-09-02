"""
returns.py — Final returns summary for the EMA + ADX strategy.
Self-contained: fetches its own data from Binance, runs the backtest,
and prints a clean summary with CAGR calculation.

Parameters come from config.py (tuned_params.json, written by tune_params.py
on PRE-2021 data). The 2021-2026 period below is therefore OUT-OF-SAMPLE.
Falls back to EMA200/ADX14/thr20 if the tuner hasn't been run.

Run: python returns.py
"""
import pandas as pd, numpy as np
from datetime import datetime, timedelta
from binance.client import Client
from config import SYM_A, SYM_B, EMA_PERIOD, ADX_PERIOD, ADX_THRESHOLD, PARAMS_ARE_TUNED

INITIAL_CASH = 1000.0
FEE_RATE = 0.001
client = Client()


def add_adx(df, period):
    df["tr"] = pd.concat([df["high"]-df["low"],
                          (df["high"]-df["close"].shift(1)).abs(),
                          (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
    up = df["high"] - df["high"].shift(1)
    dn = df["low"].shift(1) - df["low"]
    df["+dm"] = np.where((up > dn) & (up > 0), up, 0.0)
    df["-dm"] = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = df["tr"].ewm(alpha=1/period, adjust=False).mean()
    pdi = 100*(df["+dm"].ewm(alpha=1/period, adjust=False).mean()/atr)
    mdi = 100*(df["-dm"].ewm(alpha=1/period, adjust=False).mean()/atr)
    dx = 100*(abs(pdi-mdi)/(pdi+mdi))
    df["adx"] = dx.ewm(alpha=1/period, adjust=False).mean()
    df.drop(columns=["tr","+dm","-dm"], inplace=True)
    return df


def fetch(symbol, start, end):
    warmup = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=70)).strftime("%Y-%m-%d")
    kl = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_4HOUR, warmup, end)
    df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol","ct","qv","t","tb","tq","ig"])
    df["time"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
    for c in ["open","high","low","close"]: df[c] = df[c].astype(float)
    df = df[["time","open","high","low","close"]].set_index("time")
    df["ema"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    df = add_adx(df, ADX_PERIOD)
    s, e = pd.to_datetime(start).tz_localize("UTC"), pd.to_datetime(end).tz_localize("UTC")
    return df.loc[s:e]


def backtest(start, end):
    df_a, df_b = fetch(SYM_A, start, end), fetch(SYM_B, start, end)
    cash, pos, entry, trades, fees = INITIAL_CASH, 0, 0.0, 0, 0.0
    eq = []
    wins = 0
    for ts in df_a.index.intersection(df_b.index):
        pa, pb = df_a.loc[ts,"close"], df_b.loc[ts,"close"]
        a_buy = (pa > df_a.loc[ts,"ema"]) and (df_a.loc[ts,"adx"] > ADX_THRESHOLD)
        b_buy = (pb > df_b.loc[ts,"ema"]) and (df_b.loc[ts,"adx"] > ADX_THRESHOLD)
        a_exit = pa <= df_a.loc[ts,"ema"]
        b_exit = pb <= df_b.loc[ts,"ema"]
        if pos == 0:
            if a_buy and not b_buy: pos, entry = 1, pa
            elif b_buy and not a_buy: pos, entry = 2, pb
            elif a_buy and b_buy:
                pos, entry = (1, pa) if df_a.loc[ts,"adx"] >= df_b.loc[ts,"adx"] else (2, pb)
            if pos > 0: f = cash*FEE_RATE; cash -= f; fees += f; trades += 1
        elif pos == 1 and a_exit:
            v = cash*(pa/entry)
            if pa > entry: wins += 1
            f = v*FEE_RATE; cash = v-f; fees += f; pos = 0; trades += 1
        elif pos == 2 and b_exit:
            v = cash*(pb/entry)
            if pb > entry: wins += 1
            f = v*FEE_RATE; cash = v-f; fees += f; pos = 0; trades += 1
        eq.append(cash if pos==0 else cash*(pa/entry) if pos==1 else cash*(pb/entry))
    es = pd.Series(eq)
    return es, trades, fees, wins


if __name__ == "__main__":
    src = "TUNED on 2017-2020 — OUT-OF-SAMPLE" if PARAMS_ARE_TUNED else "DEFAULT params (run tune_params.py)"
    print("Fetching data from Binance (this takes a minute for 5+ years)...\n")

    start, end = "2021-01-01", "2026-05-30"
    equity, trades, fees, wins = backtest(start, end)

    final = equity.iloc[-1]
    ret = (final / INITIAL_CASH - 1) * 100
    dd = ((equity - equity.cummax()) / equity.cummax()).min() * 100
    years = (pd.to_datetime(end) - pd.to_datetime(start)).days / 365.25
    cagr = ((final / INITIAL_CASH) ** (1 / years) - 1) * 100
    win_rate = (wins / (trades // 2)) * 100 if trades > 1 else 0

    print("=" * 58)
    print("  FINAL RESULTS: EMA + ADX Momentum Strategy")
    print(f"  Assets: {SYM_A} + {SYM_B}")
    print(f"  Params: EMA{EMA_PERIOD} / ADX{ADX_PERIOD} / thr{ADX_THRESHOLD}")
    print(f"          {src}")
    print("=" * 58)
    print(f"  Period:            {start}  to  {end}  ({years:.1f} years)")
    print(f"  Starting Capital:  ${INITIAL_CASH:,.2f}")
    print(f"  Final Capital:     ${final:,.2f}")
    print(f"  ------------------------------------------------")
    print(f"  Total Return:      {ret:+,.2f}%")
    print(f"  CAGR:              {cagr:+.1f}% per year")
    print(f"  Max Drawdown:      {dd:.2f}%")
    print(f"  ------------------------------------------------")
    print(f"  Total Trades:      {trades}")
    print(f"  Win Rate:          {win_rate:.0f}%")
    print(f"  Total Fees Paid:   ${fees:,.2f}")
    print(f"  ------------------------------------------------")
    print(f"  $1,000 became:     ${final:,.2f}")
    print("=" * 58)