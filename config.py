"""
config.py — central configuration for the algo-trading pipeline.

Reads TWO machine-written files (both optional, with safe fallbacks):

  1. selected_assets.json  ← written by 0_screen_volatility.py
     Exposes:  MORE_VOLATILE, LESS_VOLATILE, SYMBOLS, SYM_A, SYM_B

  2. tuned_params.json      ← written by tune_parameters.py
     Exposes:  EMA_PERIOD, ADX_PERIOD, ADX_THRESHOLD

Every backtester and the live trader import from here, so:
  - changing the screened pair changes ALL downstream files automatically
  - the parameters used in the 2021-2026 test are exactly the ones tuned
    on the pre-2021 training window (no manual re-typing = no leakage by hand)
"""
import json, os

_DIR = os.path.dirname(__file__)
_ASSETS_PATH = os.path.join(_DIR, "selected_assets.json")
_PARAMS_PATH = os.path.join(_DIR, "tuned_params.json")

_ASSET_DEFAULTS = {"more_volatile": "ETHUSDT", "less_volatile": "BNBUSDT"}
_PARAM_DEFAULTS = {"ema_period": 200, "adx_period": 14, "adx_threshold": 20.0}


def _load(path, defaults):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return {**defaults, **json.load(f)}
        except Exception as e:
            print(f"  [config] could not read {os.path.basename(path)} ({e}) — using defaults")
            return dict(defaults)
    print(f"  [config] {os.path.basename(path)} not found — using defaults: {defaults}")
    return dict(defaults)


# ---- assets ----
_assets = _load(_ASSETS_PATH, _ASSET_DEFAULTS)
MORE_VOLATILE = _assets["more_volatile"]
LESS_VOLATILE = _assets["less_volatile"]
SYMBOLS = [MORE_VOLATILE, LESS_VOLATILE]
SYM_A, SYM_B = SYMBOLS[0], SYMBOLS[1]

# ---- tuned strategy parameters ----
_params = _load(_PARAMS_PATH, _PARAM_DEFAULTS)
EMA_PERIOD = int(_params["ema_period"])
ADX_PERIOD = int(_params["adx_period"])
ADX_THRESHOLD = float(_params["adx_threshold"])

PARAMS_ARE_TUNED = os.path.exists(_PARAMS_PATH)









# """
# config.py — reads the assets selected by 0_screen_volatility.py.
# All backtester and strategy files import from here instead of hardcoding symbols.

# If selected_assets.json doesn't exist yet, falls back to defaults (ETH/BNB).
# """
# import json, os

# _PATH = os.path.join(os.path.dirname(__file__), "selected_assets.json")
# _DEFAULTS = {"more_volatile": "ETHUSDT", "less_volatile": "BNBUSDT"}

# def _load():
#     if os.path.exists(_PATH):
#         with open(_PATH) as f:
#             return json.load(f)
#     print(f"  [config] selected_assets.json not found — using defaults: {_DEFAULTS}")
#     return _DEFAULTS

# assets = _load()
# MORE_VOLATILE = assets["more_volatile"]
# LESS_VOLATILE = assets["less_volatile"]
# SYMBOLS = [MORE_VOLATILE, LESS_VOLATILE]