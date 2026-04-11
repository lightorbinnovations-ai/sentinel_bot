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


# ═════════════════════════════════════════════════════════════════════════════
#                         TECHNICAL INDICATOR HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def calculate_sma(prices: list[float], period: int) -> float | None:
    """Simple Moving Average over the last `period` prices."""
    if len(prices) < period:
        return None
    window = prices[-period:]
    return sum(window) / period


async def send_telegram(message: str):
    """Sends a notification to Telegram if configured."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import aiohttp
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🤖 *The Void Sentinel (Legacy)*\n{message}",
        "parse_mode": "Markdown"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    log.warning(f"Telegram failed: {await resp.text()}")
    except Exception as e:
        log.warning(f"Telegram error: {e}")


def calculate_rsi(prices: list[float], period: int) -> float | None:
    """
    RSI using Wilder's smoothing (Standard Deriv/TradingView method).
    """
    if len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    
    # First Average Gain/Loss
    gains = [max(d, 0) for d in deltas[:period]]
    losses = [max(-d, 0) for d in deltas[:period]]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    # Subsequent Smoothed Averages
    for i in range(period, len(deltas)):
        d = deltas[i]
        gain = max(d, 0)
        loss = max(-d, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_adx(prices: list[float], period: int = ADX_PERIOD) -> float | None:
    """
    Simple Trend Strength Filter. 
    (Returns ADX values — generally > 25 means a strong trend).
    """
    if len(prices) < (period * 2 + 1):
        return None
    # Simplified Trend Strength: ratio of range to standard deviation
    # In a tick environment, we look for persistent direction
    up_moves = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i-1])
    total_moves = len(prices) - 1
    strength = abs(up_moves - (total_moves / 2)) / (total_moves / 2) * 100
    return strength


def get_trade_direction(
    prices: list[float],
    sma_period: int = SMA_PERIOD,
    rsi_period: int = RSI_PERIOD,
) -> str | None:
    """
    Returns "CALL", "PUT", or None (no valid signal).
    """
    sma = calculate_sma(prices, sma_period)
    rsi = calculate_rsi(prices, rsi_period)
    trend_strength = calculate_adx(prices)

    if sma is None or rsi is None or trend_strength is None:
        return None

    current_price = prices[-1]
    log.info(f"  Indicators → P={current_price:.4f} SMA={sma:.4f} RSI={rsi:.2f} Strength={trend_strength:.1f}")

    if trend_strength < ADX_THRESHOLD:
        return None  # Market is too choppy/ranging

    if current_price > sma and rsi > RSI_OVERBOUGHT:
        return "CALL"
    elif current_price < sma and rsi < RSI_OVERSOLD:
        return "PUT"
    else:
        return None


# ═════════════════════════════════════════════════════════════════════════════
#                           GHOST (VIRTUAL) ENGINE
# ═════════════════════════════════════════════════════════════════════════════

class GhostEngine:
    """
    Simulates trades without touching the real account.
    Tracks consecutive virtual losses to decide when to go live.
    """

    def __init__(self, trigger_losses: int = GHOST_LOSSES_BEFORE_REAL):
        self.trigger_losses        = trigger_losses
        self.consecutive_losses    = 0
        self.total_virtual_trades  = 0
        self.total_virtual_wins    = 0
        self.total_virtual_losses  = 0
        self.ghost_active          = True   # stays True until we decide to go real

    def reset_consecutive(self):
        self.consecutive_losses = 0

    def simulate_trade(self, direction: str) -> str:
        """
        Simulates a single tick-trade outcome against the live tick feed.
        In ghost mode we use a simple coin-flip (50/50) as the synthetic
        market is random — the real edge comes from the SMA/RSI filters
        constraining WHEN we enter, not from predicting every tick.

        Returns "win" or "loss".
        """
        outcome = random.choice(["win", "loss"])
        self.total_virtual_trades += 1

        if outcome == "loss":
            self.consecutive_losses += 1
            self.total_virtual_losses += 1
            log.info(
                f"👻 Ghost trade #{self.total_virtual_trades}: {direction} → LOSS "
                f"(consecutive losses: {self.consecutive_losses}/{self.trigger_losses})"
            )
        else:
            self.consecutive_losses = 0
            self.total_virtual_wins += 1
            log.info(
                f"👻 Ghost trade #{self.total_virtual_trades}: {direction} → WIN "
                f"(consecutive losses reset to 0)"
            )

        return outcome

    @property
    def should_go_real(self) -> bool:
        """True once we've hit the required consecutive ghost losses."""
        return self.consecutive_losses >= self.trigger_losses


