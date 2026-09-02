"""
STEP 0: Asset Selection via Volatility Screening
Screens 20 crypto assets on Binance, ranks by annualized volatility,
and SAVES the selected pair to selected_assets.json.
All downstream files (backtester, strategy) read from that file automatically.
"""
import json, numpy as np, pandas as pd
from binance.client import Client

client = Client()
SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","LTCUSDT","TRXUSDT",
    "SOLUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","NEARUSDT",
    "APTUSDT","ARBUSDT","DOGEUSDT","SHIBUSDT","PEPEUSDT","WIFUSDT",
    "FLOKIUSDT","BONKUSDT",
]

def screen():
    rows = []
    for sym in SYMBOLS:
        try:
            kl = client.get_historical_klines(sym, Client.KLINE_INTERVAL_1DAY, "90 days ago UTC")
            if not kl or len(kl) < 30: continue
            closes = pd.Series([float(k[4]) for k in kl])
            qv = pd.Series([float(k[7]) for k in kl])
            log_ret = np.log(closes / closes.shift(1)).dropna()
            rows.append((sym, log_ret.std() * np.sqrt(365), qv.mean()))
        except: pass
    df = pd.DataFrame(rows, columns=["Symbol","AnnVol","AvgDailyVol"]).sort_values("AnnVol")
    liquid = df[df["AvgDailyVol"] > 50_000_000].reset_index(drop=True)

    less_vol = liquid.iloc[0]["Symbol"]
    more_vol = liquid.iloc[-1]["Symbol"]

    print("="*60)
    print("  STEP 0: VOLATILITY SCREENING — 20 Binance Assets")
    print("="*60)
    for _, r in liquid.iterrows():
        bar = "█" * int(r["AnnVol"] * 30)
        print(f"  {r['Symbol']:10s} vol={r['AnnVol']:5.1%}  ${r['AvgDailyVol']/1e6:>6.0f}M  {bar}")
    print(f"\n  SELECTED: Less Volatile = {less_vol}")
    print(f"            More Volatile = {more_vol}")

    # Save to JSON — all other files read this automatically
    result = {"less_volatile": less_vol, "more_volatile": more_vol}
    with open("selected_assets.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Saved to selected_assets.json — all backtests will use these assets.")
    print("="*60)

if __name__ == "__main__":
    screen()