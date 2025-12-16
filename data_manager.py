"""
Data Manager v7.0: COMPREHENSIVE FIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆕 FIXED:
- InMemoryOITracker: 20 → 35 scans (30m support)
- Added 30m comparison method
- Improved tolerance for data lookup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import aiohttp
import json
import time as time_module
from datetime import datetime, timedelta
from urllib.parse import quote
import pandas as pd

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from config import *
from utils import IST, setup_logger

logger = setup_logger("data_manager")

MEMORY_TTL_SECONDS = MEMORY_TTL_HOURS * 3600


# ==================== Upstox Client ====================
class UpstoxClient:
    """Upstox API V2 Client with MONTHLY futures detection"""
    
    def __init__(self):
        self.session = None
        self._rate_limit_delay = 0.1
        self._last_request = 0
        
        self.spot_key = None
        self.index_key = None
        self.futures_key = None
        self.futures_expiry = None
        self.futures_symbol = None
    
    async def initialize(self):
        """Initialize session and detect instruments"""
        self.session = aiohttp.ClientSession()
        success = await self.detect_instruments()
        return success
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        await self.detect_instruments()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {UPSTOX_ACCESS_TOKEN}',
            'Accept': 'application/json'
        }
    
    async def _rate_limit(self):
        elapsed = asyncio.get_event_loop().time() - self._last_request
        if elapsed < self._rate_limit_delay:
            await asyncio.sleep(self._rate_limit_delay - elapsed)
        self._last_request = asyncio.get_event_loop().time()
    
    async def _request(self, url, params=None):
        """Make API request with retry"""
        await self._rate_limit()
        
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
                        logger.error(f"❌ API error {resp.status}: {text[:300]}")
                        return None
            
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout (attempt {attempt + 1}/3)")
                if attempt < 2:
                    await asyncio.sleep(2)
                    continue
                return None
            
            except Exception as e:
                logger.error(f"❌ Request failed (attempt {attempt + 1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
                    continue
                return None
        
        return None
    
    async def detect_instruments(self):
        """Auto-detect NIFTY instruments (spot + MONTHLY futures)"""
        logger.info("🔍 Auto-detecting NIFTY instruments...")
        
        try:
            url = UPSTOX_INSTRUMENTS_URL
            
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
                
                if 'NIFTY 50' in name or 'NIFTY 50' in symbol or symbol == 'NIFTY':
                    self.spot_key = instrument.get('instrument_key')
                    self.index_key = self.spot_key
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
                            'days_to_expiry': days_to_expiry,
                            'weekday': expiry_dt.strftime('%A')
                        })
                except:
                    continue
            
            if not all_futures:
                logger.error("❌ No futures contracts found")
                return False
            
            all_futures.sort(key=lambda x: x['expiry'])
            
            monthly_futures = None
            for fut in all_futures:
                if fut['days_to_expiry'] > 10:
                    monthly_futures = fut
                    break
            
            if not monthly_futures:
                monthly_futures = all_futures[0]
                logger.warning(f"⚠️ Using nearest futures")
            
            self.futures_key = monthly_futures['key']
            self.futures_expiry = monthly_futures['expiry']
            self.futures_symbol = monthly_futures['symbol']
            
            logger.info(f"✅ Futures (MONTHLY): {monthly_futures['symbol']}")
            logger.info(f"   Expiry: {monthly_futures['expiry'].strftime('%Y-%m-%d %A')} ({monthly_futures['days_to_expiry']} days)")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Detection failed: {e}")
            return False
    
    async def get_quote(self, instrument_key):
        """Get market quote"""
        if not instrument_key:
            return None
        
        encoded = quote(instrument_key, safe='')
        url = f"{UPSTOX_QUOTE_URL}?symbol={encoded}"
        
        data = await self._request(url)
        
        if not data or 'data' not in data:
            return None
        
        quotes = data['data']
        
        if instrument_key in quotes:
            return quotes[instrument_key]
        
        alt_key = instrument_key.replace('|', ':')
        if alt_key in quotes:
            return quotes[alt_key]
        
        segment = instrument_key.split('|')[0] if '|' in instrument_key else instrument_key.split(':')[0]
        for key in quotes.keys():
            if key.startswith(segment):
                return quotes[key]
        
        logger.error(f"❌ Instrument not found in: {list(quotes.keys())[:3]}")
        return None
    
    async def get_candles(self, instrument_key, interval='1minute'):
        """Get historical candles"""
        if not instrument_key:
            return None
        
        encoded = quote(instrument_key, safe='')
        url = f"{UPSTOX_HISTORICAL_URL}/intraday/{encoded}/{interval}"
        
        data = await self._request(url)
        
        if not data or 'data' not in data:
            return None
        
        return data['data']
    
    async def get_option_chain(self, instrument_key, expiry_date):
        """Get option chain"""
        if not instrument_key:
            return None
        
        encoded = quote(instrument_key, safe='')
        url = f"{UPSTOX_OPTION_CHAIN_URL}?instrument_key={encoded}&expiry_date={expiry_date}"
        
        try:
            data = await self._request(url)
            
            if not data:
                logger.error("❌ Option chain API returned None")
                return None
            
            if 'data' not in data:
                logger.error(f"❌ No 'data' key. Keys: {list(data.keys())}")
                return None
            
            return data['data']
        
        except Exception as e:
            logger.error(f"❌ Option chain error: {e}", exc_info=True)
            return None


# ==================== In-Memory OI Tracker ====================
class InMemoryOITracker:
    """
    🆕 UPGRADED: In-Memory OI History Tracker with 30m support
    
    Changes:
    - 20 → 35 scans (35 minutes of history)
    - Better tolerance for data lookup (±5 min)
    - Support for 30m comparison
    """
    
    def __init__(self):
        self.history = []
        self.max_history = OI_MEMORY_SCANS  # 🔧 FIX: Was 20, now 35
        logger.info(f"💾 In-Memory OI Tracker initialized ({self.max_history} scans = 30m+ support)")
    
    def save_snapshot(self, total_ce, total_pe, atm_strike, atm_ce_oi, atm_pe_oi):
        """Save current OI snapshot"""
        now = datetime.now(IST).replace(second=0, microsecond=0)
        
        snapshot = {
            'timestamp': now,
            'total_ce': total_ce,
            'total_pe': total_pe,
            'atm_strike': atm_strike,
            'atm_ce': atm_ce_oi,
            'atm_pe': atm_pe_oi
        }
        
        self.history.append(snapshot)
        
        # Keep only last max_history scans
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        logger.debug(f"💾 Saved snapshot #{len(self.history)}/{self.max_history}: ATM {atm_strike}, Total CE={total_ce:,}, PE={total_pe:,}")
    
    def get_comparison(self, minutes_ago=5):
        """
        🆕 IMPROVED: Get OI from N minutes ago with better tolerance
        
        Now supports: 5m, 15m, 30m comparisons
        Tolerance: ±5 minutes (was ±3)
        
        Returns: (total_ce, total_pe, atm_ce, atm_pe, found)
        """
        if len(self.history) < 2:
            return 0, 0, 0, 0, False
        
        target_time = datetime.now(IST) - timedelta(minutes=minutes_ago)
        target_time = target_time.replace(second=0, microsecond=0)
        
        # 🔧 FIX: Increased tolerance to ±5 minutes (was ±3)
        best_match = None
        min_diff = 999
        
        for snapshot in self.history:
            diff = abs((snapshot['timestamp'] - target_time).total_seconds() / 60)
            if diff < min_diff and diff <= OI_MEMORY_BUFFER:  # Within 5 minutes
                min_diff = diff
                best_match = snapshot
        
        if not best_match:
            # 🆕 DEBUG: Log if no match found
            logger.debug(f"⏳ No {minutes_ago}m data (need {minutes_ago}+ min history)")
            return 0, 0, 0, 0, False
        
        # 🆕 DEBUG: Log match info
        if min_diff > 2:
            logger.debug(f"✅ {minutes_ago}m: Found with {min_diff:.1f}m tolerance")
        
        return (
            best_match['total_ce'],
            best_match['total_pe'],
            best_match['atm_ce'],
            best_match['atm_pe'],
            True
        )
    
    def is_ready(self, minutes=5):
        """Check if we have enough history for N-minute comparison"""
        if len(self.history) < 2:
            return False
        
        elapsed = (datetime.now(IST) - self.history[0]['timestamp']).total_seconds() / 60
        return elapsed >= minutes
    
    def get_status(self):
        """Get tracker status"""
        if not self.history:
            return {
                'scans': 0,
                'oldest': None,
                'newest': None,
                'ready_5m': False,
                'ready_15m': False,
                'ready_30m': False
            }
        
        oldest = self.history[0]['timestamp']
        newest = self.history[-1]['timestamp']
        elapsed = (newest - oldest).total_seconds() / 60
        
        return {
            'scans': len(self.history),
            'oldest': oldest.strftime('%H:%M'),
            'newest': newest.strftime('%H:%M'),
            'elapsed_min': elapsed,
            'ready_5m': self.is_ready(5),
            'ready_15m': self.is_ready(15),
            'ready_30m': self.is_ready(30)
        }


# ==================== Redis Brain ====================
class RedisBrain:
    """Redis/RAM memory manager for price tracking"""
    
    def __init__(self):
        self.client = None
        self.memory = {}
        self.memory_timestamps = {}
        
        self.price_history = []
        self.last_price = None
        self.first_price = None
        self.session_open = None
        
        if REDIS_AVAILABLE and REDIS_URL:
            try:
                self.client = redis.from_url(REDIS_URL, decode_responses=True)
                self.client.ping()
                logger.info(f"✅ Redis connected (TTL: {MEMORY_TTL_HOURS}h)")
            except Exception as e:
                logger.warning(f"⚠️ Redis failed: {e}. Using RAM.")
                self.client = None
        else:
            logger.info(f"💾 RAM mode (TTL: {MEMORY_TTL_HOURS}h)")
    
    def save_price(self, price):
        """Save price snapshot"""
        now = datetime.now(IST).replace(second=0, microsecond=0)
        
        self.price_history.append((now, price))
        
        cutoff = now - timedelta(hours=24)
        self.price_history = [(t, p) for t, p in self.price_history if t > cutoff]
        
        self.last_price = price
        if self.first_price is None:
            self.first_price = price
            self.session_open = price
            logger.info(f"📍 SESSION OPEN: ₹{price:.2f}")
        
        key = f"nifty:price:{now.strftime('%Y%m%d_%H%M')}"
        value = json.dumps({'price': price, 'timestamp': now.isoformat()})
        
        if self.client:
            try:
                self.client.setex(key, MEMORY_TTL_SECONDS, value)
            except:
                self.memory[key] = value
                self.memory_timestamps[key] = time_module.time()
        else:
            self.memory[key] = value
            self.memory_timestamps[key] = time_module.time()
    
    def get_price_change(self, current_price, minutes_ago=5):
        """Get price change % from N minutes ago"""
        if not current_price:
            return 0.0, False
        
        target = datetime.now(IST) - timedelta(minutes=minutes_ago)
        target = target.replace(second=0, microsecond=0)
        
        key = f"nifty:price:{target.strftime('%Y%m%d_%H%M')}"
        
        past_str = None
        if self.client:
            try:
                past_str = self.client.get(key)
            except:
                pass
        
        if not past_str:
            past_str = self.memory.get(key)
        
        # Try tolerance ±2 minutes
        if not past_str:
            for offset in [-1, 1, -2, 2]:
                alt = target + timedelta(minutes=offset)
                alt_key = f"nifty:price:{alt.strftime('%Y%m%d_%H%M')}"
                
                if self.client:
                    try:
                        past_str = self.client.get(alt_key)
                        if past_str:
                            break
                    except:
                        pass
                
                if not past_str:
                    past_str = self.memory.get(alt_key)
                    if past_str:
                        break
        
        if not past_str:
            return 0.0, False
        
        try:
            past = json.loads(past_str)
            past_price = past.get('price', 0)
            
            if past_price == 0:
                return 0.0, False
            
            change_pct = ((current_price - past_price) / past_price) * 100
            return round(change_pct, 2), True
        
        except Exception as e:
            logger.error(f"❌ Price parse error: {e}")
            return 0.0, False
    
    def _cleanup(self):
        """Clean expired RAM entries"""
        if not self.memory:
            return
        now = time_module.time()
        expired = [k for k, ts in self.memory_timestamps.items() 
                  if now - ts > MEMORY_TTL_SECONDS]
        for key in expired:
            self.memory.pop(key, None)
            self.memory_timestamps.pop(key, None)
        
        if expired:
            logger.info(f"🧹 Cleaned {len(expired)} expired entries")


# ==================== Data Fetcher ====================
class DataFetcher:
    """High-level data fetching"""
    
    def __init__(self, client):
        self.client = client
    
    async def fetch_spot(self):
        """Fetch spot price"""
        try:
            if not self.client.spot_key:
                logger.error("❌ Spot key missing")
                return None
            
            data = await self.client.get_quote(self.client.spot_key)
            
            if not data:
                return None
            
            ltp = data.get('last_price')
            if not ltp:
                logger.error(f"❌ No 'last_price'. Keys: {list(data.keys())}")
                return None
            
            return float(ltp)
            
        except Exception as e:
            logger.error(f"❌ Spot error: {e}")
            return None
    
    async def fetch_futures_candles(self):
        """Fetch MONTHLY futures candles"""
        try:
            if not self.client.futures_key:
                return None
            
            data = await self.client.get_candles(self.client.futures_key, '1minute')
            
            if not data or 'candles' not in data:
                logger.warning("❌ No candle data")
                return None
            
            candles = data['candles']
            if not candles or len(candles) == 0:
                logger.warning("❌ Empty candles array")
                return None
            
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            return df
        
        except Exception as e:
            logger.error(f"❌ Futures candles error: {e}", exc_info=True)
            return None
    
    async def fetch_futures_ltp(self):
        """Fetch MONTHLY futures LIVE price"""
        try:
            if not self.client.futures_key:
                logger.error("❌ Futures key missing")
                return None
            
            data = await self.client.get_quote(self.client.futures_key)
            
            if not data:
                logger.error("❌ Futures quote returned None")
                return None
            
            ltp = data.get('last_price')
            if not ltp:
                logger.error(f"❌ No 'last_price'. Keys: {list(data.keys())}")
                return None
            
            return float(ltp)
            
        except Exception as e:
            logger.error(f"❌ Futures LTP error: {e}")
            return None
    
    async def fetch_option_chain(self, spot_price):
        """Fetch WEEKLY option chain - 11 strikes"""
        try:
            if not self.client.index_key:
                return None
            
            expiry = get_next_weekly_expiry()
            atm = calculate_atm_strike(spot_price)
            min_strike, max_strike = get_strike_range_fetch(atm)
            
            logger.info(f"📡 Fetching: Expiry={expiry}, ATM={atm}, Range={min_strike}-{max_strike}")
            
            data = await self.client.get_option_chain(self.client.index_key, expiry)
            
            if not data:
                return None
            
            strike_data = {}
            
            # Parse response
            if isinstance(data, list):
                for item in data:
                    strike = item.get('strike_price') or item.get('strike')
                    if not strike:
                        continue
                    
                    strike = float(strike)
                    if strike < min_strike or strike > max_strike:
                        continue
                    
                    ce_data = item.get('call_options', {}) or item.get('CE', {})
                    pe_data = item.get('put_options', {}) or item.get('PE', {})
                    
                    ce_market = ce_data.get('market_data', {})
                    pe_market = pe_data.get('market_data', {})
                    
                    strike_data[strike] = {
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
                    if strike < min_strike or strike > max_strike:
                        continue
                    
                    ce_data = item.get('call_options', {}) or item.get('CE', {})
                    pe_data = item.get('put_options', {}) or item.get('PE', {})
                    
                    ce_market = ce_data.get('market_data', {})
                    pe_market = pe_data.get('market_data', {})
                    
                    strike_data[strike] = {
                        'ce_oi': float(ce_market.get('oi') or 0),
                        'pe_oi': float(pe_market.get('oi') or 0),
                        'ce_vol': float(ce_market.get('volume') or 0),
                        'pe_vol': float(pe_market.get('volume') or 0),
                        'ce_ltp': float(ce_market.get('ltp') or 0),
                        'pe_ltp': float(pe_market.get('ltp') or 0)
                    }
            
            if not strike_data:
                logger.error("❌ No strikes parsed!")
                return None
            
            total_oi = sum(d['ce_oi'] + d['pe_oi'] for d in strike_data.values())
            if total_oi == 0:
                logger.error("❌ ALL OI VALUES ARE ZERO!")
                return None
            
            # Calculate totals
            total_ce = sum(d['ce_oi'] for d in strike_data.values())
            total_pe = sum(d['pe_oi'] for d in strike_data.values())
            
            logger.info(f"✅ Parsed {len(strike_data)} strikes (Total OI: CE={total_ce:,.0f}, PE={total_pe:,.0f})")
            
            return strike_data, atm, total_ce, total_pe
        
        except Exception as e:
            logger.error(f"❌ Option chain fetch error: {e}", exc_info=True)
            return None
