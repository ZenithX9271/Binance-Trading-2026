"""
STEP 3.5: Walk-Forward Parameter Tuning  (eliminates data leakage)
==================================================================
Grid-searches the EMA200+ADX strategy's three parameters on a PRE-2021
TRAINING window (in-sample), picks the best combo by risk-adjusted return
(Sharpe), and writes it to tuned_params.json.

Because config.py reads tuned_params.json, the 2021-2026 "Multi-Year" test in
4_backtest_ema200_adx.py then uses parameters chosen WITHOUT ever seeing the
test data — making that result a true OUT-OF-SAMPLE / walk-forward number.

IMPORTANT — data availability:
  Binance launched July 2017. ETHUSDT lists ~Aug 2017 and BNBUSDT ~Nov 2017,
  so there is NO Binance data for 2016. The training window therefore starts at
  the earliest both assets exist (~Sep 2017) and runs through end-2020. If your
  screener picks even newer coins, the tuner auto-trims to the data it can get.

Run:  python tune_parameters.py      (do this BEFORE the backtests)
"""
import json, itertools
import numpy as np, pandas as pd
from datetime import datetime, timedelta
from binance.client import Client
from config import SYM_A, SYM_B

# ----------------- settings -----------------
INITIAL_CASH   = 1000.0
FEE_RATE       = 0.001
BARS_PER_YEAR  = 6 * 365            # 4H candles -> 6 per day
INTERVAL       = Client.KLINE_INTERVAL_4HOUR

TRAIN_START    = "2017-09-01"       # earliest both ETH & BNB exist on Binance
TRAIN_END      = "2020-12-31"       # everything from 2021 on is the OOS test
WARMUP_DAYS    = 70                 # enough to seed EMA up to span 300

# search grid (3 parameters)
EMA_GRID       = [100, 150, 200, 250, 300]
ADX_PERIOD_GRID= [10, 14, 20]
ADX_THR_GRID   = [15, 20, 25, 30]

# objective: maximise Sharpe, but ignore combos that barely trade
MIN_TRADES     = 10
# ---------------------------------------------

client = Client()


