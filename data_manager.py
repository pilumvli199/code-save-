"""
Data Manager - Upstox API Integration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fetches: Option Chain, Spot Price, Futures Price
Tracks: OI History, Price History
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from collections import deque
from config import *
from utils import *

logger = logging.getLogger("NiftyBot.DataManager")

class DataManager:
    """Manages all data fetching and storage"""
    
    def __init__(self):
        self.access_token = UPSTOX_ACCESS_TOKEN
        self.base_url = "https://api.upstox.com/v2"
        
        # Auto-detect futures symbol if not set
        if FUTURES_SYMBOL:
            self.futures_symbol = FUTURES_SYMBOL
        else:
            self.futures_symbol = get_futures_symbol()
            logger.info(f"📅 Auto-detected Futures: {self.futures_symbol}")
        
        # Data storage
        self.oi_history = deque(maxlen=60)  # Keep 60 data points
        self.price_history = deque(maxlen=60)
        self.option_chain_cache = None
        self.last_fetch_time = None
    
    async def fetch_spot_price(self):
        """Fetch NIFTY 50 spot price"""
        try:
            # URL encode the symbol (space becomes %20)
            import urllib.parse
            encoded_symbol = urllib.parse.quote(INDEX_SYMBOL)
            
            url = f"{self.base_url}/market-quote/quotes"
            params = {"symbol": encoded_symbol}
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json"
            }
            
            logger.debug(f"Fetching spot with symbol: {encoded_symbol}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    response_text = await response.text()
                    logger.debug(f"Spot API Response: {response.status} - {response_text[:200]}")
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Try to get LTP from response
                        if 'data' in data:
                            # Try both encoded and original symbol
                            if encoded_symbol in data['data']:
                                ltp = data['data'][encoded_symbol]['last_price']
                            elif INDEX_SYMBOL in data['data']:
                                ltp = data['data'][INDEX_SYMBOL]['last_price']
                            else:
                                logger.error(f"Symbol not found in data. Keys: {list(data['data'].keys())}")
                                return None
                            
                            logger.info(f"  ✅ NIFTY Spot: ₹{ltp:.2f}")
                            return ltp
                        else:
                            logger.error(f"No 'data' in response: {data}")
                            return None
                    elif response.status == 401:
                        logger.error("❌ Upstox token expired! Refresh access token!")
                        return None
                    else:
                        logger.error(f"Spot price fetch failed: {response.status} - {response_text}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching spot price: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def fetch_futures_price(self):
        """Fetch NIFTY futures price"""
        try:
            url = f"{self.base_url}/market-quote/quotes"
            params = {"symbol": self.futures_symbol}
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if 'data' in data and self.futures_symbol in data['data']:
                            ltp = data['data'][self.futures_symbol]['last_price']
                            logger.debug(f"Futures price: ₹{ltp:.2f}")
                            return ltp
                        else:
                            logger.error(f"Futures data not found in response")
                            return None
                    elif response.status == 401:
                        logger.error("❌ Upstox token expired!")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"Futures fetch failed: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching futures price: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def fetch_option_chain(self, spot_price):
        """Fetch complete option chain"""
        try:
            expiry = get_nearest_expiry()
            atm_strike = round_to_strike(spot_price)
            
            # Calculate strike range
            min_strike = atm_strike - STRIKES_RANGE
            max_strike = atm_strike + STRIKES_RANGE
            
            logger.info(f"📡 Fetching option chain: ATM={atm_strike}, Range={min_strike}-{max_strike}")
            
            # Build URL (Upstox API format)
            url = f"{self.base_url}/option/chain"
            params = {
                "instrument_key": f"NSE_FO|{SYMBOL}",
                "expiry_date": expiry.strftime("%Y-%m-%d")
            }
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse option chain
                        chain_data = self._parse_option_chain(data, min_strike, max_strike)
                        
                        # Store in history
                        self._store_oi_snapshot(chain_data, spot_price)
                        
                        self.option_chain_cache = chain_data
                        self.last_fetch_time = get_ist_time()
                        
                        logger.info(f"✅ Option chain fetched: {len(chain_data['strikes'])} strikes")
                        return chain_data
                    else:
                        logger.error(f"Option chain fetch failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
            return None
    
    def _parse_option_chain(self, raw_data, min_strike, max_strike):
        """Parse raw option chain data"""
        strikes_data = {}
        
        for item in raw_data.get('data', []):
            strike_price = item['strike_price']
            
            # Filter by strike range
            if strike_price < min_strike or strike_price > max_strike:
                continue
            
            if strike_price not in strikes_data:
                strikes_data[strike_price] = {
                    'strike': strike_price,
                    'CE': {},
                    'PE': {}
                }
            
            # Call data
            if 'call_options' in item:
                ce_data = item['call_options']
                strikes_data[strike_price]['CE'] = {
                    'oi': ce_data.get('oi', 0),
                    'volume': ce_data.get('volume', 0),
                    'ltp': ce_data.get('last_price', 0),
                    'change_oi': ce_data.get('oi_day_high', 0) - ce_data.get('oi_day_low', 0)
                }
            
            # Put data
            if 'put_options' in item:
                pe_data = item['put_options']
                strikes_data[strike_price]['PE'] = {
                    'oi': pe_data.get('oi', 0),
                    'volume': pe_data.get('volume', 0),
                    'ltp': pe_data.get('last_price', 0),
                    'change_oi': pe_data.get('oi_day_high', 0) - pe_data.get('oi_day_low', 0)
                }
        
        # Convert to list and sort
        strikes_list = sorted(strikes_data.values(), key=lambda x: x['strike'])
        
        # Calculate totals
        total_ce_oi = sum(s['CE'].get('oi', 0) for s in strikes_list)
        total_pe_oi = sum(s['PE'].get('oi', 0) for s in strikes_list)
        
        return {
            'strikes': strikes_list,
            'total_ce_oi': total_ce_oi,
            'total_pe_oi': total_pe_oi,
            'pcr': total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0,
            'timestamp': get_ist_time()
        }
    
    def _store_oi_snapshot(self, chain_data, price):
        """Store OI snapshot in history"""
        snapshot = {
            'timestamp': get_ist_time(),
            'price': price,
            'total_ce_oi': chain_data['total_ce_oi'],
            'total_pe_oi': chain_data['total_pe_oi'],
            'pcr': chain_data['pcr'],
            'strikes': chain_data['strikes']
        }
        
        self.oi_history.append(snapshot)
        logger.debug(f"OI snapshot stored: PCR={snapshot['pcr']:.3f}")
    
    def get_oi_history(self, minutes_ago):
        """Get OI data from N minutes ago"""
        if len(self.oi_history) == 0:
            return None
        
        target_time = get_ist_time() - timedelta(minutes=minutes_ago)
        
        # Find closest snapshot
        closest = min(
            self.oi_history,
            key=lambda x: abs((x['timestamp'] - target_time).total_seconds())
        )
        
        # Check if close enough (within 2 minutes)
        time_diff = abs((closest['timestamp'] - target_time).total_seconds())
        if time_diff > 120:  # More than 2 minutes off
            return None
        
        return closest
    
    def get_oi_change(self, minutes_ago):
        """Calculate OI change from N minutes ago"""
        if len(self.oi_history) < 2:
            return None, None
        
        old_data = self.get_oi_history(minutes_ago)
        current_data = self.oi_history[-1]
        
        if not old_data:
            return None, None
        
        ce_change = calculate_percentage_change(
            old_data['total_ce_oi'],
            current_data['total_ce_oi']
        )
        
        pe_change = calculate_percentage_change(
            old_data['total_pe_oi'],
            current_data['total_pe_oi']
        )
        
        return ce_change, pe_change
    
    def get_price_change(self, minutes_ago):
        """Get price change from N minutes ago"""
        if len(self.oi_history) < 2:
            return None
        
        old_data = self.get_oi_history(minutes_ago)
        current_data = self.oi_history[-1]
        
        if not old_data:
            return None
        
        return current_data['price'] - old_data['price']
    
    def get_status(self):
        """Get data manager status"""
        return {
            'history_count': len(self.oi_history),
            'last_fetch': self.last_fetch_time,
            'has_data': len(self.oi_history) >= MIN_HISTORY_FOR_SIGNAL
        }
