# 🌌 The Void Sentinel — Smart Algorithmic Trading Bot

> A professional-grade Deriv trading engine featuring **Ghost-First** logic, **ADX/SMA/RSI** triple-filtering, and strict risk management. Managed 24/7 via GitHub Actions.

---

## 📁 Project Structure

```
void-sentinel/
├── sentinel.py               ← Main trading engine (v3.0)
├── void_sentinel_legacy.py    ← Legacy logic (kept for reference)
├── requirements.txt          ← Python dependencies
├── README.md                 ← This documentation
├── void_sentinel_reference.xml ← Original XML strategy
└── .github/
    └── workflows/
        └── main.yml          ← GitHub Actions (The "Heartbeat")
```

---

## 🧠 Strategy: "The Perfect Sentinel"

| Feature | Details |
|---|---|
| **Market** | Volatility 100 Index (`R_100`) |
| **Contract** | Rise / Fall (CALL / PUT) — 1 tick |
| **Initial Stake** | $1.50 (Configurable) |
| **Martingale** | ×1.071 (Conservative recovery) |
| **Ghost Engine** | Waits for **X** virtual losses before going real (Default: 3) |
| **Hard Shield** | Hard stop at -$2.00 total loss (Configurable) |
| **Profit Lock** | Secures the bag once win targets are met |
| **Triple Filter** | SMA (Trend) + RSI (Momentum) + ADX (Strength) |
| **Cooldown** | 120-second pause between strikes |

---

## 📤 Quick Deploy to GitHub

If you haven't pushed your code yet, run these commands in your project folder:

```powershell
git init
git add .
git commit -m "Initialize The Void Sentinel v3.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/void-sentinel.git
git push -u origin main
```

---

## 🔑 Required Secrets

Add these to **Settings > Secrets and variables > Actions > Secrets**:
- `DERIV_TOKEN`: Your Deriv API Token (Trade/Read).
- `TELEGRAM_TOKEN`: Your Telegram Bot Token.
- `TELEGRAM_CHAT_ID`: Your Telegram Chat ID.
- `GH_TOKEN`: Your GitHub Personal Access Token (for persistence).

## ⚙️ Configurable Variables

Add these to **Settings > Secrets and variables > Actions > Variables**:
- `INITIAL_STAKE`: Default $1.50
- `STOP_LOSS`: Default $2.00
- `GHOST_THRESHOLD`: Default 3
- `TAKE_PROFIT`: Default $10.00

---

## 🛡️ Risk Disclaimer

Algorithmic trading carries high risk. This bot is provided for educational/advanced trading purposes. Only risk capital you can afford to lose.
