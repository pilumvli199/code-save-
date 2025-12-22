"""
Data Manager - NIFTY Bot Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Based on: v7.0 Comprehensive Fix
Modified for: ±2 ATM strikes focus (5 strikes total)
"""

import asyncio
import aiohttp
import json
import time as time_module
from datetime import datetime, timedelta
from urllib.parse import quote
from collections import deque

from config import *
from utils import *

logger = logging.getLogger("NiftyBot.DataManager")


class UpstoxClient:
    """Upstox API V2 Client"""
    
    def __init__(self):
        self.session = None
        self.spot_key = None
        self.futures_key = None
        self.futures_symbol = None
    
    async def initialize(self):
        """Initialize and detect instruments"""
        self.session = aiohttp.ClientSession()
        success = await self.detect_instruments()
        return success
    
    async def close(self):
        """Close session"""
        if self.session:
            await self.session.close()
    
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {UPSTOX_ACCESS_TOKEN}',
            'Accept': 'application/json'
        }
    
    async def _request(self, url, params=None):
        """Make API request with retry"""
        for attempt in range(3):
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with self.session.get(url, headers=self._get_headers(), 
                                           params=params, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        logger.warning(f"⚠️ Rate limit, retry {attempt+1}/3")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    else:
                        text = await resp.text()
                        logger.error(f"❌ API error {resp.status}: {text[:200]}")
                        return None
            
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout (attempt {attempt + 1}/3)")
                if attempt < 2:
                    await asyncio.sleep(2)
                return None
            
            except Exception as e:
                logger.error(f"❌ Request failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
                return None
        
        return None
    
    async def detect_instruments(self):
        """Auto-detect NIFTY instruments"""
        logger.info("🔍 Auto-detecting NIFTY instruments...")
        
        try:
            url = "https://api.upstox.com/v2/market-quote/instruments"
            
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    logger.error(f"❌ Instruments fetch failed: {resp.status}")
                    return False
                
                import gzip
                content = await resp.read()
                json_text = gzip.decompress(content).decode('utf-8')
                instruments = json.loads(json_text)
            
            # Find NIFTY spot
            for instrument in instruments:
                if instrument.get('segment') != 'NSE_INDEX':
                    continue
                
                name = instrument.get('name', '').upper()
                symbol = instrument.get('trading_symbol', '').upper()
                
                if 'NIFTY' in name or 'NIFTY' in symbol:
                    self.spot_key = instrument.get('instrument_key')
                    logger.info(f"✅ Spot: {self.spot_key}")
                    break
            
            if not self.spot_key:
                logger.error("❌ NIFTY spot not found")
                return False
            
            # Find MONTHLY futures
            now = datetime.now(IST)
            all_futures = []
            
            for instrument in instruments:
                if instrument.get('segment') != 'NSE_FO':
                    continue
                if instrument.get('instrument_type') != 'FUT':
                    continue
                if instrument.get('name') != 'NIFTY':
                    continue
                
                expiry_ms = instrument.get('expiry', 0)
                if not expiry_ms:
                    continue
                
                try:
                    expiry_dt = datetime.fromtimestamp(expiry_ms / 1000, tz=IST)
                    
                    if expiry_dt > now:
                        days_to_expiry = (expiry_dt - now).days
                        all_futures.append({
                            'key': instrument.get('instrument_key'),
                            'expiry': expiry_dt,
                            'symbol': instrument.get('trading_symbol', ''),
                            'days_to_expiry': days_to_expiry
                        })
                except:
                    continue
            
            if not all_futures:
                logger.error("❌ No futures found")
                return False
            
            all_futures.sort(key=lambda x: x['expiry'])
            
            # Get monthly (>10 days to expiry)
            monthly = None
            for fut in all_futures:
                if fut['days_to_expiry'] > 10:
                    monthly = fut
                    break
            
            if not monthly:
                monthly = all_futures[0]
            
            self.futures_key = monthly['key']
            self.futures_symbol = monthly['symbol']
            
            logger.info(f"✅ Futures: {monthly['symbol']} ({monthly['days_to_expiry']} days)")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Detection failed: {e}")
            return False
    
    async def get_quote(self, instrument_key):
        """Get market quote"""
        if not instrument_key:
            return None
        
        encoded = quote(instrument_key, safe='')
        url = f"https://api.upstox.com/v2/market-quote/quotes?symbol={encoded}"
        
        data = await self._request(url)
        
        if not data or 'data' not in data:
            return None
        
        quotes = data['data']
        
        # Try direct match
        if instrument_key in quotes:
            return quotes[instrument_key]
        
        # Try with colon
        alt_key = instrument_key.replace('|', ':')
        if alt_key in quotes:
            return quotes[alt_key]
        
        # Try first match
        if quotes:
            return list(quotes.values())[0]
        
        return None
    
    async def get_option_chain(self, expiry_date):
        """Get option chain for WEEKLY expiry"""
        if not self.spot_key:
            return None
        
        encoded = quote(self.spot_key, safe='')
        url = f"https://api.upstox.com/v2/option/chain?instrument_key={encoded}&expiry_date={expiry_date}"
        
        try:
            data = await self._request(url)
            
            if not data or 'data' not in data:
                return None
            
            return data['data']
        
        except Exception as e:
            logger.error(f"❌ Option chain error: {e}")
            return None


class DataManager:
    """Main data manager"""
    
    def __init__(self):
        self.client = UpstoxClient()
        
        # OI History (35 scans = 30min+ history)
        self.oi_history = deque(maxlen=35)
        
        # Price History
        self.price_history = deque(maxlen=60)
        
        self.futures_symbol = None
        self.initialized = False
    
    async def initialize(self):
        """Initialize client"""
        success = await self.client.initialize()
        if success:
            self.futures_symbol = self.client.futures_symbol
            self.initialized = True
            logger.info("✅ DataManager initialized")
        return success
    
    async def close(self):
        """Close connections"""
        await self.client.close()
    
    async def fetch_spot_price(self):
        """Fetch NIFTY spot price"""
        try:
            data = await self.client.get_quote(self.client.spot_key)
            
            if not data:
                return None
            
            ltp = data.get('last_price')
            if not ltp:
                return None
            
            price = float(ltp)
            
            # Save to history
            now = get_ist_time()
            self.price_history.append({'time': now, 'price': price})
            
            return price
            
        except Exception as e:
            logger.error(f"❌ Spot fetch error: {e}")
            return None
    
    async def fetch_futures_price(self):
        """Fetch NIFTY futures price"""
        try:
            data = await self.client.get_quote(self.client.futures_key)
            
            if not data:
                return None
            
            ltp = data.get('last_price')
            if not ltp:
                return None
            
            return float(ltp)
            
        except Exception as e:
            logger.error(f"❌ Futures fetch error: {e}")
            return None
    
    async def fetch_option_chain(self, spot_price):
        """
        Fetch option chain - FOCUSED ON ±2 ATM STRIKES
        
        Returns: dict with option data + totals
        """
        try:
            # Get nearest expiry (Tuesday)
            expiry = get_nearest_expiry()
            expiry_str = expiry.strftime('%Y-%m-%d')
            
            # Calculate ATM
            atm_strike = round_to_strike(spot_price)
            
            # ±2 strikes = 5 strikes total
            strikes_to_fetch = [
                atm_strike - 100,  # ATM - 2
                atm_strike - 50,   # ATM - 1
                atm_strike,        # ATM
                atm_strike + 50,   # ATM + 1
                atm_strike + 100   # ATM + 2
            ]
            
            logger.info(f"📡 Fetching: ATM={atm_strike}, Strikes={strikes_to_fetch[0]}-{strikes_to_fetch[-1]}")
            
            # Fetch option chain
            data = await self.client.get_option_chain(expiry_str)
            
            if not data:
                return None
            
            # Parse option chain
            strikes_data = {}
            
            if isinstance(data, list):
                for item in data:
                    strike = item.get('strike_price') or item.get('strike')
                    if not strike:
                        continue
                    
                    strike = float(strike)
                    
                    # Only keep ±2 ATM strikes
                    if strike not in strikes_to_fetch:
                        continue
                    
                    ce_data = item.get('call_options', {}) or item.get('CE', {})
                    pe_data = item.get('put_options', {}) or item.get('PE', {})
                    
                    ce_market = ce_data.get('market_data', {})
                    pe_market = pe_data.get('market_data', {})
                    
                    strikes_data[strike] = {
                        'ce_oi': float(ce_market.get('oi') or 0),
                        'pe_oi': float(pe_market.get('oi') or 0),
                        'ce_vol': float(ce_market.get('volume') or 0),
                        'pe_vol': float(pe_market.get('volume') or 0),
                        'ce_ltp': float(ce_market.get('ltp') or 0),
                        'pe_ltp': float(pe_market.get('ltp') or 0)
                    }
            
            elif isinstance(data, dict):
                for key, item in data.items():
                    strike = item.get('strike_price') or item.get('strike')
                    if not strike:
                        continue
                    
                    strike = float(strike)
                    
                    if strike not in strikes_to_fetch:
                        continue
                    
                    ce_data = item.get('call_options', {}) or item.get('CE', {})
                    pe_data = item.get('put_options', {}) or item.get('PE', {})
                    
                    ce_market = ce_data.get('market_data', {})
                    pe_market = pe_data.get('market_data', {})
                    
                    strikes_data[strike] = {
                        'ce_oi': float(ce_market.get('oi') or 0),
                        'pe_oi': float(pe_market.get('oi') or 0),
                        'ce_vol': float(ce_market.get('volume') or 0),
                        'pe_vol': float(pe_market.get('volume') or 0),
                        'ce_ltp': float(ce_market.get('ltp') or 0),
                        'pe_ltp': float(pe_market.get('ltp') or 0)
                    }
            
            if not strikes_data:
                logger.error("❌ No strikes parsed!")
                return None
            
            # Calculate totals (from ±2 ATM strikes)
            total_ce_oi = sum(d['ce_oi'] for d in strikes_data.values())
            total_pe_oi = sum(d['pe_oi'] for d in strikes_data.values())
            
            # Get ATM strike data
            atm_data = strikes_data.get(atm_strike, {
                'ce_oi': 0, 'pe_oi': 0, 'ce_vol': 0, 'pe_vol': 0, 
                'ce_ltp': 0, 'pe_ltp': 0
            })
            
            # Calculate PCR
            pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
            
            # Save to history
            now = get_ist_time()
            self.oi_history.append({
                'time': now,
                'total_ce_oi': total_ce_oi,
                'total_pe_oi': total_pe_oi,
                'atm_strike': atm_strike,
                'atm_ce_oi': atm_data['ce_oi'],
                'atm_pe_oi': atm_data['pe_oi'],
                'pcr': pcr
            })
            
            logger.info(f"✅ Parsed {len(strikes_data)} strikes | PCR: {pcr:.3f}")
            logger.info(f"   CE OI: {format_number(total_ce_oi)} | PE OI: {format_number(total_pe_oi)}")
            
            return {
                'strikes': list(strikes_data.keys()),
                'strike_data': strikes_data,
                'atm_strike': atm_strike,
                'total_ce_oi': total_ce_oi,
                'total_pe_oi': total_pe_oi,
                'pcr': pcr
            }
        
        except Exception as e:
            logger.error(f"❌ Option chain error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def get_oi_change(self, minutes_ago=5):
        """Get OI change from N minutes ago"""
        if len(self.oi_history) < 2:
            return None, None
        
        target_time = get_ist_time() - timedelta(minutes=minutes_ago)
        
        # Find closest snapshot
        best_match = None
        min_diff = 999
        
        for snapshot in self.oi_history:
            diff = abs((snapshot['time'] - target_time).total_seconds() / 60)
            if diff < min_diff and diff <= 5:  # Within 5 minutes tolerance
                min_diff = diff
                best_match = snapshot
        
        if not best_match:
            return None, None
        
        current = self.oi_history[-1]
        
        # Calculate % change
        ce_change = 0
        if best_match['total_ce_oi'] > 0:
            ce_change = ((current['total_ce_oi'] - best_match['total_ce_oi']) / 
                        best_match['total_ce_oi']) * 100
        
        pe_change = 0
        if best_match['total_pe_oi'] > 0:
            pe_change = ((current['total_pe_oi'] - best_match['total_pe_oi']) / 
                        best_match['total_pe_oi']) * 100
        
        return ce_change, pe_change
    
    def get_price_change(self, minutes_ago=5):
        """Get price change from N minutes ago"""
        if len(self.price_history) < 2:
            return None
        
        target_time = get_ist_time() - timedelta(minutes=minutes_ago)
        
        # Find closest price
        best_match = None
        min_diff = 999
        
        for snapshot in self.price_history:
            diff = abs((snapshot['time'] - target_time).total_seconds() / 60)
            if diff < min_diff and diff <= 5:
                min_diff = diff
                best_match = snapshot
        
        if not best_match:
            return None
        
        current_price = self.price_history[-1]['price']
        past_price = best_match['price']
        
        change = current_price - past_price
        
        return change
    
    def get_status(self):
        """Get data manager status"""
        oi_scans = len(self.oi_history)
        price_scans = len(self.price_history)
        
        has_data = oi_scans >= 2 and price_scans >= 2
        
        return {
            'has_data': has_data,
            'oi_scans': oi_scans,
            'price_scans': price_scans,
            'futures_symbol': self.futures_symbol
        }
