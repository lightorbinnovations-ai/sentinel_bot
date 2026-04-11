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

# ═════════════════════════════════════════════════════════════════════════════
#                         ENVIRONMENT & CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

API_TOKEN        = os.getenv("DERIV_TOKEN")
GH_TOKEN         = os.getenv("GH_TOKEN")
REPO_NAME        = os.getenv("GITHUB_REPOSITORY")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Trading Parameters (Defaults + Env Overrides)
INITIAL_STAKE    = float(os.getenv("INITIAL_STAKE", "1.50"))
STOP_LOSS_LIMIT  = float(os.getenv("STOP_LOSS", "2.00"))
TAKE_PROFIT      = float(os.getenv("TAKE_PROFIT", "10.00"))
MAX_STAKE_CAP    = float(os.getenv("MAX_STAKE", "15.00"))
GHOST_THRESHOLD  = int(os.getenv("GHOST_THRESHOLD", "3"))

WS_URL           = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
SYMBOL           = "R_100"
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
        
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_trend_strength(prices):
    """Proxy for ADX/Trend strength in ticks."""
    period = 14
    if len(prices) < period + 1: return 0
    data = list(prices)[-(period+1):]
    up_moves = sum(1 for i in range(1, len(data)) if data[i] > data[i-1])
    total = len(data) - 1
    return abs(up_moves - (total / 2)) / (total / 2) * 100

# ═════════════════════════════════════════════════════════════════════════════
#                             COMMAND & CONTROL
# ═════════════════════════════════════════════════════════════════════════════

class SentinelControl:
    def __init__(self, initial_sl, initial_stake):
        self.stop_loss = initial_sl
        self.stake = initial_stake
        self.last_update_id = 0

    async def sync_to_github(self, var_name, value):
        if not GH_TOKEN or not REPO_NAME: 
            log.warning(f"⚠️ Persistence disabled: GH_TOKEN or REPO_NAME missing.")
            return
        url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
        headers = {"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        data = {"name": var_name, "value": str(value)}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=headers, json=data) as resp:
                    if resp.status == 204: 
                        log.info(f"📤 GitHub Sync: {var_name} -> {value}")
                    else:
                        log.error(f"❌ GitHub Sync Failed ({resp.status}): {await resp.text()}")
        except Exception as e:
            log.error(f"❌ Sync Error: {e}")

    async def poll_commands(self, state):
        if not TELEGRAM_TOKEN: return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 1}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        msg = update.get("message", {}).get("text", "")
                        if not msg: continue
                        
                        args = msg.split()
                        cmd = args[0].lower()
                        
                        if cmd == "/status" or cmd == "/start":
                            await send_tele_message(f"📊 *Sentinel Status*\nStake: ${self.stake}\nSL: ${self.stop_loss}\nPnL: ${state.total_pnl}\nGhost: {state.ghost_losses}/{GHOST_THRESHOLD}")
                        elif cmd == "/stoploss" and len(args) > 1:
                            self.stop_loss = float(args[1])
                            await self.sync_to_github("STOP_LOSS", self.stop_loss)
                            await send_tele_message(f"🛡️ SL updated: ${self.stop_loss}")
                        elif cmd == "/stake" and len(args) > 1:
                            self.stake = float(args[1])
                            await self.sync_to_github("INITIAL_STAKE", self.stake)
                            await send_tele_message(f"💰 Stake updated: ${self.stake}")
        except: pass

