"""
Alerts - Telegram Notifications
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sends: Trading signals, Status updates
Format: Clean, readable messages
"""

import aiohttp
import asyncio
import logging
from config import *
from utils import *

logger = logging.getLogger("NiftyBot.Alerts")

class TelegramBot:
    """Send alerts via Telegram"""
    
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    async def send_message(self, text, parse_mode='HTML'):
        """Send text message to Telegram"""
        if not SEND_TELEGRAM_ALERTS:
            logger.debug("Telegram alerts disabled")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.debug("Telegram message sent")
                        return True
                    else:
                        logger.error(f"Telegram send failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def send_startup_message(self, futures_symbol=None):
        """Send bot startup notification"""
        if not SEND_STARTUP_MESSAGE:
            return
        
        expiry_date = get_nearest_expiry()
        days_to_expiry = (expiry_date - get_ist_time().date()).days
        
        message = f"""
<b>NIFTY BOT STARTED</b>

Date: {get_ist_time().strftime('%d %b %Y')}
Time: {get_ist_time().strftime('%H:%M:%S IST')}
Version: {BOT_VERSION}

<b>INSTRUMENT:</b>
Index: NIFTY 50
Futures: {futures_symbol or 'Auto-detect'}
Expiry: {expiry_date.strftime('%d %b %Y')} ({NIFTY_EXPIRY_DAY})
Days to Expiry: {days_to_expiry}

<b>STRATEGY:</b>
Min Confidence: {MIN_CONFIDENCE}%
Max Trades/Day: {MAX_TRADES_PER_DAY}
Capital/Trade: Rs.{CAPITAL_PER_TRADE:,}
Stop Loss: {STOP_LOSS_PERCENT}%
Target: {int(TARGET_MULTIPLIER * 100)}%

<b>ANALYSIS:</b>
Scan Interval: {SCAN_INTERVAL_SECONDS // 60} minutes
OI Threshold: {OI_SIGNIFICANT_CHANGE}%
PCR Support: {PCR_STRONG_SUPPORT}
PCR Resistance: {PCR_STRONG_RESISTANCE}

Strategy: OI + PCR + Price
Scenarios: 9 implemented
Status: ACTIVE

<i>Scanning every {SCAN_INTERVAL_SECONDS // 60} minutes...</i>
"""
        await self.send_message(message)
    
    async def send_signal_alert(self, signal):
        """Send trading signal alert"""
        if not ALERT_ON_SIGNAL:
            return
        
        # Icon based on signal type
        if signal.signal_type == SignalType.CE_BUY:
            icon = "CE CALL BUY"
        elif signal.signal_type == SignalType.PE_BUY:
            icon = "PE PUT BUY"
        else:
            return  # Don't send NO_TRADE alerts
        
        # Format analysis data
        analysis = signal.analysis
        
        message = f"""
<b>{icon} SIGNAL</b>

<b>SIGNAL:</b>
Confidence: {signal.confidence}%
Strike: {signal.entry_strike}
Entry: Rs.{signal.entry_price:.2f}
Target: Rs.{signal.target_price:.2f}
Stop Loss: Rs.{signal.stop_loss:.2f}

<b>MARKET:</b>
Nifty: Rs.{analysis['price']:.2f}
Change: {analysis['price_change']:+.1f} pts
PCR: {analysis['pcr']['pcr']:.3f} ({analysis['pcr']['zone']})

<b>OI ANALYSIS:</b>
CE OI: {analysis['oi']['ce_change']:+.1f}%
PE OI: {analysis['oi']['pe_change']:+.1f}%
Total CE: {format_number(analysis['total_ce_oi'])}
Total PE: {format_number(analysis['total_pe_oi'])}

<b>REASON:</b>
"""
        
        # Add reasons
        for reason in signal.reason:
            message += f"{reason}\n"
        
        message += f"""
Time: {signal.timestamp.strftime('%H:%M:%S IST')}

Risk: Rs.{signal.entry_price * STOP_LOSS_PERCENT/100:.2f}
R:R: 1:{TARGET_MULTIPLIER * 100 / STOP_LOSS_PERCENT:.1f}
"""
        
        await self.send_message(message)
    
    async def send_market_status(self, status_text):
        """Send market status update"""
        message = f"""
<b>MARKET STATUS</b>

{status_text}

Time: {get_ist_time().strftime('%H:%M:%S IST')}
"""
        await self.send_message(message)
    
    async def send_daily_summary(self, summary_data):
        """Send end of day summary"""
        if not SEND_DAILY_SUMMARY:
            return
        
        message = f"""
<b>DAILY SUMMARY</b>

Date: {get_ist_time().strftime('%d %b %Y')}

<b>STATS:</b>
Signals: {summary_data.get('signals', 0)}
Trades: {summary_data.get('trades', 0)}
Win Rate: {summary_data.get('win_rate', 0):.1f}%

<b>PERFORMANCE:</b>
P/L: Rs.{summary_data.get('pnl', 0):+,.2f}
Best: Rs.{summary_data.get('best_trade', 0):+,.2f}
Worst: Rs.{summary_data.get('worst_trade', 0):+,.2f}

<b>ACCURACY:</b>
Wins: {summary_data.get('wins', 0)}
Losses: {summary_data.get('losses', 0)}

Market Closed. See you tomorrow!
"""
        await self.send_message(message)
    
    async def send_error_alert(self, error_text):
        """Send error notification"""
        message = f"""
<b>ERROR ALERT</b>

{error_text}

Time: {get_ist_time().strftime('%H:%M:%S IST')}
"""
        await self.send_message(message)


class MessageFormatter:
    """Format messages for different scenarios"""
    
    @staticmethod
    def format_oi_summary(analysis):
        """Format OI analysis summary"""
        return f"""
OI Analysis:
CE: {analysis['oi']['ce_change']:+.1f}% ({analysis['oi']['ce_status']})
PE: {analysis['oi']['pe_change']:+.1f}% ({analysis['oi']['pe_status']})
-> {analysis['oi']['interpretation']}
"""
    
    @staticmethod
    def format_pcr_summary(analysis):
        """Format PCR analysis summary"""
        pcr = analysis['pcr']
        return f"""
PCR: {pcr['pcr']:.3f}
Zone: {pcr['zone']}
Bias: {pcr['bias']} ({pcr['strength']})
"""
    
    @staticmethod
    def format_price_summary(analysis):
        """Format price movement summary"""
        return f"""
Price: Rs.{analysis['price']:.2f}
Change: {analysis['price_change']:+.1f} pts
"""
