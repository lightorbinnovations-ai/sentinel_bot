"""
╔══════════════════════════════════════════════════════════════════╗
║                   THE VOID SENTINEL (v3.0)                       ║
║           Advanced Algorithmic Trading Bot for Deriv             ║
╚══════════════════════════════════════════════════════════════════╝

Architecture: Asynchronous, Ghost-First, Trend-Focused.
Consolidated Excellence: Merging Sentinel Control + Smart Indicators.
"""

import asyncio
import os
import sys
import time
import logging
import aiohttp
from collections import deque
from datetime import datetime

# ── Dependencies ───────────────────────────────────────────────────────────────
try:
    from deriv_api import DerivAPI
except ImportError:
    print("ERROR: deriv_api not installed. Run: pip install python-deriv-api")
    sys.exit(1)

# ── Logging Setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("VoidSentinel")

# ── Global Configuration ──────────────────────────────────────────────────────
# Pulling core identities
API_TOKEN        = os.getenv("DERIV_TOKEN")
GH_TOKEN          = os.getenv("GH_TOKEN")
REPO_NAME        = os.getenv("GITHUB_REPOSITORY")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Trading Parameters (Defaults + Env Overrides)
INITIAL_STAKE    = float(os.getenv("INITIAL_STAKE", "1.50"))
STOP_LOSS_LIMIT  = float(os.getenv("STOP_LOSS", "2.00"))
TAKE_PROFIT      = float(os.getenv("TAKE_PROFIT", "10.00"))
MAX_STAKE_CAP    = float(os.getenv("MAX_STAKE", "15.00"))
GHOST_THRESHOLD  = int(os.getenv("GHOST_THRESHOLD", "3"))

# ── Pre-Flight Verification ───────────────────────────────────────────────────
def check_env():
    required = ["DERIV_TOKEN", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        log.critical(f"❌ MISSING SECRETS: {', '.join(missing)}")
        log.critical("Ensure these are added to GitHub Secrets (NOT Variables).")
        sys.exit(1)
    
    # Check variables (optional but good to know)
    if not os.getenv("GH_TOKEN"):
        log.warning("⚠️ GH_TOKEN not found. Persistence is disabled.")

APP_ID           = 1089
# Direct Endpoints (un-parameterized)
BASE_ENDPOINTS = [
    "wss://ws.derivws.com/websockets/v3",
    "wss://ws.binaryws.com/websockets/v3",
    "wss://green.binaryws.com/websockets/v3"
]
# Stealth Headers (making the connection look like a real browser)
STEALTH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Origin": "https://tradingview.binary.com",
    "Host": "ws.binaryws.com"
}
DURATION         = 1
DURATION_UNIT    = "t"
MARTINGALE_MULT  = 1.071

# Indicators
SMA_PERIOD       = 50
RSI_PERIOD       = 14
RSI_OB           = 70
RSI_OS           = 30
ADX_THRESHOLD    = 25
COOLDOWN_SECS    = 120

# ═════════════════════════════════════════════════════════════════════════════
#                             INDICATOR ENGINE
# ═════════════════════════════════════════════════════════════════════════════

def calculate_sma(prices, period):
    if len(prices) < period: return None
    return sum(list(prices)[-period:]) / period

def calculate_rsi(prices, period):
    """Wilder's Smoothing RSI."""
    if len(prices) < period + 1: return None
    data = list(prices)
    deltas = [data[i] - data[i-1] for i in range(1, len(data))]
    
    gains = [max(d, 0) for d in deltas[:period]]
    losses = [max(-d, 0) for d in deltas[:period]]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + max(deltas[i], 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-deltas[i], 0)) / period
        
    if avg_loss == 0:  # Prevent division by zero
        return 100 if avg_gain == 0 else 0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# Additional function to validate API token and connection
async def validate_connection(api_token):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_ENDPOINTS[0]}/ping", headers={"Authorization": f"Bearer {api_token}"}) as response:
                if response.status != 200:
                    log.critical("❌ Invalid API token or connection issue.")
                    sys.exit(1)
        except Exception as e:
            log.critical(f"❌ Connection error: {e}")
            sys.exit(1)

