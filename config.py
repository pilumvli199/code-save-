"""
Configuration & Settings
ULTIMATE FIX: Better thresholds, analysis range (ATM ± 2), re-entry protection
"""
import os
from datetime import datetime, timedelta, time

# API Configuration
API_VERSION = 'v2'
UPSTOX_BASE_URL = 'https://api.upstox.com'
UPSTOX_QUOTE_URL = f'{UPSTOX_BASE_URL}/v2/market-quote/quotes'
UPSTOX_HISTORICAL_URL = f'{UPSTOX_BASE_URL}/v2/historical-candle'
UPSTOX_OPTION_CHAIN_URL = f'{UPSTOX_BASE_URL}/v2/option/chain'
UPSTOX_INSTRUMENTS_URL = f'{UPSTOX_BASE_URL}/v2/market-quote/instrument'

UPSTOX_ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN', '')

# Memory & Storage - 24 HOURS
REDIS_URL = os.getenv('REDIS_URL', None)
MEMORY_TTL_HOURS = 24
MEMORY_TTL_SECONDS = MEMORY_TTL_HOURS * 3600
SCAN_INTERVAL = 60  # seconds

# Market Timings
PREMARKET_START = time(9, 10)
PREMARKET_END = time(9, 15)
FIRST_DATA_TIME = time(9, 16)
SIGNAL_START = time(9, 21)
MARKET_CLOSE = time(15, 30)
WARMUP_MINUTES = 15
EARLY_SIGNAL_CONFIDENCE = 85

# ==================== STRIKE RANGE SETTINGS ====================

# Storage: Store 11 strikes (ATM ± 5) in Redis for backup
STORAGE_STRIKE_RANGE = 5  # ± 5 strikes = 11 total

# Analysis: Use only 5 strikes (ATM ± 2) for signal generation
ANALYSIS_STRIKE_RANGE = 2  # ✅ ± 2 strikes = 5 total (HIGH PRECISION)

# ⚡ This ensures:
# - 11 strikes stored (handles big moves)
# - Only 5 strikes analyzed (avoids noise from Deep OTM/ITM)
# - ATM shift transitions smooth (data already in memory)

# ==================== FIXED THRESHOLDS ====================

# OI Thresholds - STRICTER
OI_THRESHOLD_STRONG = 5.0
OI_THRESHOLD_MEDIUM = 2.5
ATM_OI_THRESHOLD = 3.0
OI_5M_THRESHOLD = 2.0

# Multi-timeframe Requirements
MIN_OI_5M_FOR_ENTRY = 2.0
MIN_OI_15M_FOR_ENTRY = 2.5
STRONG_OI_5M_THRESHOLD = 3.5
STRONG_OI_15M_THRESHOLD = 5.0

# Volume Thresholds
VOL_SPIKE_MULTIPLIER = 2.0
VOL_SPIKE_STRONG = 3.0

# PCR Thresholds
PCR_BULLISH = 1.2
PCR_BEARISH = 0.8

# Technical Indicators
ATR_PERIOD = 14
ATR_TARGET_MULTIPLIER = 2.5
ATR_SL_MULTIPLIER = 1.5
ATR_SL_GAMMA_MULTIPLIER = 2.0

# VWAP Settings
VWAP_BUFFER = 10
VWAP_DISTANCE_MAX_ATR_MULTIPLE = 0.5
VWAP_STRICT_MODE = True

# Candle Settings
MIN_CANDLE_SIZE = 5

# ==================== EXIT LOGIC - FIXED ====================

EXIT_OI_REVERSAL_THRESHOLD = 3.0
EXIT_OI_CONFIRMATION_CANDLES = 2
EXIT_OI_SPIKE_THRESHOLD = 8.0

EXIT_VOLUME_DRY_THRESHOLD = 0.5
EXIT_PREMIUM_DROP_PERCENT = 15
EXIT_CANDLE_REJECTION_MULTIPLIER = 2

# Minimum Hold Time
MIN_HOLD_TIME_MINUTES = 10
MIN_HOLD_BEFORE_OI_EXIT = 8

# ==================== RE-ENTRY PROTECTION ====================

SAME_STRIKE_COOLDOWN_MINUTES = 10
OPPOSITE_SIGNAL_COOLDOWN_MINUTES = 5
SAME_DIRECTION_COOLDOWN_MINUTES = 3

# ==================== RISK MANAGEMENT ====================

USE_PREMIUM_SL = True
PREMIUM_SL_PERCENT = 30

ENABLE_TRAILING_SL = True
TRAILING_SL_TRIGGER = 0.6
TRAILING_SL_DISTANCE = 0.4
TRAILING_SL_UPDATE_THRESHOLD = 5

SIGNAL_COOLDOWN_SECONDS = 180
MIN_PRIMARY_CHECKS = 2
MIN_CONFIDENCE = 70

# ==================== TELEGRAM ====================

TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ==================== NIFTY CONFIG ====================

NIFTY_SPOT_KEY = None
NIFTY_INDEX_KEY = None
NIFTY_FUTURES_KEY = None

STRIKE_GAP = 50
LOT_SIZE = 50
ATR_FALLBACK = 30


# ==================== HELPER FUNCTIONS ====================

def get_next_tuesday_expiry():
    """Get next Tuesday expiry (weekly)"""
    today = datetime.now()
    days_ahead = 1 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    next_tuesday = today + timedelta(days=days_ahead)
    return next_tuesday.strftime('%Y-%m-%d')


def get_futures_contract_name():
    """Generate NIFTY futures contract name"""
    expiry = datetime.strptime(get_next_tuesday_expiry(), '%Y-%m-%d')
    year = expiry.strftime('%y')
    month = expiry.strftime('%b').upper()
    return f"NIFTY{year}{month}FUT"


def calculate_atm_strike(spot_price):
    """Calculate ATM strike"""
    return round(spot_price / STRIKE_GAP) * STRIKE_GAP


def get_strike_range(atm_strike, num_strikes=STORAGE_STRIKE_RANGE):
    """
    Get min/max strike range for STORAGE
    
    Default: 11 strikes (ATM ± 5) stored in Redis
    """
    min_strike = atm_strike - (num_strikes * STRIKE_GAP)
    max_strike = atm_strike + (num_strikes * STRIKE_GAP)
    return min_strike, max_strike


def get_analysis_strike_range(atm_strike):
    """
    ✅ NEW: Get strike range for ANALYSIS (ATM ± 2)
    
    Returns only 5 strikes for high-precision signal generation
    This avoids noise from Deep OTM/ITM strikes
    """
    min_strike = atm_strike - (ANALYSIS_STRIKE_RANGE * STRIKE_GAP)
    max_strike = atm_strike + (ANALYSIS_STRIKE_RANGE * STRIKE_GAP)
    return min_strike, max_strike