async def send_tele_message(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🌌 *The Void Sentinel*\n{msg}", "parse_mode": "Markdown"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                pass
    except: pass

# ═════════════════════════════════════════════════════════════════════════════
#                             SESSION STATE
# ═════════════════════════════════════════════════════════════════════════════

class SentinelState:
    def __init__(self, start_balance):
        self.start_balance = start_balance
        self.current_balance = start_balance
        self.stake = INITIAL_STAKE
        self.first_win_achieved = False
        self.last_trade_time = 0
        self.ghost_losses = 0
        self.current_direction = "CALL"

    @property
    def total_pnl(self):
        return round(self.current_balance - self.start_balance, 2)

    def get_signal(self, current_price, sma, rsi, trend):
        if time.time() - self.last_trade_time < COOLDOWN_SECS: return None
        if sma is None or rsi is None: return None
        
        # Trend Filter (initiative added)
        if trend < ADX_THRESHOLD: return None
        
        if current_price > sma and rsi > RSI_OB: return "CALL"
        if current_price < sma and rsi < RSI_OS: return "PUT"
        return None

    def update_balance(self, balance):
        self.current_balance = float(balance)

    def process_result(self, is_win, profit_amount=0):
        if is_win:
            self.stake = INITIAL_STAKE
            self.first_win_achieved = True
            self.ghost_losses = 0
        else:
            self.stake = min(round(self.stake * MARTINGALE_MULT, 2), MAX_STAKE_CAP)
            self.current_direction = "PUT" if self.current_direction == "CALL" else "CALL"

# ═════════════════════════════════════════════════════════════════════════════
#                             MAIN EXECUTION
# ═════════════════════════════════════════════════════════════════════════════

async def run_sentinel():
    if not API_TOKEN:
        log.error("❌ DERIV_TOKEN not found! Emergency shutdown.")
        return

    log.info("🌌 THE VOID SENTINEL v3.0 initializing...")
    if not GH_TOKEN:
        log.warning("⚠️ Persistence token (GH_TOKEN) missing. Variables will not be saved.")
    
    api = DerivAPI(endpoint=WS_URL)
    
    try:
        auth_resp = await api.authorize({"authorize": API_TOKEN})
        start_bal = float(auth_resp['authorize']['balance'])
        log.info(f"📡 Connection Established. Balance: ${start_bal:.2f}")
        await send_tele_message(f"🚀 Sentinel Online. Balance: ${start_bal:.2f}\nTarget: +${TAKE_PROFIT}")
    except Exception as e:
        log.error(f"❌ Auth failure: {e}")
        return

    state = SentinelState(start_bal)
    ctrl = SentinelControl(STOP_LOSS_LIMIT, INITIAL_STAKE)
    prices = deque(maxlen=100)
    
    log.info("📥 Warming up engines (Syncing history)...")
    try:
        history = await api.ticks_history({"ticks_history": SYMBOL, "count": 100, "end": "latest", "style": "ticks"})
        if 'error' in history:
            log.error(f"❌ Warm-up Error: {history['error'].get('message', 'Unknown error')}")
            return
        prices.extend([float(p) for p in history['history']['prices']])
    except Exception as e:
        log.error(f"❌ Warm-up Critical Failure: {e}")
        return

    while True:
        try:
            await ctrl.poll_commands(state)
            current_sl = ctrl.stop_loss
            
            # Re-auth for balance check (Deriv subscription is better but this is fine for polling)
            account_info = await api.authorize({"authorize": API_TOKEN})
            state.update_balance(account_info['authorize']['balance'])

            # Security Guards
            if state.total_pnl <= -current_sl:
                msg = f"🛑 HARD STOP ACTIVATED. PnL: ${state.total_pnl:.2f}. Shutting down."
                log.critical(msg); await send_tele_message(msg); break
            
            if state.total_pnl >= TAKE_PROFIT:
                msg = f"🎯 TAKE PROFIT REACHED! PnL: ${state.total_pnl:.2f}. Mission accomplished."
                log.info(msg); await send_tele_message(msg); break

            if state.first_win_achieved and state.total_pnl <= 0:
                msg = "📉 Profit Lock: Outlay secured. Profit depleted. Terminating."
                log.warning(msg); await send_tele_message(msg); break

            # Tick Monitoring
            tick_data = await api.ticks_history({"ticks_history": SYMBOL, "count": 1, "end": "latest", "style": "ticks"})
            current_price = float(tick_data['history']['prices'][0])
            prices.append(current_price)

            sma = calculate_sma(prices, SMA_PERIOD)
            rsi = calculate_rsi(prices, RSI_PERIOD)
            trend = calculate_trend_strength(prices)
            
            signal = state.get_signal(current_price, sma, rsi, trend)

            if not signal:
                await asyncio.sleep(2); continue

            # Direction is determined by strategy (flip on loss), timing by signal
            trade_direction = state.current_direction

            # GHOST ENGINE (inititive: uses real tick comparison)
            if state.ghost_losses < GHOST_THRESHOLD:
                log.info(f"👻 Ghosting {trade_direction} | Filter: RSI={rsi:.1f} ADX={trend:.1f} | Losses: {state.ghost_losses}/{GHOST_THRESHOLD}")
                await asyncio.sleep(1) # Wait for tick resolution
                next_tick = await api.ticks_history({"ticks_history": SYMBOL, "count": 1, "end": "latest", "style": "ticks"})
                price_after = float(next_tick['history']['prices'][0])
                
                is_virtual_win = (trade_direction == "CALL" and price_after > current_price) or \
                                 (trade_direction == "PUT" and price_after < current_price)
                
                if not is_virtual_win and price_after != current_price: # Ignore ties
                    state.ghost_losses += 1
                    state.current_direction = "PUT" if state.current_direction == "CALL" else "CALL"
                    log.info(f"📉 Virtual Loss. Target flipped to {state.current_direction}")
                elif is_virtual_win:
                    state.ghost_losses = 0
                    log.info(f"✅ Virtual Win. Ghost chain reset.")
                
                state.last_trade_time = time.time()
                continue

            # REAL STRIKE
            trade_stake = ctrl.stake if state.stake == INITIAL_STAKE else state.stake
            
            # Profit Protection Stake Scaling
            if state.first_win_achieved:
                trade_stake = min(trade_stake, state.total_pnl)
                if trade_stake < 0.35:
                    log.warning("📉 Profit insufficient for minimum stake. Halting."); break

            log.info(f"⚡ STRIKING: {trade_direction} | Stake: ${trade_stake:.2f} | PnL: ${state.total_pnl:.2f}")
            
            try:
                proposal = await api.proposal({
                    "proposal": 1, "amount": trade_stake, "basis": "stake",
                    "contract_type": trade_direction, "currency": "USD", "duration": DURATION, 
                    "duration_unit": DURATION_UNIT, "symbol": SYMBOL
                })
                buy = await api.buy({"buy": proposal['proposal']['id'], "price": trade_stake})
                contract_id = buy['buy']['contract_id']
                
                log.info(f"🎯 Contract {contract_id} live. Awaiting settlement...")
                
                # Check result
                settled = False
                for _ in range(10): # Max 20s wait
                    await asyncio.sleep(2)
                    pt = await api.profit_table({"profit_table": 1, "limit": 1})
                    tx = pt['profit_table']['transactions'][0]
                    if tx['contract_id'] == contract_id:
                        profit = float(tx['sell_price']) - float(tx['buy_price'])
                        is_real_win = profit > 0
                        
                        emoji = "✅" if is_real_win else "❌"
                        res_str = "WIN" if is_real_win else "LOSS"
                        log.info(f"{emoji} REAL {res_str} (${profit:+.2f}) | PnL: ${state.total_pnl + profit:.2f}")
                        await send_tele_message(f"{emoji} REAL {res_str}: ${profit:+.2f}\nTotal PnL: ${state.total_pnl + profit:.2f}")

                        state.process_result(is_real_win, profit)
                        state.last_trade_time = time.time()
                        settled = True
                        break
                
                if not settled:
                    log.warning("⚠️ Settlement timeout. Moving to next tick.")
                    
            except Exception as e:
                log.error(f"⚠️ Trade anomaly: {e}")
                await asyncio.sleep(10)

        except Exception as e:
            log.error(f"🔄 Stream error: {e}")
            await asyncio.sleep(5)

    await api.disconnect()
    log.info("🌌 The Void Sentinel enters standby.")

if __name__ == "__main__":
    try:
        asyncio.run(run_sentinel())
    except KeyboardInterrupt:
        pass