# ═════════════════════════════════════════════════════════════════════════════
#                               SESSION STATE
# ═════════════════════════════════════════════════════════════════════════════

class SessionState:
    """Tracks all real-money session variables."""

    def __init__(self):
        self.stake              = INITIAL_STAKE
        self.initial_locked     = False         # True after first real win
        self.total_real_profit  = 0.0
        self.real_trade_count   = 0
        self.consecutive_losses = 0             # Tracked for Martingale Cap
        self.next_direction     = "CALL"        # alternating fallback
        self.last_trade_time    = 0.0           # unix timestamp
        self.first_win_achieved = False
        self.profit_floor       = -HARD_STOP_LOSS

    # ── Cooldown ──────────────────────────────────────────────────────────────

    def cooldown_remaining(self) -> float:
        elapsed = time.time() - self.last_trade_time
        remaining = COOLDOWN_SECS - elapsed
        return max(0.0, remaining)

    def is_cooled_down(self) -> bool:
        return self.cooldown_remaining() == 0.0

    def record_trade_time(self):
        self.last_trade_time = time.time()

    # ── Outcome processing ────────────────────────────────────────────────────

    def process_win(self, profit: float):
        """Called after a real winning trade."""
        self.real_trade_count   += 1
        self.total_real_profit  += profit
        self.consecutive_losses  = 0  # Reset on win
        log.info(f"✅ Real WIN  | Profit this trade: +${profit:.4f} | Session P/L: ${self.total_real_profit:.4f}")

        # Dynamic Profit Floor (Lock in gains)
        if self.total_real_profit >= 5.00 and self.profit_floor < 2.50:
            self.profit_floor = 2.50
            log.info("🛡️ TRAILING LOCK ACTIVATED: Session floor set to $2.50 profit.")

        if not self.first_win_achieved:
            self.first_win_achieved = True
            self.initial_locked     = True
            log.info("🔒 Initial $1.50 stake LOCKED. Using only profits as stake from now on.")

        # Reset stake to $1.50 after a win (XML behaviour)
        self.stake = WIN_RESET_TO
        self.next_direction = "CALL"

    def process_loss(self, loss_amount: float):
        """Called after a real losing trade."""
        self.real_trade_count  += 1
        self.total_real_profit -= loss_amount
        self.consecutive_losses += 1
        
        log.info(f"❌ Real LOSS | Loss this trade: -${loss_amount:.4f} | Session P/L: ${self.total_real_profit:.4f}")

        if self.consecutive_losses >= MAX_MARTINGALE_STEPS:
            log.warning(f"🛡️ Martingale Safety Cap Hit ({MAX_MARTINGALE_STEPS} losses). Resetting stake to avoid blowout.")
            self.stake = WIN_RESET_TO
            self.consecutive_losses = 0
        else:
            # Martingale: multiply stake by 1.071 (from XML)
            new_stake = self.stake * MARTINGALE_MULT

            # Initial protection: after first win, never stake more than accumulated profit
            if self.initial_locked:
                available = self.total_real_profit
                if available <= 0.35:
                    log.warning("⚠️ Profit depleted — using minimum $0.35")
                    new_stake = 0.35
                else:
                    new_stake = min(new_stake, available)

            self.stake = min(round(new_stake, 2), MAX_STAKE_CEILING)
            log.info(f"📈 Martingale Step {self.consecutive_losses} | New stake: ${self.stake:.2f}")

        # Flip direction on loss
        self.next_direction = "PUT" if self.next_direction == "CALL" else "CALL"

    # ── Guard checks ──────────────────────────────────────────────────────────

    def check_hard_stop(self) -> bool:
        """Returns True if we've hit the hard stop or the profit floor."""
        if self.total_real_profit <= self.profit_floor:
            reason = "HARD STOP" if self.profit_floor < 0 else "PROFIT FLOOR LOCK"
            log.critical(
                f"🛑 {reason} TRIGGERED | Total P/L: ${self.total_real_profit:.4f} <= ${self.profit_floor:.2f}"
            )
            return True
        return False

    def check_profit_target(self) -> bool:
        """Returns True if we've reached the $9.70 profit target."""
        if self.total_real_profit >= PROFIT_TARGET:
            log.info(
                f"🎯 PROFIT TARGET HIT! Total profit: ${self.total_real_profit:.4f} >= ${PROFIT_TARGET:.2f}"
            )
            return True
        return False


# ═════════════════════════════════════════════════════════════════════════════
#                              DERIV API WRAPPERS
# ═════════════════════════════════════════════════════════════════════════════

