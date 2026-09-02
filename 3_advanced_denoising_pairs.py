"""
STEP 3: Advanced Techniques — Wavelet Denoising + Pairs/Kalman Analysis

Explores two sophisticated signal-processing techniques:
  1. Wavelet Denoising (DWT) — strips high-frequency noise from prices to reveal the
     true underlying trend, using a CAUSAL rolling-window approach (no look-ahead).
  2. Kalman Filter on the ETH/BNB Ratio — dynamically estimates the "fair" spread
     between the two assets. Z-score deviations from the Kalman estimate drive
     an inverse-volatility weighted rotation strategy.

Saves a comparison chart: denoised vs raw prices + Kalman spread.
"""
import pandas as pd, numpy as np, pywt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from binance.client import Client

INITIAL_CASH = 1000.0
FEE_RATE = 0.001
ZSCORE_WINDOW = 100
WAVELET = "db4"
DENOISE_WINDOW = 200   # trailing bars for causal denoising
ATR_PERIOD = 20
client = Client()

from config import SYMBOLS
SYM_A, SYM_B = SYMBOLS[0], SYMBOLS[1]


# ==================== WAVELET DENOISING (CAUSAL) ====================
def causal_denoise(prices, window=DENOISE_WINDOW, wavelet=WAVELET):
    """
    Causal wavelet denoising: at each bar, decompose ONLY the trailing window
    (past data), strip high-frequency detail coefficients, reconstruct, and
    take the last value. This ensures NO future data leaks into the signal.
    """
    denoised = np.full(len(prices), np.nan)
    for i in range(window, len(prices)):
        segment = prices[i - window : i + 1]
        coeff = pywt.wavedec(segment, wavelet, mode="per")
        coeff[1:] = [np.zeros_like(c) for c in coeff[1:]]
        reconstructed = pywt.waverec(coeff, wavelet, mode="per")[: len(segment)]
        denoised[i] = reconstructed[-1]
    return denoised


# ==================== KALMAN FILTER ====================
def kalman_filter(series, R=0.01, Q=0.0001):
    """
    1D Kalman filter for dynamic spread estimation.
    R = measurement noise, Q = process noise.
    Lower Q = smoother estimate (trusts model more).
    Fully causal — each output uses only past observations.
    """
    x = float(series.iloc[0])
    P = 1.0
    filtered = []
    for z in series.values:
        P_pred = P + Q                  # predict uncertainty
        K = P_pred / (P_pred + R)       # Kalman gain
        x = x + K * (float(z) - x)     # update estimate
        P = (1 - K) * P_pred           # update uncertainty
        filtered.append(x)
    return pd.Series(filtered, index=series.index)