def fetch(symbol, start, end):
    """Fetch raw 4H OHLC with warmup. Returns whatever Binance has (auto-trims)."""
    warmup = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    kl = client.get_historical_klines(symbol, INTERVAL, warmup, end)
    df = pd.DataFrame(kl, columns=["ot","open","high","low","close","vol",
                                   "ct","qv","t","tb","tq","ig"])
    df["time"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
    for c in ["open","high","low","close"]:
        df[c] = df[c].astype(float)
    return df[["time","open","high","low","close"]].set_index("time")


def add_indicators(raw, ema_p, adx_p):
    """Compute EMA + ADX on the FULL series (warmup included), causally."""
    df = raw.copy()
    df["ema"] = df["close"].ewm(span=ema_p, adjust=False).mean()
    tr = pd.concat([df["high"]-df["low"],
                    (df["high"]-df["close"].shift(1)).abs(),
                    (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
    up = df["high"] - df["high"].shift(1)
    dn = df["low"].shift(1) - df["low"]
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    atr = tr.ewm(alpha=1/adx_p, adjust=False).mean()
    pdi = 100*(pdm.ewm(alpha=1/adx_p, adjust=False).mean()/atr)
    mdi = 100*(mdm.ewm(alpha=1/adx_p, adjust=False).mean()/atr)
    dx  = 100*((pdi-mdi).abs()/(pdi+mdi))
    df["adx"] = dx.ewm(alpha=1/adx_p, adjust=False).mean()
    return df


def backtest(raw_a, raw_b, ema_p, adx_p, adx_thr, start, end):
    """Run the EMA200+ADX rotation on the train window; return metrics dict."""
    a = add_indicators(raw_a, ema_p, adx_p)
    b = add_indicators(raw_b, ema_p, adx_p)
    s = pd.to_datetime(start).tz_localize("UTC")
    e = pd.to_datetime(end).tz_localize("UTC")
    a, b = a.loc[s:e], b.loc[s:e]

    cash, pos, entry, trades = INITIAL_CASH, 0, 0.0, 0
    eq = []
    for ts in a.index.intersection(b.index):
        pa, pb = a.loc[ts,"close"], b.loc[ts,"close"]
        a_buy = (pa > a.loc[ts,"ema"]) and (a.loc[ts,"adx"] > adx_thr)
        b_buy = (pb > b.loc[ts,"ema"]) and (b.loc[ts,"adx"] > adx_thr)
        a_exit = pa <= a.loc[ts,"ema"]
        b_exit = pb <= b.loc[ts,"ema"]
        if pos == 0:
            if a_buy and not b_buy:   pos, entry = 1, pa
            elif b_buy and not a_buy: pos, entry = 2, pb
            elif a_buy and b_buy:
                pos, entry = (1, pa) if a.loc[ts,"adx"] >= b.loc[ts,"adx"] else (2, pb)
            if pos > 0:
                cash *= (1 - FEE_RATE); trades += 1
        elif pos == 1 and a_exit:
            cash = cash*(pa/entry)*(1 - FEE_RATE); pos = 0; trades += 1
        elif pos == 2 and b_exit:
            cash = cash*(pb/entry)*(1 - FEE_RATE); pos = 0; trades += 1
        eq.append(cash if pos==0 else cash*(pa/entry) if pos==1 else cash*(pb/entry))

    es = pd.Series(eq)
    if len(es) < 2:
        return dict(ret=0.0, dd=0.0, sharpe=0.0, trades=trades, final=INITIAL_CASH)
    ret = (es.iloc[-1]/INITIAL_CASH - 1)*100
    dd  = ((es - es.cummax())/es.cummax()).min()*100
    r   = es.pct_change().dropna()
    sharpe = (r.mean()/r.std()*np.sqrt(BARS_PER_YEAR)) if r.std() > 0 else 0.0
    return dict(ret=ret, dd=dd, sharpe=sharpe, trades=trades, final=es.iloc[-1])


def main():
    print("="*64)
    print("  STEP 3.5: PARAMETER TUNING (in-sample) — NO DATA LEAKAGE")
    print("="*64)
    print(f"  Assets:        {SYM_A} + {SYM_B}")
    print(f"  Train window:  {TRAIN_START} -> {TRAIN_END}  (pre-2021 only)")
    print(f"  Objective:     max Sharpe, min {MIN_TRADES} trades")
    print(f"  Grid:          EMA{EMA_GRID}  ADXp{ADX_PERIOD_GRID}  thr{ADX_THR_GRID}")
    print("="*64)

    print("\n  Downloading training data (this only needs to happen once)...")
    raw_a = fetch(SYM_A, TRAIN_START, TRAIN_END)
    raw_b = fetch(SYM_B, TRAIN_START, TRAIN_END)
    got_a = raw_a.index.min().date() if len(raw_a) else None
    got_b = raw_b.index.min().date() if len(raw_b) else None
    print(f"    {SYM_A}: {len(raw_a)} bars (from {got_a})")
    print(f"    {SYM_B}: {len(raw_b)} bars (from {got_b})")
    if len(raw_a) < 300 or len(raw_b) < 300:
        print("\n  [!] Not enough pre-2021 data to tune reliably for this pair.")
        print("      (A newly-listed coin won't have a real training history.)")
        print("      Falling back to defaults EMA200/ADX14/thr20 — no file written.")
        return

    combos = list(itertools.product(EMA_GRID, ADX_PERIOD_GRID, ADX_THR_GRID))
    print(f"\n  Evaluating {len(combos)} parameter combinations on the train window...\n")

    rows = []
    for i, (ep, ap, th) in enumerate(combos, 1):
        m = backtest(raw_a, raw_b, ep, ap, th, TRAIN_START, TRAIN_END)
        rows.append({"ema": ep, "adx_p": ap, "thr": th, **m})
        print(f"\r    {i}/{len(combos)}  EMA{ep} ADX{ap} thr{th} "
              f"-> sharpe {m['sharpe']:5.2f}  ret {m['ret']:+7.1f}%", end="")
    print()

    res = pd.DataFrame(rows)
    eligible = res[res["trades"] >= MIN_TRADES]
    if eligible.empty:
        print("\n  No combo met the minimum-trades guard — keeping defaults.")
        return
    eligible = eligible.sort_values("sharpe", ascending=False).reset_index(drop=True)

    print("\n  ---- TOP 8 (in-sample / training) ----")
    print("   rank  EMA  ADXp  thr  | sharpe   return    maxDD  trades")
    print("  -------------------------------------------------------------")
    for i, r in eligible.head(8).iterrows():
        print(f"   {i+1:>3}   {int(r.ema):>3}  {int(r.adx_p):>3}  {int(r.thr):>3}  |"
              f" {r.sharpe:5.2f}  {r.ret:+8.1f}%  {r.dd:7.1f}%   {int(r.trades):>4}")

    best = eligible.iloc[0]
    tuned = {
        "ema_period": int(best.ema),
        "adx_period": int(best.adx_p),
        "adx_threshold": float(best.thr),
        "_meta": {
            "tuned_on": f"{TRAIN_START}..{TRAIN_END}",
            "objective": "max_sharpe",
            "train_sharpe": round(float(best.sharpe), 3),
            "train_return_pct": round(float(best.ret), 2),
            "train_max_dd_pct": round(float(best.dd), 2),
            "train_trades": int(best.trades),
            "assets": [SYM_A, SYM_B],
            "note": "Selected on pre-2021 data only. 2021-2026 results are out-of-sample.",
        },
    }
    with open("tuned_params.json", "w") as f:
        json.dump(tuned, f, indent=2)

    print("\n  ---- SELECTED (written to tuned_params.json) ----")
    print(f"    EMA_PERIOD    = {tuned['ema_period']}")
    print(f"    ADX_PERIOD    = {tuned['adx_period']}")
    print(f"    ADX_THRESHOLD = {tuned['adx_threshold']}")
    print("\n  Now run the backtests — they auto-read these via config.py:")
    print("    python 2_backtest_ema200.py")
    print("    python 4_backtest_ema200_adx.py   <- 2021-2026 is now OUT-OF-SAMPLE")
    print("="*64)


if __name__ == "__main__":
    main()