"""
Market Analyzers: OI, Volume, Technical, Market Structure
FIXED: VWAP validation strengthened for PE_BUY
"""

import pandas as pd
from datetime import datetime
from config import *
from utils import IST, setup_logger

logger = setup_logger("analyzers")


# ==================== OI Analyzer ====================
class OIAnalyzer:
    """Open Interest analysis WITH PRICE CONTEXT"""
    
    @staticmethod
    def calculate_total_oi(strike_data):
        """Calculate total CE/PE OI (uses ALL 11 strikes)"""
        if not strike_data:
            return 0, 0
        
        total_ce = sum(d.get('ce_oi', 0) for d in strike_data.values())
        total_pe = sum(d.get('pe_oi', 0) for d in strike_data.values())
        
        return total_ce, total_pe
    
    @staticmethod
    def calculate_deep_analysis_oi(strike_data, atm_strike):
        """Calculate CE/PE OI for DEEP ANALYSIS strikes only (5 strikes)"""
        deep_strikes = get_deep_analysis_strikes(atm_strike)
        
        deep_ce = 0
        deep_pe = 0
        
        for strike in deep_strikes:
            if strike in strike_data:
                deep_ce += strike_data[strike].get('ce_oi', 0)
                deep_pe += strike_data[strike].get('pe_oi', 0)
        
        return deep_ce, deep_pe, deep_strikes
    
    @staticmethod
    def calculate_pcr(total_pe, total_ce):
        """Calculate Put-Call Ratio with neutral default"""
        if total_ce == 0:
            if total_pe == 0:
                return 1.0
            else:
                return 10.0
        
        pcr = total_pe / total_ce
        return round(min(pcr, 10.0), 2)
    
    @staticmethod
    def analyze_oi_with_price(ce_5m, ce_15m, pe_5m, pe_15m, price_change_pct):
        """
        🔥 COMPLETE OI Analysis with PRICE direction
        
        Detects 6 scenarios:
        1. CE Long Buildup (STRONG BULLISH)
        2. CE Short Covering (WEAK BULLISH)
        3. CE Long Unwinding (WEAK BEARISH)
        4. PE Short Buildup (STRONG BEARISH)
        5. PE Short Covering (WEAK BEARISH)
        6. PE Long Unwinding (WEAK BULLISH)
        """
        
        # Thresholds
        OI_BUILDUP_THRESHOLD = 3.0
        OI_UNWINDING_THRESHOLD = -5.0
        STRONG_BUILDUP = 7.0
        STRONG_UNWINDING = -8.0
        PRICE_UP = 0.15
        PRICE_DOWN = -0.15
        
        result = {
            'ce_scenario': None,
            'pe_scenario': None,
            'ce_signal': 'NEUTRAL',
            'pe_signal': 'NEUTRAL',
            'ce_strength': 'none',
            'pe_strength': 'none',
            'primary_direction': 'NEUTRAL',
            'confidence_boost': 0,
            'details': {}
        }
        
        # ━━━━━━━━━━━━ CE ANALYSIS ━━━━━━━━━━━━
        
        # Scenario 1: CE LONG BUILDUP
        if (ce_5m > OI_BUILDUP_THRESHOLD and 
            ce_15m > OI_BUILDUP_THRESHOLD and 
            price_change_pct > PRICE_UP):
            
            if ce_15m > STRONG_BUILDUP and ce_5m > STRONG_BUILDUP:
                strength = 'strong'
                confidence = 95
            elif ce_15m > OI_BUILDUP_THRESHOLD * 1.5:
                strength = 'medium'
                confidence = 85
            else:
                strength = 'weak'
                confidence = 75
            
            result['ce_scenario'] = 'LONG_BUILDUP'
            result['ce_signal'] = 'STRONG_BULLISH'
            result['ce_strength'] = strength
            result['confidence_boost'] = confidence - 70
            result['details']['ce'] = {
                'type': 'Fresh Call Buying',
                'meaning': 'Bulls entering aggressively',
                'oi_5m': ce_5m,
                'oi_15m': ce_15m,
                'price_move': price_change_pct,
                'action': 'BUY_CALL_HIGH_CONFIDENCE'
            }
        
        # Scenario 2: CE SHORT COVERING
        elif (ce_5m < OI_UNWINDING_THRESHOLD and 
              ce_15m < OI_UNWINDING_THRESHOLD and 
              price_change_pct > PRICE_UP):
            
            if ce_15m < STRONG_UNWINDING:
                strength = 'medium'
                confidence = 65
            else:
                strength = 'weak'
                confidence = 55
            
            result['ce_scenario'] = 'SHORT_COVERING'
            result['ce_signal'] = 'WEAK_BULLISH'
            result['ce_strength'] = strength
            result['confidence_boost'] = -10
            result['details']['ce'] = {
                'type': 'Call Unwinding (Short Covering)',
                'meaning': 'Bears exiting, NOT fresh buying',
                'oi_5m': ce_5m,
                'oi_15m': ce_15m,
                'price_move': price_change_pct,
                'action': 'WAIT_OR_SKIP',
                'warning': '⚠️ Temporary bounce, not sustainable'
            }
        
        # Scenario 3: CE LONG UNWINDING
        elif (ce_5m < OI_UNWINDING_THRESHOLD and 
              ce_15m < OI_UNWINDING_THRESHOLD and 
              price_change_pct < PRICE_DOWN):
            
            if ce_15m < STRONG_UNWINDING:
                strength = 'medium'
                confidence = 70
            else:
                strength = 'weak'
                confidence = 60
            
            result['ce_scenario'] = 'LONG_UNWINDING'
            result['ce_signal'] = 'WEAK_BEARISH'
            result['ce_strength'] = strength
            result['details']['ce'] = {
                'type': 'Call Unwinding (Long Exit)',
                'meaning': 'Bulls booking profit',
                'oi_5m': ce_5m,
                'oi_15m': ce_15m,
                'price_move': price_change_pct,
                'action': 'AVOID_CALL',
                'warning': '⚠️ Profit booking'
            }
        
        # ━━━━━━━━━━━━ PE ANALYSIS ━━━━━━━━━━━━
        
        # Scenario 4: PE SHORT BUILDUP
        if (pe_5m > OI_BUILDUP_THRESHOLD and 
            pe_15m > OI_BUILDUP_THRESHOLD and 
            price_change_pct < PRICE_DOWN):
            
            if pe_15m > STRONG_BUILDUP and pe_5m > STRONG_BUILDUP:
                strength = 'strong'
                confidence = 95
            elif pe_15m > OI_BUILDUP_THRESHOLD * 1.5:
                strength = 'medium'
                confidence = 85
            else:
                strength = 'weak'
                confidence = 75
            
            result['pe_scenario'] = 'SHORT_BUILDUP'
            result['pe_signal'] = 'STRONG_BEARISH'
            result['pe_strength'] = strength
            result['confidence_boost'] = max(result['confidence_boost'], confidence - 70)
            result['details']['pe'] = {
                'type': 'Fresh Put Buying',
                'meaning': 'Bears entering aggressively',
                'oi_5m': pe_5m,
                'oi_15m': pe_15m,
                'price_move': price_change_pct,
                'action': 'BUY_PUT_HIGH_CONFIDENCE'
            }
        
        # Scenario 5: PE SHORT COVERING
        elif (pe_5m < OI_UNWINDING_THRESHOLD and 
              pe_15m < OI_UNWINDING_THRESHOLD and 
              price_change_pct < PRICE_DOWN):
            
            if pe_15m < STRONG_UNWINDING:
                strength = 'medium'
                confidence = 65
            else:
                strength = 'weak'
                confidence = 55
            
            result['pe_scenario'] = 'SHORT_COVERING'
            result['pe_signal'] = 'WEAK_BEARISH'
            result['pe_strength'] = strength
            result['confidence_boost'] = min(result['confidence_boost'], -10)
            result['details']['pe'] = {
                'type': 'Put Unwinding (Short Covering)',
                'meaning': 'Bulls exiting puts',
                'oi_5m': pe_5m,
                'oi_15m': pe_15m,
                'price_move': price_change_pct,
                'action': 'WAIT_OR_SKIP',
                'warning': '⚠️ Temporary dip'
            }
        
        # Scenario 6: PE LONG UNWINDING
        elif (pe_5m < OI_UNWINDING_THRESHOLD and 
              pe_15m < OI_UNWINDING_THRESHOLD and 
              price_change_pct > PRICE_UP):
            
            if pe_15m < STRONG_UNWINDING:
                strength = 'medium'
                confidence = 70
            else:
                strength = 'weak'
                confidence = 60
            
            result['pe_scenario'] = 'LONG_UNWINDING'
            result['pe_signal'] = 'WEAK_BULLISH'
            result['pe_strength'] = strength
            result['details']['pe'] = {
                'type': 'Put Unwinding (Long Exit)',
                'meaning': 'Bears booking profit',
                'oi_5m': pe_5m,
                'oi_15m': pe_15m,
                'price_move': price_change_pct,
                'action': 'AVOID_PUT',
                'warning': '⚠️ Bear profit booking'
            }
        
        # Determine Primary Direction
        ce_bullish = result['ce_signal'] in ['STRONG_BULLISH', 'WEAK_BULLISH']
        pe_bullish = result['pe_signal'] in ['STRONG_BULLISH', 'WEAK_BULLISH']
        ce_bearish = result['ce_signal'] in ['STRONG_BEARISH', 'WEAK_BEARISH']
        pe_bearish = result['pe_signal'] in ['STRONG_BEARISH', 'WEAK_BEARISH']
        
        # Confluence check
        if ce_bullish and pe_bullish:
            result['primary_direction'] = 'STRONG_BULLISH'
            result['confidence_boost'] += 15
        elif ce_bearish and pe_bearish:
            result['primary_direction'] = 'STRONG_BEARISH'
            result['confidence_boost'] += 15
        elif 'STRONG_BULLISH' in [result['ce_signal'], result['pe_signal']]:
            result['primary_direction'] = 'BULLISH'
        elif 'STRONG_BEARISH' in [result['ce_signal'], result['pe_signal']]:
            result['primary_direction'] = 'BEARISH'
        else:
            result['primary_direction'] = 'NEUTRAL'
        
        return result
    
    @staticmethod
    def detect_unwinding(ce_5m, ce_15m, pe_5m, pe_15m):
        """LEGACY - kept for backward compatibility"""
        ce_unwinding = (ce_15m < -MIN_OI_15M_FOR_ENTRY and ce_5m < -MIN_OI_5M_FOR_ENTRY)
        
        if ce_15m < -STRONG_OI_15M_THRESHOLD and ce_5m < -STRONG_OI_5M_THRESHOLD:
            ce_strength = 'strong'
        elif ce_15m < -MIN_OI_15M_FOR_ENTRY and ce_5m < -MIN_OI_5M_FOR_ENTRY:
            ce_strength = 'medium'
        else:
            ce_strength = 'weak'
        
        pe_unwinding = (pe_15m < -MIN_OI_15M_FOR_ENTRY and pe_5m < -MIN_OI_5M_FOR_ENTRY)
        
        if pe_15m < -STRONG_OI_15M_THRESHOLD and pe_5m < -STRONG_OI_5M_THRESHOLD:
            pe_strength = 'strong'
        elif pe_15m < -MIN_OI_15M_FOR_ENTRY and pe_5m < -MIN_OI_5M_FOR_ENTRY:
            pe_strength = 'medium'
        else:
            pe_strength = 'weak'
        
        multi_tf = (ce_5m < -2.0 and ce_15m < -3.0) or (pe_5m < -2.0 and pe_15m < -3.0)
        
        return {
            'ce_unwinding': ce_unwinding,
            'pe_unwinding': pe_unwinding,
            'ce_strength': ce_strength,
            'pe_strength': pe_strength,
            'multi_timeframe': multi_tf
        }
    
    @staticmethod
    def get_atm_data(strike_data, atm_strike):
        """Get ATM strike data"""
        return strike_data.get(atm_strike, {
            'ce_oi': 0, 'pe_oi': 0,
            'ce_vol': 0, 'pe_vol': 0,
            'ce_ltp': 0, 'pe_ltp': 0
        })
    
    @staticmethod
    def check_oi_reversal(signal_type, oi_changes_history, threshold=EXIT_OI_REVERSAL_THRESHOLD):
        """Check OI reversal with sustained building"""
        if not oi_changes_history or len(oi_changes_history) < EXIT_OI_CONFIRMATION_CANDLES:
            return False, 'none', 0.0, "Insufficient data"
        
        recent = oi_changes_history[-EXIT_OI_CONFIRMATION_CANDLES:]
        current = recent[-1]
        
        building_count = sum(1 for oi in recent if oi > threshold)
        
        if building_count >= EXIT_OI_CONFIRMATION_CANDLES:
            avg_building = sum(recent) / len(recent)
            strength = 'strong' if avg_building > 5.0 else 'medium'
            return True, strength, avg_building, f"{signal_type} sustained building"
        
        if current > EXIT_OI_SPIKE_THRESHOLD:
            return True, 'spike', current, f"{signal_type} spike: {current:.1f}%"
        
        return False, 'none', current, f"{signal_type} OI: {current:.1f}% (not sustained)"


