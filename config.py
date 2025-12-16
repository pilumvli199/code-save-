"""
Configuration & Settings v7.0 - COMPREHENSIVE FIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆕 ADDED:
- 30m OI comparison thresholds
- OI Velocity pattern thresholds
- OTM strike analysis settings
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
from datetime import datetime, timedelta, time

# ==================== API CONFIGURATION ====================
API_VERSION = 'v2'
UPSTOX_BASE_URL = 'https://api.upstox.com'
UPSTOX_QUOTE_URL = f'{UPSTOX_BASE_URL}/v2/market-quote/quotes'
UPSTOX_HISTORICAL_URL = f'{UPSTOX_BASE_URL}/v2/historical-candle'
UPSTOX_OPTION_CHAIN_URL = f'{UPSTOX_BASE_URL}/v2/option/chain'
UPSTOX_INSTRUMENTS_URL = 'https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz'

UPSTOX_ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN', '')

# ==================== MEMORY & STORAGE ====================
REDIS_URL = os.getenv('REDIS_URL', None)
MEMORY_TTL_HOURS = 24
MEMORY_TTL_SECONDS = MEMORY_TTL_HOURS * 3600
SCAN_INTERVAL = 60  # seconds

# 🔧 MODIFIED: Warmup reduced to 15 minutes (was 35 for 30m)
OI_MEMORY_SCANS = 20  # 20 scans = 20 minutes (15m warmup + 5m buffer)
OI_MEMORY_BUFFER = 5  # Extra buffer for tolerance

# ==================== MARKET TIMINGS ====================
PREMARKET_START = time(9, 10)
PREMARKET_END = time(9, 15)
FIRST_DATA_TIME = time(9, 16)
SIGNAL_START = time(9, 21)     # 🔥 EARLY SIGNALS from 9:21 AM
MARKET_CLOSE = time(15, 30)
WARMUP_MINUTES = 15             # 🔧 REDUCED: Was 30, now 15
EARLY_SIGNAL_CONFIDENCE = 85    # 🔥 HIGH threshold for early signals (before full warmup)

# ==================== STRIKE CONFIGURATION ====================
STRIKE_GAP = 50
STRIKES_TO_FETCH = 5           # ATM ± 5 = 11 total strikes
STRIKES_FOR_ANALYSIS = 2       # ATM ± 2 = 5 strikes for deep analysis

# 🆕 OTM STRIKE ANALYSIS (from Image 3)
OTM_RESISTANCE_OFFSET = 100    # Check ATM + 100 for resistance
OTM_SUPPORT_OFFSET = 100       # Check ATM - 100 for support
OTM_HIGH_OI_THRESHOLD = 1000000  # OI above this = significant level

# ==================== OI THRESHOLDS ====================
# Multi-timeframe OI thresholds
OI_5M_THRESHOLD = 2.0
OI_15M_THRESHOLD = 2.5
OI_30M_THRESHOLD = 3.0  # 🆕 NEW: 30m should be stronger

# Signal generation requirements
MIN_OI_5M_FOR_ENTRY = 2.0
MIN_OI_15M_FOR_ENTRY = 2.5
MIN_OI_30M_FOR_ENTRY = 3.0  # 🆕 NEW

STRONG_OI_5M_THRESHOLD = 3.5
STRONG_OI_15M_THRESHOLD = 5.0
STRONG_OI_30M_THRESHOLD = 6.0  # 🆕 NEW

# ATM-specific
ATM_OI_THRESHOLD = 3.0
OI_THRESHOLD_STRONG = 5.0
OI_THRESHOLD_MEDIUM = 2.5

# 🆕 OI VELOCITY PATTERNS (from Image 1)
# Acceleration: 15m > 30m (speed increasing)
VELOCITY_ACCELERATION_MIN = 5.0
VELOCITY_ACCELERATION_STRONG = 8.0

# Deceleration: 15m < 30m (speed decreasing)
VELOCITY_DECELERATION_MIN = 5.0

# Monster Loading: Both 15m & 30m very high
VELOCITY_MONSTER_15M = 8.0
VELOCITY_MONSTER_30M = 8.0

# Exhaustion: 30m high but 15m low (slowing)
VELOCITY_EXHAUSTION_30M = 6.0
VELOCITY_EXHAUSTION_15M = 2.0

# ==================== VOLUME THRESHOLDS ====================
VOL_SPIKE_MULTIPLIER = 2.0
VOL_SPIKE_STRONG = 3.0

# ==================== PCR THRESHOLDS ====================
PCR_BULLISH = 1.2
PCR_BEARISH = 0.8

# 🆕 PCR BIAS BANDS (from Image 1)
PCR_OVERHEATED = 0.7   # Too bullish
PCR_BALANCED_BULL = 0.9
PCR_NEUTRAL_LOW = 0.9
PCR_NEUTRAL_HIGH = 1.1
PCR_BALANCED_BEAR = 1.3
PCR_OVERSOLD = 1.3     # Too bearish

# ==================== TECHNICAL INDICATORS ====================
ATR_PERIOD = 14
ATR_TARGET_MULTIPLIER = 2.5
ATR_SL_MULTIPLIER = 1.5
ATR_SL_GAMMA_MULTIPLIER = 2.0

# VWAP Settings
VWAP_BUFFER = 10
VWAP_DISTANCE_MAX_ATR_MULTIPLE = 3.0
VWAP_STRICT_MODE = True

# 🆕 VWAP SCORE (raised threshold)
MIN_VWAP_SCORE = 70  # Was 50 - Now stricter

# Candle Settings
MIN_CANDLE_SIZE = 5

# ==================== EXIT LOGIC ====================
EXIT_OI_REVERSAL_THRESHOLD = 3.0
EXIT_OI_CONFIRMATION_CANDLES = 2
EXIT_OI_SPIKE_THRESHOLD = 8.0

EXIT_VOLUME_DRY_THRESHOLD = 0.5
EXIT_PREMIUM_DROP_PERCENT = 15
EXIT_CANDLE_REJECTION_MULTIPLIER = 2

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

# ==================== LOGGING ====================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ==================== NIFTY CONFIG ====================
NIFTY_SPOT_KEY = None
NIFTY_INDEX_KEY = None
NIFTY_FUTURES_KEY = None

LOT_SIZE = 50
ATR_FALLBACK = 30


# ==================== HELPER FUNCTIONS ====================

def get_next_weekly_expiry():
    """Get next Tuesday (weekly options expiry)"""
    today = datetime.now()
    days_ahead = 1 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    next_tuesday = today + timedelta(days=days_ahead)
    return next_tuesday.strftime('%Y-%m-%d')


def get_futures_contract_name():
    """Generate display name for futures contract"""
    return "NIFTY_FUTURES_AUTO"


def calculate_atm_strike(spot_price):
    """Calculate ATM strike (rounded to nearest 50)"""
    return round(spot_price / STRIKE_GAP) * STRIKE_GAP


def get_strike_range_fetch(atm_strike):
    """Get strike range for FETCHING (11 strikes total)"""
    min_strike = atm_strike - (STRIKES_TO_FETCH * STRIKE_GAP)
    max_strike = atm_strike + (STRIKES_TO_FETCH * STRIKE_GAP)
    return min_strike, max_strike


def get_deep_analysis_strikes(atm_strike):
    """Get strikes for DEEP ANALYSIS (5 strikes only)"""
    strikes = []
    for i in range(-STRIKES_FOR_ANALYSIS, STRIKES_FOR_ANALYSIS + 1):
        strikes.append(atm_strike + (i * STRIKE_GAP))
    return strikes


def get_otm_strikes(atm_strike):
    """
    🆕 Get OTM strikes for support/resistance analysis
    Returns: (otm_above, otm_below)
    """
    otm_above = atm_strike + OTM_RESISTANCE_OFFSET  # ATM + 100 (resistance)
    otm_below = atm_strike - OTM_SUPPORT_OFFSET     # ATM - 100 (support)
    return otm_above, otm_below


def is_deep_analysis_strike(strike, atm_strike):
    """Check if strike is in deep analysis range"""
    diff = abs(strike - atm_strike)
    return diff <= (STRIKES_FOR_ANALYSIS * STRIKE_GAP)
