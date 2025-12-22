"""
NIFTY 50 Trading Bot - Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Based on: Price + OI + PCR Combined Strategy
Author: Yellow Flash
Date: December 2024
"""

import pytz
from datetime import time

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CREDENTIALS (From Environment Variables)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import os

# Upstox API
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_API_SECRET = os.getenv("UPSTOX_API_SECRET")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TRADING SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Instrument
SYMBOL = "NIFTY"
INDEX_SYMBOL = "NSE_INDEX|Nifty 50"

# Futures Symbol - Can be set via ENV or auto-calculated
FUTURES_SYMBOL = os.getenv("FUTURES_SYMBOL", None)  # If not set, will auto-detect in code

# Expiry
NIFTY_EXPIRY_DAY = "Tuesday"  # NIFTY weekly expiry

# Timezone
IST = pytz.timezone('Asia/Kolkata')

# Trading Hours
MARKET_OPEN = time(9, 15)
TRADING_START = time(9, 15)  # Start at market open
TRADING_END = time(15, 20)    # Stop 10 min before close
MARKET_CLOSE = time(15, 30)

# Scan Interval
SCAN_INTERVAL_SECONDS = 300  # Every 5 minutes (300 seconds) for OI analysis

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRATEGY PARAMETERS (From PDF Guide)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# PCR Thresholds
PCR_STRONG_SUPPORT = 2.5      # PCR > 2.5 = Strong support
PCR_SUPPORT = 1.5             # PCR 1.5-2.5 = Support
PCR_NEUTRAL_HIGH = 1.0        # PCR 1.0-1.5 = Neutral bullish
PCR_NEUTRAL_LOW = 0.7         # PCR 0.7-1.0 = Neutral bearish
PCR_RESISTANCE = 0.5          # PCR 0.5-0.7 = Resistance
PCR_STRONG_RESISTANCE = 0.5   # PCR < 0.5 = Strong resistance

# OI Change Thresholds (percentage)
OI_SIGNIFICANT_CHANGE = 5.0   # 5% change = significant
OI_STRONG_CHANGE = 10.0       # 10% change = strong signal

# Price Change Thresholds (points)
PRICE_SIGNIFICANT_MOVE = 20   # 20 points = significant
PRICE_STRONG_MOVE = 50        # 50 points = strong move

# Signal Confidence
MIN_CONFIDENCE = 70           # Minimum confidence to trade
HIGH_CONFIDENCE = 85          # High confidence threshold

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RISK MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Position Sizing
CAPITAL_PER_TRADE = 10000     # ₹10,000 per trade
MAX_TRADES_PER_DAY = 3        # Maximum 3 trades per day

# Stop Loss & Target
STOP_LOSS_PERCENT = 30        # 30% SL (as per your strategy)
TARGET_MULTIPLIER = 2.0       # 2x target (60% profit)

# Position Management
MAX_HOLDING_TIME_MINUTES = 120  # 2 hours max hold
TRAIL_SL_AFTER_PROFIT = 20      # Trail SL after 20% profit

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA COLLECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Option Chain
STRIKES_RANGE = 500           # Fetch ±500 points from ATM
STRIKES_INTERVAL = 50         # NIFTY strike interval

# Historical Data
HISTORY_RETENTION_MINUTES = 60  # Keep 60 min history
MIN_HISTORY_FOR_SIGNAL = 3      # Need 3 data points minimum

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILTERING (From your requirements)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Volume Filter
MIN_VOLUME_RATIO = 1.0        # Normal volume required

# VWAP Filter
VWAP_FILTER_ENABLED = True
VWAP_DEVIATION_MAX = 0.5      # 0.5% max deviation

# Time-based Filters
AVOID_FIRST_15_MIN = True     # Skip 9:15-9:30
AVOID_LAST_15_MIN = True      # Skip 15:15-15:30
CAUTIOUS_EXPIRY_DAY = True    # Be careful on Tuesday

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LOG_LEVEL = "INFO"            # DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True
LOG_FILE_PATH = "bot_logs.log"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ALERTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SEND_TELEGRAM_ALERTS = True
SEND_STARTUP_MESSAGE = True
SEND_DAILY_SUMMARY = True

# Alert Types
ALERT_ON_SIGNAL = True
ALERT_ON_ENTRY = True
ALERT_ON_EXIT = True
ALERT_ON_SL_HIT = True
ALERT_ON_TARGET_HIT = True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ADVANCED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Retry Settings
API_RETRY_ATTEMPTS = 3
API_RETRY_DELAY = 2           # seconds

# Rate Limiting
API_RATE_LIMIT_DELAY = 0.5    # 0.5s between calls

# Debug Mode
DEBUG_MODE = False            # Set True for testing
PAPER_TRADING = True          # Set False for live trading

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VERSION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_VERSION = "1.0-NIFTY-OI-PCR"
BOT_NAME = "NIFTY OI+PCR Bot"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VALIDATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_config():
    """Validate configuration settings"""
    errors = []
    
    # Check API credentials
    if not UPSTOX_API_KEY or UPSTOX_API_KEY == "your_api_key_here":
        errors.append("UPSTOX_API_KEY not set!")
    
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token":
        errors.append("TELEGRAM_BOT_TOKEN not set!")
    
    # Check parameters
    if MIN_CONFIDENCE > 100 or MIN_CONFIDENCE < 0:
        errors.append("MIN_CONFIDENCE must be 0-100")
    
    if STOP_LOSS_PERCENT > 50:
        errors.append("STOP_LOSS_PERCENT too high!")
    
    return errors

if __name__ == "__main__":
    errors = validate_config()
    if errors:
        print("❌ Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✅ Configuration valid!")