# ==================== Volume Analyzer ====================
class VolumeAnalyzer:
    """Volume and order flow analysis"""
    
    @staticmethod
    def calculate_total_volume(strike_data):
        """Calculate total CE/PE volume"""
        if not strike_data:
            return 0, 0
        
        ce_vol = sum(d.get('ce_vol', 0) for d in strike_data.values())
        pe_vol = sum(d.get('pe_vol', 0) for d in strike_data.values())
        return ce_vol, pe_vol
    
    @staticmethod
    def detect_volume_spike(current, avg):
        """Detect volume spike"""
        if avg == 0:
            return False, 0.0
        ratio = current / avg
        return ratio >= VOL_SPIKE_MULTIPLIER, round(ratio, 2)
    
    @staticmethod
    def calculate_order_flow(strike_data):
        """Calculate order flow ratio"""
        ce_vol, pe_vol = VolumeAnalyzer.calculate_total_volume(strike_data)
        
        if ce_vol == 0 and pe_vol == 0:
            return 1.0
        elif pe_vol == 0:
            return 5.0
        elif ce_vol == 0:
            return 0.2
        
        ratio = ce_vol / pe_vol
        return round(max(0.2, min(ratio, 5.0)), 2)
    
    @staticmethod
    def analyze_volume_trend(df, periods=5):
        """🔧 FIX: Analyze volume trend with better validation"""
        if df is None or len(df) < periods + 1:
            return {
                'trend': 'unknown',
                'avg_volume': 0,
                'current_volume': 0,
                'ratio': 1.0
            }
        
        try:
            recent = df['volume'].tail(periods + 1)
            avg = recent.iloc[:-1].mean()
            current = recent.iloc[-1]
            
            # Avoid divide by zero
            if avg == 0:
                ratio = 1.0
            else:
                ratio = current / avg
            
            trend = 'increasing' if ratio > 1.3 else 'decreasing' if ratio < 0.7 else 'stable'
            
            return {
                'trend': trend,
                'avg_volume': round(float(avg), 2),
                'current_volume': round(float(current), 2),
                'ratio': round(float(ratio), 2)
            }
        except Exception as e:
            logger.error(f"❌ Volume trend error: {e}")
            return {
                'trend': 'unknown',
                'avg_volume': 0,
                'current_volume': 0,
                'ratio': 1.0
            }