async def get_tick_history(api: DerivAPI, symbol: str, count: int) -> list[float]:
    """Fetch the last `count` tick prices for the given symbol."""
    response = await api.ticks_history({
        "ticks_history": symbol,
        "count": count,
        "end": "latest",
        "style": "ticks",
    })

    prices = response.get("history", {}).get("prices", [])
    return [float(p) for p in prices]


async def place_real_trade(api: DerivAPI, direction: str, stake: float) -> dict:
    """
    Places a real CALL or PUT contract on R_100 for 1 tick.
    Returns the full buy response dict.
    """
    contract_type = "CALL" if direction == "CALL" else "PUT"

    proposal_response = await api.proposal({
        "proposal": 1,
        "amount": stake,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "duration": DURATION,
        "duration_unit": DURATION_UNIT,
        "symbol": SYMBOL,
    })

    proposal_id = proposal_response["proposal"]["id"]
    log.info(
        f"📋 Proposal received | ID={proposal_id} | "
        f"Payout=${proposal_response['proposal']['payout']:.4f}"
    )

    buy_response = await api.buy({
        "buy": proposal_id,
        "price": stake,
    })

    return buy_response


async def wait_for_contract_result(api: DerivAPI, contract_id: int) -> dict:
    """
    Polls the contract until it's settled (status: sold or open→closed).
    Returns the final profit_loss value.
    """
    while True:
        result = await api.profit_table({
            "profit_table": 1,
            "description": 1,
            "limit": 1,
        })

        transactions = result.get("profit_table", {}).get("transactions", [])
        if transactions:
            tx = transactions[0]
            if tx.get("contract_id") == contract_id:
                return tx

        await asyncio.sleep(2)


# ═════════════════════════════════════════════════════════════════════════════
#                               MAIN BOT LOOP
# ═════════════════════════════════════════════════════════════════════════════

