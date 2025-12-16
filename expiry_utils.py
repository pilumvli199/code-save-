"""
Auto Expiry Date Calculator for NIFTY Options
Automatically selects nearest available expiry (Tuesday for NIFTY 50)
"""

from datetime import datetime, timedelta
import pytz

IST = pytz.timezone('Asia/Kolkata')


def get_next_tuesday():
    """
    Get next Tuesday date (NIFTY 50 weekly expiry)
    
    Logic:
    - If today is Tuesday AND time < 3:30 PM → Use TODAY
    - If today is Tuesday AND time >= 3:30 PM → Use NEXT Tuesday
    - Otherwise → Use next Tuesday
    
    Returns:
        str: Expiry date in YYYY-MM-DD format
    """
    today = datetime.now(IST).date()
    now = datetime.now(IST)
    
    # Days until next Tuesday (0=Mon, 1=Tue, 2=Wed, ..., 6=Sun)
    days_ahead = (1 - today.weekday()) % 7
    
    # If today is Tuesday
    if today.weekday() == 1:  # Tuesday
        # Before 3:30 PM → Use today's expiry
        if now.hour < 15 or (now.hour == 15 and now.minute < 30):
            next_tuesday = today
        else:
            # After 3:30 PM → Use next week
            next_tuesday = today + timedelta(days=7)
    elif days_ahead == 0:  # Should not reach here, but safety
        next_tuesday = today + timedelta(days=7)
    else:
        # Any other day → Next Tuesday
        next_tuesday = today + timedelta(days=days_ahead)
    
    return next_tuesday.strftime('%Y-%m-%d')


def get_next_thursday():
    """
    Get next Thursday date (NIFTY MONTHLY expiry - last Thursday)
    
    Returns:
        str: Expiry date in YYYY-MM-DD format
    """
    today = datetime.now(IST).date()
    
    # Days until next Thursday
    days_ahead = (3 - today.weekday()) % 7
    
    if days_ahead == 0:  # Today is Thursday
        next_thursday = today + timedelta(days=7)
    else:
        next_thursday = today + timedelta(days=days_ahead)
    
    return next_thursday.strftime('%Y-%m-%d')


def get_next_weekly_expiry():
    """
    Get nearest weekly expiry for NIFTY 50 (Tuesday)
    
    Returns:
        str: Expiry date in YYYY-MM-DD format
    
    Examples:
        Monday 16-Dec → Tuesday 17-Dec
        Tuesday 17-Dec (before 3:30 PM) → Tuesday 17-Dec
        Tuesday 17-Dec (after 3:30 PM) → Tuesday 24-Dec
        Wednesday 18-Dec → Tuesday 24-Dec
    """
    return get_next_tuesday()


def get_next_monthly_expiry():
    """
    Get nearest monthly expiry (Last Thursday of month)
    
    Returns:
        str: Expiry date in YYYY-MM-DD format
    """
    today = datetime.now(IST).date()
    
    # Get last day of current month
    if today.month == 12:
        next_month = datetime(today.year + 1, 1, 1)
    else:
        next_month = datetime(today.year, today.month + 1, 1)
    
    last_day = next_month - timedelta(days=1)
    
    # Find last Thursday
    while last_day.weekday() != 3:  # 3 = Thursday
        last_day -= timedelta(days=1)
    
    # If last Thursday already passed, get next month's
    if last_day.date() < today:
        if last_day.month == 12:
            next_next_month = datetime(last_day.year + 1, 1, 1)
        else:
            next_next_month = datetime(last_day.year, last_day.month + 1, 1)
        
        last_day = next_next_month + timedelta(days=31)  # Go to next month
        last_day = datetime(last_day.year, last_day.month, 1) - timedelta(days=1)
        
        while last_day.weekday() != 3:
            last_day -= timedelta(days=1)
    
    return last_day.strftime('%Y-%m-%d')


def format_expiry_display(expiry_date):
    """
    Format expiry date for display
    
    Args:
        expiry_date: Date string in YYYY-MM-DD format
    
    Returns:
        str: Formatted display string
    
    Example:
        "2025-12-17" → "Tuesday, 17-Dec-25 (1 day)"
    """
    try:
        exp_date = datetime.strptime(expiry_date, '%Y-%m-%d')
        today = datetime.now(IST).date()
        
        days_diff = (exp_date.date() - today).days
        
        day_name = exp_date.strftime('%A')
        date_str = exp_date.strftime('%d-%b-%y')
        
        if days_diff == 0:
            days_text = "TODAY"
        elif days_diff == 1:
            days_text = "1 day"
        else:
            days_text = f"{days_diff} days"
        
        return f"{day_name}, {date_str} ({days_text})"
    
    except Exception:
        return expiry_date


# Test function
if __name__ == "__main__":
    print("="*60)
    print("🔥 Auto Expiry Calculator Test")
    print("="*60)
    
    today = datetime.now(IST)
    print(f"Today: {today.strftime('%A, %d-%b-%Y %I:%M %p IST')}")
    print()
    
    weekly = get_next_weekly_expiry()
    monthly = get_next_monthly_expiry()
    
    print(f"📅 NIFTY 50 Weekly Expiry (Tuesday):")
    print(f"   Date: {weekly}")
    print(f"   Display: {format_expiry_display(weekly)}")
    print()
    
    print(f"📅 NIFTY Monthly Expiry (Last Thursday):")
    print(f"   Date: {monthly}")
    print(f"   Display: {format_expiry_display(monthly)}")
    print()
    
    print("="*60)