# ==================== Technical Analyzer ====================
class TechnicalAnalyzer:
    """Technical indicators"""
    
    @staticmethod
    def calculate_vwap(df):
        """Calculate VWAP"""
        if df is None or len(df) == 0:
            return None
        
        try:
            df_copy = df.copy()
            df_copy['typical_price'] = (df_copy['high'] + df_copy['low'] + df_copy['close']) / 3
            df_copy['vol_price'] = df_copy['typical_price'] * df_copy['volume']
            df_copy['cum_vol_price'] = df_copy['vol_price'].cumsum()
            df_copy['cum_volume'] = df_copy['volume'].cumsum()
            df_copy['vwap'] = df_copy['cum_vol_price'] / df_copy['cum_volume']
            return round(df_copy['vwap'].iloc[-1], 2)
        except Exception as e:
            logger.error(f"❌ VWAP error: {e}")
            return None
    
    @staticmethod
    def calculate_vwap_distance(price, vwap):
        """Calculate distance from VWAP"""
        if not vwap or not price:
            return 0
        return round(price - vwap, 2)
    
    @staticmethod
    def validate_signal_with_vwap(signal_type, spot, vwap, atr):
        """🔧 FIX #2: STRENGTHENED VWAP validation for PE_BUY"""
        if not vwap or not spot or not atr:
            return False, "Missing VWAP/Price data", 0
        
        distance = spot - vwap
        
        if VWAP_STRICT_MODE:
            buffer = atr * VWAP_DISTANCE_MAX_ATR_MULTIPLE
        else:
            buffer = VWAP_BUFFER
        
        if signal_type == "CE_BUY":
            # CE_BUY: Price should be NEAR or ABOVE VWAP
            if distance < -buffer:
                return False, f"Price {abs(distance):.0f} pts below VWAP", 0
            elif distance > buffer * 3:
                return False, f"Price {distance:.0f} pts above VWAP", 0
            else:
                if distance > 0:
                    score = min(100, 80 + (distance / buffer * 20))
                else:
                    score = max(60, 80 - (abs(distance) / buffer * 20))
                return True, f"VWAP OK: {distance:+.0f} pts", int(score)
        
        elif signal_type == "PE_BUY":
            # 🔧 FIX: PE_BUY MUST be BELOW VWAP (bearish)
            # If price is ABOVE VWAP, it's NOT bearish!
            if distance > 0:
                return False, f"⚠️ Price ABOVE VWAP (+{distance:.0f} pts) - NOT BEARISH!", 0
            
            # Price is below VWAP (correct bearish position)
            if distance > buffer:
                return False, f"Price {distance:.0f} pts above VWAP", 0
            elif distance < -buffer * 3:
                return False, f"Price {abs(distance):.0f} pts below VWAP", 0
            else:
                # Score higher when price is clearly below VWAP
                if distance < 0:
                    score = min(100, 80 + (abs(distance) / buffer * 20))
                else:
                    score = max(60, 80 - (distance / buffer * 20))
                return True, f"VWAP OK: {distance:+.0f} pts", int(score)
        
        return False, "Unknown signal type", 0
    
    @staticmethod
    def calculate_atr(df, period=ATR_PERIOD):
        """Calculate ATR"""
        if df is None or len(df) < period:
            return ATR_FALLBACK
        
        try:
            df_copy = df.copy()
            df_copy['h_l'] = df_copy['high'] - df_copy['low']
            df_copy['h_cp'] = abs(df_copy['high'] - df_copy['close'].shift(1))
            df_copy['l_cp'] = abs(df_copy['low'] - df_copy['close'].shift(1))
            df_copy['tr'] = df_copy[['h_l', 'h_cp', 'l_cp']].max(axis=1)
            atr = df_copy['tr'].rolling(window=period).mean().iloc[-1]
            return round(atr, 2)
        except Exception as e:
            logger.error(f"❌ ATR error: {e}")
            return ATR_FALLBACK
    
    @staticmethod
    def analyze_candle(df):
        """Analyze current candle"""
        if df is None or len(df) == 0:
            return TechnicalAnalyzer._empty_candle()
        
        try:
            candle = df.iloc[-1]
            o, h, l, c = candle['open'], candle['high'], candle['low'], candle['close']
            
            total_size = h - l
            body = abs(c - o)
            upper_wick = h - max(o, c)
            lower_wick = min(o, c) - l
            
            color = 'GREEN' if c > o else 'RED' if c < o else 'DOJI'
            
            rejection = False
            rejection_type = None
            
            if upper_wick > body * EXIT_CANDLE_REJECTION_MULTIPLIER and body > 0:
                rejection = True
                rejection_type = 'upper'
            elif lower_wick > body * EXIT_CANDLE_REJECTION_MULTIPLIER and body > 0:
                rejection = True
                rejection_type = 'lower'
            
            return {
                'color': color,
                'size': round(total_size, 2),
                'body_size': round(body, 2),
                'upper_wick': round(upper_wick, 2),
                'lower_wick': round(lower_wick, 2),
                'rejection': rejection,
                'rejection_type': rejection_type,
                'open': o, 'high': h, 'low': l, 'close': c
            }
        except Exception as e:
            logger.error(f"❌ Candle error: {e}")
            return TechnicalAnalyzer._empty_candle()
    
    @staticmethod
    def detect_momentum(df, periods=3):
        """Detect price momentum"""
        if df is None or len(df) < periods:
            return {
                'direction': 'unknown',
                'strength': 0,
                'consecutive_green': 0,
                'consecutive_red': 0
            }
        
        recent = df.tail(periods)
        green = sum(recent['close'] > recent['open'])
        red = sum(recent['close'] < recent['open'])
        
        direction = 'bullish' if green >= 2 else 'bearish' if red >= 2 else 'sideways'
        strength = green if green >= 2 else red if red >= 2 else 0
        
        return {
            'direction': direction,
            'strength': strength,
            'consecutive_green': green,
            'consecutive_red': red
        }
    
    @staticmethod
    def _empty_candle():
        return {
            'color': 'UNKNOWN', 'size': 0, 'body_size': 0,
            'upper_wick': 0, 'lower_wick': 0,
            'rejection': False, 'rejection_type': None,
            'open': 0, 'high': 0, 'low': 0, 'close': 0
        }