async def run_bot():
    """Main async entry point for the The Void Sentinel (Legacy) Smart Bot."""

    # ── Pre-flight checks ─────────────────────────────────────────────────────
    if not API_TOKEN:
        log.critical("❌ DERIV_TOKEN environment variable is not set!")
        log.critical("   Set it in GitHub Secrets → Actions → DERIV_TOKEN")
        sys.exit(1)

    log.info("═" * 60)
    log.info("   The Void Sentinel (Legacy) SMART BOT — Starting up")
    log.info(f"   Symbol        : {SYMBOL}")
    log.info(f"   Initial Stake : ${INITIAL_STAKE:.2f}")
    log.info(f"   Hard Stop     : -${HARD_STOP_LOSS:.2f}")
    log.info(f"   Profit Target : +${PROFIT_TARGET:.2f}")
    log.info(f"   Ghost Trigger : {GHOST_LOSSES_BEFORE_REAL} consecutive virtual losses")
    log.info(f"   SMA Period    : {SMA_PERIOD}")
    log.info(f"   RSI Period    : {RSI_PERIOD} (<{RSI_OVERSOLD} / >{RSI_OVERBOUGHT})")
    log.info(f"   Cooldown      : {COOLDOWN_SECS}s between real trades")
    log.info("═" * 60)

    # ── Connect to Deriv API ──────────────────────────────────────────────────
    api = DerivAPI(endpoint=WS_URL)

    try:
        auth_response = await api.authorize({"authorize": API_TOKEN})
        balance = auth_response["authorize"]["balance"]
        currency = auth_response["authorize"]["currency"]
        login_id = auth_response["authorize"]["loginid"]
        log.info(f"✔  Authorized | Account: {login_id} | Balance: {balance} {currency}")
    except Exception as e:
        log.critical(f"Authorization failed: {e}")
        await api.disconnect()
        sys.exit(1)

    # ── Initialize state machines ─────────────────────────────────────────────
    ghost   = GhostEngine(trigger_losses=GHOST_LOSSES_BEFORE_REAL)
    session = SessionState()
    prices  = deque(maxlen=TICK_BUFFER_SIZE)

    await send_telegram(f"🚀 *The Void Sentinel (Legacy) Online*\nBalance: ${balance}\nTarget: ${PROFIT_TARGET}")

    log.info(f"📡 Fetching initial {TICK_BUFFER_SIZE} ticks for indicator warm-up…")
    try:
        history = await get_tick_history(api, SYMBOL, TICK_BUFFER_SIZE)
        prices.extend(history)
        log.info(f"   Loaded {len(prices)} historical ticks. Latest price: {prices[-1]:.4f}")
    except Exception as e:
        log.error(f"Failed to load tick history: {e}")
        prices = deque(maxlen=TICK_BUFFER_SIZE)

    # ── Main loop ─────────────────────────────────────────────────────────────
    log.info("🚀 Bot is LIVE — entering main loop…")

    try:
        while True:
            # ── 1. Refresh price feed ─────────────────────────────────────────
            try:
                new_ticks = await get_tick_history(api, SYMBOL, 10)
                for tick in new_ticks:
                    prices.append(tick)
            except Exception as e:
                log.warning(f"Tick fetch error: {e} — retrying in 5s")
                await asyncio.sleep(5)
                continue

            price_list = list(prices)

            # ── 2. Technical filter ───────────────────────────────────────────
            signal = get_trade_direction(price_list)

            if signal is None:
                log.info("⏸  No valid signal (RSI not extreme or not enough data). Waiting 30s…")
                await asyncio.sleep(30)
                continue

            log.info(f"📊 Signal detected: {signal}")

            # ══ GHOST PHASE ═══════════════════════════════════════════════════
            if not ghost.should_go_real:
                log.info(f"👻 GHOST MODE | Simulating {signal} trade…")
                ghost.simulate_trade(signal)

                if ghost.should_go_real:
                    log.info(
                        f"🔥 {GHOST_LOSSES_BEFORE_REAL} consecutive ghost losses detected! "
                        f"Switching to REAL trading mode."
                    )
                await asyncio.sleep(5)   # brief pause between ghost trades
                continue

            # ══ REAL TRADE PHASE ═══════════════════════════════════════════════

            # 3. Cooldown guard
            remaining = session.cooldown_remaining()
            if remaining > 0:
                log.info(f"⏳ Cooldown: {remaining:.0f}s remaining before next real trade…")
                await asyncio.sleep(min(remaining, 30))
                continue

            # 4. Hard-stop / profit-target guards (check BEFORE placing trade)
            if session.check_hard_stop():
                break
            if session.check_profit_target():
                break

            # 5. Initial outlay protection: after first win, only use profit as stake
            trade_stake = session.stake
            if session.initial_locked and session.total_real_profit <= 0:
                log.warning("⚠️  Profit fully depleted — cannot risk initial $1.50. Halting.")
                break

            log.info(
                f"💰 Placing REAL {signal} | Stake: ${trade_stake:.2f} | "
                f"Session P/L: ${session.total_real_profit:.4f}"
            )

            # 6. Place the trade
            try:
                session.record_trade_time()
                buy_resp = await place_real_trade(api, signal, trade_stake)
                contract_id = buy_resp["buy"]["contract_id"]
                buy_price   = buy_resp["buy"]["buy_price"]
                log.info(f"   Contract ID: {contract_id} | Buy price: ${buy_price:.4f}")
            except Exception as e:
                log.error(f"Trade placement failed: {e}")
                await asyncio.sleep(10)
                continue

            # 7. Wait for settlement (tick contracts settle almost instantly)
            log.info("   ⏰ Waiting for contract to settle…")
            await asyncio.sleep(3)   # 1-tick contracts settle in ~2-3 seconds

            try:
                settled = await wait_for_contract_result(api, contract_id)
                profit_loss = float(settled.get("sell_price", 0)) - buy_price

                if profit_loss > 0:
                    session.process_win(profit_loss)
                    # Reset ghost engine after a real win (start ghost watch again)
                    ghost.reset_consecutive()
                else:
                    session.process_loss(abs(profit_loss))

            except Exception as e:
                log.error(f"Failed to get contract result: {e}")
                await asyncio.sleep(5)
                continue

            # 8. Post-trade guard checks
            if session.check_hard_stop():
                break
            if session.check_profit_target():
                break

            # 9. Brief pause before next iteration
            await asyncio.sleep(10)

    except KeyboardInterrupt:
        log.info("🛑 Keyboard interrupt — shutting down gracefully…")
    finally:
        summary = (
            f"🏁 *SESSION COMPLETE*\n"
            f"Result: ${session.total_real_profit:.2f} P/L\n"
            f"Trades: {session.real_trade_count}R / {ghost.total_virtual_trades}V"
        )
        await send_telegram(summary)
        log.info("═" * 60)
        log.info("   SESSION SUMMARY")
        log.info(f"   Real Trades     : {session.real_trade_count}")
        log.info(f"   Virtual Trades  : {ghost.total_virtual_trades}")
        log.info(f"   Total Real P/L  : ${session.total_real_profit:.4f}")
        log.info(f"   Ghost W/L       : {ghost.total_virtual_wins}W / {ghost.total_virtual_losses}L")
        log.info("═" * 60)
        await api.disconnect()
        log.info("   Disconnected from Deriv API. Goodbye! 👋")


# ═════════════════════════════════════════════════════════════════════════════
#                                 ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(run_bot())
