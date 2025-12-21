"""
Utility Functions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Helper functions for bot
"""

import logging
from datetime import datetime, timedelta
from config import *

def setup_logger():
    """Setup logging configuration"""
    logger = logging.getLogger("NiftyBot")
    logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler
    if LOG_TO_FILE:
        file_handler = logging.FileHandler(LOG_FILE_PATH)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger

def get_ist_time():
    """Get current IST time"""
    return datetime.now(IST)

def is_market_open():
    """Check if market is currently open"""
    now = get_ist_time()
    
    # Check weekday (Monday=0, Sunday=6)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    current_time = now.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE

def is_trading_hours():
    """Check if within trading hours"""
    now = get_ist_time()
    
    if not is_market_open():
        return False
    
    current_time = now.time()
    return TRADING_START <= current_time <= TRADING_END

def get_nearest_expiry():
    """Get nearest NIFTY expiry (Tuesday)"""
    today = get_ist_time().date()
    days_ahead = 1 - today.weekday()  # Tuesday = 1
    
    if days_ahead <= 0:  # If today is Tuesday or later
        days_ahead += 7  # Next Tuesday
    
    expiry_date = today + timedelta(days=days_ahead)
    return expiry_date

def get_futures_symbol():
    """Auto-generate futures symbol based on nearest expiry"""
    expiry = get_nearest_expiry()
    month_code = expiry.strftime("%b").upper()[:3]  # JAN, FEB, MAR, etc.
    year_code = expiry.strftime("%y")  # 24, 25, etc.
    
    # Format: NSE_FO|NIFTY25JANFUT
    symbol = f"NSE_FO|NIFTY{year_code}{month_code}FUT"
    return symbol

def round_to_strike(price, interval=50):
    """Round price to nearest strike"""
    return round(price / interval) * interval

def calculate_percentage_change(old_value, new_value):
    """Calculate percentage change"""
    if old_value == 0:
        return 0
    return ((new_value - old_value) / old_value) * 100

def format_number(num):
    """Format large numbers (Indian style)"""
    if num >= 10000000:  # 1 Crore
        return f"{num/10000000:.2f}Cr"
    elif num >= 100000:  # 1 Lakh
        return f"{num/100000:.2f}L"
    elif num >= 1000:
        return f"{num/1000:.2f}K"
    else:
        return f"{num:.2f}"

def get_market_status():
    """Get current market status"""
    if not is_market_open():
        return "CLOSED"
    elif not is_trading_hours():
        return "OPEN (Non-trading hours)"
    else:
        return "TRADING"

def is_expiry_day():
    """Check if today is expiry day"""
    today = get_ist_time().weekday()
    return today == 1  # Tuesday = 1

def time_until_close():
    """Get minutes until market close"""
    now = get_ist_time()
    close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if now > close_time:
        return 0
    
    diff = close_time - now
    return int(diff.total_seconds() / 60)

# Signal type enum
class SignalType:
    CE_BUY = "CE_BUY"
    PE_BUY = "PE_BUY"
    NO_TRADE = "NO_TRADE"

# Market status
class MarketStatus:
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