# ==================== Market Analyzer ====================
class MarketAnalyzer:
    """Market structure analysis"""
    
    @staticmethod
    def calculate_max_pain(strike_data, spot_price):
        """Calculate max pain strike"""
        if not strike_data:
            return 0, 0.0
        
        strikes = sorted(strike_data.keys())
        if not strikes:
            return 0, 0.0
        
        max_pain_strike = strikes[len(strikes) // 2]
        min_pain = float('inf')
        
        for test_strike in strikes:
            total_pain = 0.0
            
            for strike, data in strike_data.items():
                ce_oi = data.get('ce_oi', 0)
                pe_oi = data.get('pe_oi', 0)
                
                if test_strike > strike:
                    total_pain += ce_oi * (test_strike - strike)
                if test_strike < strike:
                    total_pain += pe_oi * (strike - test_strike)
            
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_strike
        
        return max_pain_strike, round(min_pain, 2)
    
    @staticmethod
    def detect_gamma_zone():
        """Check if expiry day"""
        try:
            from config import get_next_weekly_expiry
            today = datetime.now(IST).date()
            expiry = datetime.strptime(get_next_weekly_expiry(), '%Y-%m-%d').date()
            return today == expiry
        except:
            return False
    
    @staticmethod
    def calculate_sentiment(pcr, order_flow, ce_change, pe_change):
        """Calculate market sentiment"""
        bullish = 0
        bearish = 0
        
        if pcr > PCR_BULLISH:
            bullish += 1
        elif pcr < PCR_BEARISH:
            bearish += 1
        
        if order_flow < 1.0:
            bullish += 1
        elif order_flow > 1.5:
            bearish += 1
        
        if ce_change < -2.0:
            bullish += 1
        if pe_change < -2.0:
            bearish += 1
        
        if bullish > bearish:
            return "BULLISH"
        elif bearish > bullish:
            return "BEARISH"
        else:
            return "NEUTRAL"