# Call the validation function at the start
asyncio.run(validate_connection(API_TOKEN))
<<<<< END sentinel.py <<<<<

===FILE: void_sentinel_legacy.py===
"""
╔══════════════════════════════════════════════════════════════════╗
║           The Void Sentinel (Legacy) — Smart Algorithmic Trading Bot           ║
║          Built for Deriv API (python-deriv-api) + GitHub Actions ║
╚══════════════════════════════════════════════════════════════════╝

Strategy (translated from the original XML bot + smart enhancements):
  • Market       : Volatility 100 Index (R_100) — Synthetic Indices
  • Contract     : Rise / Fall (CALL / PUT) — Call/Put category
  • Duration     : 1 tick  (fast, synthetic ticks)
  • Initial Stake: $1.50
  • Martingale   : ×1.071 on consecutive losses (from original XML)
  • Win Reset    : Stake resets to $1.50 on win; initial $1.50 stays locked
                   after first win (only accumulated profit is risked)
  • GHOST MODE   : Simulated trades run first; real order placed only after
                   3 consecutive VIRTUAL losses
  • Hard Stop    : Total real loss >= $2.00  →  immediate termination
  • Profit Target: $9.70 total profit  →  graceful stop
  • Entry Filters: 50-SMA (price vs SMA) + RSI-14 (<30 or >70)
  • Cooldown     : 2 minutes between real trade attempts
  • Direction    : CALL if price > SMA AND RSI > 70
                   PUT  if price < SMA AND RSI < 30
"""

import asyncio
import os
import sys
import time
import logging
import random
from collections import deque
from datetime import datetime

# ── Third-party ──────────────────────────────────────────────────────────────
try:
    from deriv_api import DerivAPI
except ImportError:
    print("ERROR: deriv_api not installed. Run: pip install python-deriv-api")
    sys.exit(1)

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("VoidSentinelLegacy")

# ═════════════════════════════════════════════════════════════════════════════
#                         CONFIGURATION CONSTANTS
# ═════════════════════════════════════════════════════════════════════════════

# API
WS_URL          = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
API_TOKEN       = os.getenv("DERIV_TOKEN")          # pulled from GitHub Secret

# Market
SYMBOL          = "R_100"                           # Volatility 100 Index
DURATION        = 1                                 # 1 tick duration
DURATION_UNIT   = "t"                               # ticks

# Money
INITIAL_STAKE   = 1.50                              # $1.50 (from XML)
MARTINGALE_MULT = 1.071                             # ×1.071 on loss (from XML)
HARD_STOP_LOSS  = 2.00                              # $2.00 total loss → terminate
PROFIT_TARGET   = 9.70                              # $9.70 target (from XML)
WIN_RESET_TO    = 1.50                              # reset stake on win (from XML)

# Ghost / Smart Mode
GHOST_LOSSES_BEFORE_REAL = 3                        # real trade after 3 virtual losses

# Risk Management Armor
MAX_MARTINGALE_STEPS = 5                            # Reset stake after 5 losses (Protection)
MAX_STAKE_CEILING    = 15.00                        # Hard cap on any single trade stake

# Filters
SMA_PERIOD      = 50                                # 50-period SMA
RSI_PERIOD      = 14                                # RSI-14
RSI_OVERBOUGHT  = 70
RSI_OVERSOLD    = 30
ADX_PERIOD      = 14                                # ADX for trend strength
ADX_THRESHOLD   = 25                                # Only trade if trend is strong

# Notifications
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Timing
COOLDOWN_SECS   = 120                               # 2-minute cooldown between real trades
TICK_BUFFER_SIZE = max(SMA_PERIOD + 1, RSI_PERIOD + 20, ADX_PERIOD * 2 + 1)

# Additional function to validate API token and connection
async def validate_connection(api_token):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{WS_URL}/ping", headers={"Authorization": f"Bearer {api_token}"}) as response:
                if response.status != 200:
                    log.critical("❌ Invalid API token or connection issue.")
                    sys.exit(1)
        except Exception as e:
            log.critical(f"❌ Connection error: {e}")
            sys.exit(1)

# Call the validation function at the start
asyncio.run(validate_connection(API_TOKEN))
<<<<< END void_sentinel_legacy.py <<<<<