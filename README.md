# Multi-Strategy Systematic Crypto Trading Framework
### Walk-Forward Validated Momentum & Statistical Arbitrage on Binance

A from-scratch systematic trading research pipeline: asset selection → four
progressively more sophisticated strategies → walk-forward parameter tuning
→ formal bias audit → live execution against Binance's Testnet API.

---

## 1. Universe Selection

`0_screen_volatility.py` screens ~20 liquid USDT pairs on Binance, filters
for average daily quote volume > $50M, and ranks the survivors by
annualized realized volatility (90-day log-return std, annualized).

The **least volatile** and **most volatile** eligible pairs are selected as
a two-asset trading universe and frozen for the rest of the pipeline
(written to `selected_assets.json`, consumed by every downstream script via
`config.py`). This universe is fixed *before* any backtest runs — no asset
is added or removed based on how it performed later, which rules out
survivorship bias by construction.

Example screening run selected **BTCUSDT** (least volatile) and **NEARUSDT**
(most volatile) from a pool including ETH, BNB, XRP, SOL.

## 2. Strategy Progression

Each strategy was built specifically to fix a weakness exposed by the one
before it.

### Strategy 1 — Naive EMA20/50 Crossover (baseline)
Classic fast-moving-average crossover on 4H candles. Included to
**quantify** the beginner mistake of over-trading: it racked up 303 trades
and $423 in fees over the multi-year test, with an 82.9% max drawdown.
This became the empirical case for a slower filter.

### Strategy 2 — Single EMA Trend Filter
Removed the fast/slow crossover in favor of one EMA: hold an asset only
while price is above it, otherwise sit in cash. Fewer trades, but still no
notion of trend *strength* — it happily entered weak, choppy trends
(-20% in the Choppy Summer window) since direction alone was the only
signal.

### Strategy 3 — Wavelet-Denoised Kalman Pairs (mean-reversion overlay)
A signal-processing-heavy approach on the same two-asset universe:
1. **Causal wavelet denoising** (Daubechies-4, rolling window, no
   look-ahead) strips high-frequency noise from both price series while
   preserving trend structure.
2. **Inverse-volatility weighting** sets a risk-parity base allocation
   between the two assets.
3. A **Kalman filter** tracks the dynamic "fair" price ratio between the
   pair.
4. The **z-score** of the actual ratio vs. the Kalman estimate tilts the
   allocation away from the base weight — buying more of the
   relatively-cheap asset, less of the relatively-expensive one.
5. Weights are clipped to 15%–85% — the strategy is **always invested**,
   unlike the trend-following strategies.

### Strategy 4 — EMA + ADX Momentum Filter (final / selected)
Adds ADX (Average Directional Index) as a trend-*strength* confirmation on
top of the EMA direction filter from Strategy 2. Only enters when price is
above its EMA **and** ADX exceeds a threshold; when both assets qualify,
rotates into whichever has the higher ADX reading.

## 3. Eliminating Data Leakage — Walk-Forward Parameter Tuning

The EMA period, ADX period, and ADX threshold for Strategy 4 were **not**
hand-picked. `tune_parameters.py` grid-searches all three on a **training
window of 2017-09 → 2020-12** (the earliest data Binance has, through the
end of 2020), scoring each combination by Sharpe ratio with a
minimum-trade-count guard to reject high-Sharpe/low-sample-size flukes.

The selected parameters are written to `tuned_params.json` and consumed
automatically by every backtest and the live trader via `config.py` — so
the same numbers used to report the 2021–2026 result are exactly the ones
chosen without that period ever being seen. All 2021–2026 figures below
are genuine **out-of-sample** results.

## 4. Formal Bias Audit

Before finalizing, the strategy was written up against three standard
backtesting failure modes:

| Bias | Assessment |
|---|---|
| Look-ahead bias | Not detected — all indicators are causal, recursive functions of past prices only (`EMA_t = f(P_1...P_t)`) |
| Survivorship bias | Not detected — trading universe fixed *a priori*, no asset substitution based on outcome |
| Data snooping / overfitting | Low risk **once walk-forward tuning is applied** — parameters selected on train data only, single configuration evaluated once on test data |

*(Full write-up in `docs/bias_explanation.pdf`)*

## 5. Live Execution

`strategy_live.py` runs the exact Strategy 4 signal logic against Binance's
**Testnet/Demo API** — same EMA/ADX code path as the backtest, same tuned
parameters via `config.py` — placing real (simulated-funds) market orders
and rebalancing hourly. Two additional live traders
(`ema_live.py`, `2_strategy_live.py`) demonstrate Strategies 2 and 3 live,
letting each strategy's distinct behavior be observed directly: the
EMA+ADX strategy will correctly sit in cash when there's no strong trend,
while the always-invested pairs strategy trades on every run.

---

## Results Summary

All figures below are from the tuned pipeline on **BTCUSDT / NEARUSDT**,
Strategy 4 parameters: EMA100, ADX period 10, ADX threshold 20
(selected via walk-forward tuning on 2017–2020 data).

| Strategy | Bear Mkt (Nov'21–Jan'22) | Choppy (May–Aug'23) | Multi-Year (2021–2026) | Max DD (Multi-Yr) |
|---|---|---|---|---|
| 1. Naive EMA20/50 | −25.2% | −15.4% | +10.9% | −82.9% |
| 2. EMA-only (tuned period) | +14.3% | −20.1% | −8.2% | −78.6% |
| 3. Wavelet+Kalman pairs | −30.5% | −18.5% | **+134.9%** | — |
| 4. EMA+ADX (final, tuned, OOS) | +16.2% | −18.1% | **+38.9%** (~6% CAGR) | −76.7% |

**In-sample vs. out-of-sample (Strategy 4):** training-window return was
+115.0%; out-of-sample multi-year return was +38.9%. The gap between these
two numbers is the headline finding — it is direct, quantified evidence of
how much naive backtesting overstates real performance, and the reason the
walk-forward split exists.

*Note: Strategy 3 produced the highest raw multi-year return but was not
subjected to the same walk-forward parameter search as Strategy 4 — its
window sizes (wavelet=200 bars, z-score=100 bars) were fixed by design
rather than tuned, so it is reported for completeness rather than selected
as the "winning" strategy.*

---

## Tech Stack
Python · pandas / numpy · python-binance · PyWavelets (DWT) · custom Kalman
filter implementation · Binance REST API (historical + Testnet live
trading) · matplotlib

## Repository Structure
```
0_screen_volatility.py       # universe selection
tune_parameters.py           # walk-forward parameter search (train: 2017-2020)
config.py                    # shared config — reads screener + tuner outputs
1_backtest_naive_ema.py      # Strategy 1
2_backtest_ema200.py         # Strategy 2
3_advanced_denoising_pairs.py# Strategy 3 (wavelet + Kalman + z-score)
4_backtest_ema200_adx.py     # Strategy 4 (final, OOS-reported)
returns.py                   # final summary report (CAGR, win rate, etc.)
strategy_live.py             # Strategy 4 live on Binance Testnet
ema_live.py                  # Strategy 2 live on Binance Testnet
2_strategy_live.py           # Strategy 3 live on Binance Testnet
docs/bias_explanation.pdf    # formal look-ahead / survivorship / snooping audit
```
