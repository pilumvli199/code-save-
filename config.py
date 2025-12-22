"""
Configuration & Settings - NIFTY Bot Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Based on: v7.0 Comprehensive Fix
Modified for: ±2 ATM strike focus
"""
import os
from datetime import datetime, timedelta, time
import pytz

# ==================== API CONFIGURATION ====================
API_VERSION = 'v2'
UPSTOX_BASE_URL = 'https://api.upstox.com'
UPSTOX_QUOTE_URL = f'{UPSTOX_BASE_URL}/v2/market-quote/quotes'
UPSTOX_HISTORICAL_URL = f'{UPSTOX_BASE_URL}/v2/historical-candle'
UPSTOX_OPTION_CHAIN_URL = f'{UPSTOX_BASE_URL}/v2/option/chain'
UPSTOX_INSTRUMENTS_URL = 'https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz'

# Clean token (remove whitespace/newlines)
UPSTOX_ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN', '').strip()

# ==================== TIMEZONE ====================
IST = pytz.timezone('Asia/Kolkata')

# ==================== MEMORY & STORAGE ====================
REDIS_URL = os.getenv('REDIS_URL', None)
MEMORY_TTL_HOURS = 24
SCAN_INTERVAL = 300  # 5 minutes
SCAN_INTERVAL_SECONDS = 300  # Same as SCAN_INTERVAL

# OI Memory: 35 scans = 30+ minutes
OI_MEMORY_SCANS = 35
OI_MEMORY_BUFFER = 5

# ==================== MARKET TIMINGS ====================
MARKET_OPEN = time(9, 15)
TRADING_START = time(9, 15)
TRADING_END = time(15, 20)
SIGNAL_START = time(9, 15)
MARKET_CLOSE = time(15, 30)

# ==================== STRIKE CONFIGURATION ====================
STRIKE_GAP = 50
STRIKES_TO_FETCH = 2  # ±2 ATM = 5 strikes total
STRIKES_FOR_ANALYSIS = 2

# ==================== OI THRESHOLDS ====================
OI_5M_THRESHOLD = 2.0
OI_15M_THRESHOLD = 2.5
MIN_OI_15M_FOR_ENTRY = 2.5
STRONG_OI_15M_THRESHOLD = 5.0
ATM_OI_THRESHOLD = 3.0

# ==================== PCR THRESHOLDS ====================
PCR_STRONG_SUPPORT = 2.5
PCR_SUPPORT = 1.5
PCR_NEUTRAL_HIGH = 1.1
PCR_NEUTRAL_LOW = 0.9
PCR_RESISTANCE = 0.7
PCR_STRONG_RESISTANCE = 0.5

# ==================== SIGNAL SETTINGS ====================
MIN_CONFIDENCE = 70
MAX_TRADES_PER_DAY = 3
CAPITAL_PER_TRADE = 10000
STOP_LOSS_PERCENT = 30
TARGET_MULTIPLIER = 2.0

# Price movement thresholds
PRICE_SIGNIFICANT_MOVE = 20  # points
PRICE_STRONG_MOVE = 50  # points

# OI change significance
OI_SIGNIFICANT_CHANGE = 5.0   # %
OI_STRONG_CHANGE = 10.0      # %

# ==================== FILTERS ====================
VWAP_FILTER_ENABLED = True
VWAP_DEVIATION_MAX = 0.5  # %
CAUTIOUS_EXPIRY_DAY = True
AVOID_FIRST_15_MIN = False
AVOID_LAST_15_MIN = False
MIN_HISTORY_FOR_SIGNAL = 3  # scans

# ==================== TELEGRAM ====================
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
SEND_TELEGRAM_ALERTS = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
SEND_STARTUP_MESSAGE = True
SEND_DAILY_SUMMARY = False
ALERT_ON_SIGNAL = True

# ==================== BOT INFO ====================
BOT_NAME = "NIFTY OI+PCR Bot"
BOT_VERSION = "1.0-NIFTY-OI-PCR"
SYMBOL = "NIFTY"
NIFTY_EXPIRY_DAY = "Tuesday"

# ==================== HELPER FUNCTIONS ====================

def get_next_weekly_expiry():
    """Get next Tuesday (NIFTY weekly expiry)"""
    today = datetime.now(IST)
    days_ahead = 1 - today.weekday()  # Tuesday = 1
    if days_ahead <= 0:
        days_ahead += 7
    next_tuesday = today + timedelta(days=days_ahead)
    return next_tuesday.strftime('%Y-%m-%d')


def calculate_atm_strike(spot_price):
    """Calculate ATM strike"""
    return round(spot_price / STRIKE_GAP) * STRIKE_GAP


def get_strike_range_fetch(atm_strike):
    """Get strike range for fetching (5 strikes: ±2 ATM)"""
    min_strike = atm_strike - (STRIKES_TO_FETCH * STRIKE_GAP)
    max_strike = atm_strike + (STRIKES_TO_FETCH * STRIKE_GAP)
    return min_strike, max_strike


def validate_config():
    """Validate configuration"""
    errors = []
    
    if not UPSTOX_ACCESS_TOKEN:
        errors.append("UPSTOX_ACCESS_TOKEN not set!")
    
    if SEND_TELEGRAM_ALERTS:
        if not TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN not set!")
        if not TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID not set!")
    
    return errors