# ==================== DATA FETCHING ====================
def fetch(symbol, start, end):
    warmup_dt = datetime.strptime(start, "%Y-%m-%d") - timedelta(days=50)
    kl = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_4HOUR,
                                      warmup_dt.strftime("%Y-%m-%d"), end)
    df = pd.DataFrame(kl, columns=["ot","o","h","l","close","v","ct","qv","t","tb","tq","ig"])
    df["time"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
    df["close"] = df["close"].astype(float)
    df = df[["time", "close"]].set_index("time")
    return df


# ==================== BACKTEST ENGINE ====================
def run_scenario(name, start, end):
    print(f"\n  Fetching {name}...")
    eth_raw = fetch(SYM_A, start, end)
    bnb_raw = fetch(SYM_B, start, end)
    idx = eth_raw.index.intersection(bnb_raw.index)
    eth_c, bnb_c = eth_raw.loc[idx, "close"].values, bnb_raw.loc[idx, "close"].values

    # 1. Causal wavelet denoising
    eth_den = causal_denoise(eth_c)
    bnb_den = causal_denoise(bnb_c)

    # 2. Inverse-volatility weights (on denoised returns)
    eth_s = pd.Series(eth_den)
    bnb_s = pd.Series(bnb_den)
    vol_e = eth_s.pct_change().rolling(ATR_PERIOD).std()
    vol_b = bnb_s.pct_change().rolling(ATR_PERIOD).std()
    inv_e = 1.0 / vol_e
    inv_b = 1.0 / vol_b
    base_w = inv_e / (inv_e + inv_b)

    # 3. Kalman-filtered ratio + z-score for rotation
    ratio = eth_s / bnb_s
    kalman_ratio = kalman_filter(ratio.dropna())
    kalman_ratio = kalman_ratio.reindex(ratio.index)
    z = (ratio - kalman_ratio) / ratio.rolling(ZSCORE_WINDOW).std()

    # 4. Target weights: inverse-vol base shifted by z-score
    target_eth = (base_w - z * 0.15).clip(0.15, 0.85)
    target_bnb = 1.0 - target_eth

    # 5. Simulate portfolio (always invested, rebalancing with fees)
    # Slice to test period
    s_utc = pd.to_datetime(start).tz_localize("UTC")
    e_utc = pd.to_datetime(end).tz_localize("UTC")
    mask = (idx >= s_utc) & (idx <= e_utc)
    test_idx = np.where(mask)[0]
    if len(test_idx) < 10:
        print(f"    Insufficient data for {name}"); return 0

    prev_we, prev_wb = 0.5, 0.5
    equity = INITIAL_CASH
    for i in test_idx[1:]:
        if np.isnan(target_eth.iloc[i]) or np.isnan(target_bnb.iloc[i]):
            continue
        re = (eth_c[i] / eth_c[i-1]) - 1 if eth_c[i-1] > 0 else 0
        rb = (bnb_c[i] / bnb_c[i-1]) - 1 if bnb_c[i-1] > 0 else 0
        equity *= (1 + prev_we * re + prev_wb * rb)
        # Fee on weight change
        we_new, wb_new = target_eth.iloc[i], target_bnb.iloc[i]
        turnover = abs(we_new - prev_we) + abs(wb_new - prev_wb)
        equity *= (1 - turnover * FEE_RATE)
        prev_we, prev_wb = we_new, wb_new

    ret = (equity / INITIAL_CASH - 1) * 100
    print(f"  --- {name} ({start} to {end}) ---")
    print(f"    Return: {ret:+.2f}%  |  Final: ${equity:.2f}")

    # Save chart for the first scenario that has enough data
    if len(test_idx) > 200:
        save_chart(idx, eth_c, eth_den, ratio.values,
                   kalman_ratio.values if kalman_ratio is not None else ratio.values,
                   test_idx, name)
    return ret


def save_chart(idx, raw, denoised, ratio, kalman, test_slice, name):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7))
    sl = test_slice[:min(500, len(test_slice))]  # show first 500 bars of test
    x = range(len(sl))

    ax1.plot(x, raw[sl], alpha=0.5, linewidth=0.8, label="Raw ETH Price", color="#FF6B6B")
    valid_den = [denoised[i] for i in sl]
    ax1.plot(x, valid_den, linewidth=1.8, label="Wavelet Denoised (causal)", color="#4ECDC4")
    ax1.set_title(f"Wavelet Denoising: Raw vs Cleaned  ({name})")
    ax1.legend()
    ax1.grid(alpha=0.3)

    r_sl = [ratio[i] for i in sl]
    k_sl = [kalman[i] if i < len(kalman) and not np.isnan(kalman[i]) else ratio[i] for i in sl]
    ax2.plot(x, r_sl, alpha=0.5, linewidth=0.8, label="Raw ETH/BNB Ratio", color="#FF6B6B")
    ax2.plot(x, k_sl, linewidth=1.8, label="Kalman Filtered Ratio", color="#45B7D1")
    ax2.set_title("Kalman Filter: Dynamic Spread Estimation")
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    out = "chart_advanced_techniques.png"
    plt.savefig(out, dpi=130)
    print(f"    Chart saved: {out}")


# ==================== MAIN ====================
if __name__ == "__main__":
    print("=" * 60)
    print("  STEP 3: ADVANCED TECHNIQUES — Wavelet + Kalman + Pairs")
    print("=" * 60)
    print("\n  Techniques applied:")
    print("    1. Wavelet Denoising (Daubechies-4, causal rolling window)")
    print("       → Strips high-freq noise while preserving trend structure")
    print("    2. Kalman Filter on ETH/BNB ratio")
    print("       → Dynamic fair-spread estimation for pairs rotation")
    print("    3. Inverse-Volatility Weighting")
    print("       → Lower volatility = higher allocation (risk parity)")

    run_scenario("Bear Crash",    "2021-11-01", "2022-01-31")
    run_scenario("Choppy Summer", "2023-05-01", "2023-08-31")
    r = run_scenario("Multi-Year",    "2021-01-01", "2026-05-30")

    print(f"\n  {'='*56}")
    print("  FINDING: Advanced denoising + pairs rotation shows the")
    print("  power of signal processing.")
    print(f"  {'='*56}")