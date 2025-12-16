"""
Signal Engine v6.0: COMPREHENSIVE FIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ CRITICAL FIXES:
1. Strict VWAP validation (price MUST be correct side)
2. Reversal detection (both ATM unwinding = NO_TRADE)
3. Time filter (no trades after 3:00 PM)
4. Trap detection (one-sided spike = NO_TRADE)

✅ ENHANCEMENTS:
5. PCR bias bands (< 0.7, > 1.3 logic)
6. Raised VWAP threshold (50 → 70)
7. Better confidence scoring
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, time as dt_time
from enum import Enum
from typing import Optional, Tuple

from config import *
from utils import IST, setup_logger
from analyzers import TechnicalAnalyzer

logger = setup_logger("signal_engine")


# ==================== Enhanced Config ====================
# 🔥 FIX #1: Raise VWAP threshold
MIN_VWAP_SCORE = 70  # Was 50 - Now stricter

# 🔥 FIX #2: Time filter
MARKET_CLOSE_BUFFER_MINUTES = 30  # Avoid last 30 min

# 🔥 FIX #3: Reversal detection
REVERSAL_ATM_THRESHOLD = 50  # Both sides > 50% unwinding

# 🔥 FIX #4: Trap detection
TRAP_SPIKE_THRESHOLD = 8  # One side > 8%
TRAP_FLAT_THRESHOLD = 2   # Other side < 2%


# ==================== Signal Models ====================
class SignalType(Enum):
    CE_BUY = "CE_BUY"
    PE_BUY = "PE_BUY"


@dataclass
class Signal:
    """Trading signal data structure"""
    signal_type: SignalType
    timestamp: datetime
    entry_price: float
    target_price: float
    stop_loss: float
    atm_strike: int
    recommended_strike: int
    option_premium: float
    premium_sl: float
    vwap: float
    vwap_distance: float
    vwap_score: int
    atr: float
    oi_5m: float
    oi_15m: float
    oi_strength: str
    atm_ce_change: float
    atm_pe_change: float
    pcr: float
    pcr_bias: str  # 🆕 NEW
    volume_spike: bool
    volume_ratio: float
    order_flow: float
    confidence: int
    primary_checks: int
    bonus_checks: int
    oi_scenario_type: Optional[str] = None


# ==================== Helper Functions ====================
def get_pcr_bias(pcr: float) -> Tuple[str, str, int]:
    """
    🆕 NEW: Get PCR bias and confidence adjustment
    
    Returns:
        (bias, description, confidence_modifier)
    """
    if pcr < 0.7:
        return "OVERHEATED", "Too bullish - Look for PE_BUY at tops", -10
    elif pcr < 0.9:
        return "BULLISH", "Healthy uptrend - CE_BUY on dips", +5
    elif pcr < 1.1:
        return "NEUTRAL", "Range-bound - Wait for breakout", 0
    elif pcr < 1.3:
        return "BEARISH", "Healthy downtrend - PE_BUY on rallies", +5
    else:
        return "OVERSOLD", "Too bearish - Look for CE_BUY at bottoms", -10


def detect_reversal(atm_ce_15m: float, atm_pe_15m: float, has_data: bool) -> Tuple[bool, str]:
    """
    🆕 FIX #2: Detect reversal/exhaustion pattern
    
    When both ATM CE and PE are heavily unwinding = Position exhaustion
    This is NOT a directional signal, it's a reversal warning!
    """
    if not has_data:
        return False, ""
    
    # Both sides unwinding heavily
    if abs(atm_ce_15m) > REVERSAL_ATM_THRESHOLD and abs(atm_pe_15m) > REVERSAL_ATM_THRESHOLD:
        if atm_ce_15m < 0 and atm_pe_15m < 0:
            return True, f"Both ATM unwinding (CE: {atm_ce_15m:.1f}%, PE: {atm_pe_15m:.1f}%)"
    
    return False, ""


def detect_trap(ce_15m: float, pe_15m: float, has_data: bool) -> Tuple[bool, str]:
    """
    🆕 FIX #4: Detect Bull/Bear trap
    
    Bull Trap: CE spike + PE flat = Retail panic, institutions selling
    Bear Trap: PE spike + CE flat = Retail panic, institutions selling
    """
    if not has_data:
        return False, ""
    
    # Bull Trap: CE spike + PE flat
    if abs(ce_15m) > TRAP_SPIKE_THRESHOLD and abs(pe_15m) < TRAP_FLAT_THRESHOLD:
        return True, f"BULL TRAP detected (CE: {ce_15m:.1f}%, PE: {pe_15m:.1f}%)"
    
    # Bear Trap: PE spike + CE flat  
    if abs(pe_15m) > TRAP_SPIKE_THRESHOLD and abs(ce_15m) < TRAP_FLAT_THRESHOLD:
        return True, f"BEAR TRAP detected (CE: {ce_15m:.1f}%, PE: {pe_15m:.1f}%)"
    
    return False, ""


def check_market_timing() -> Tuple[bool, str]:
    """
    🆕 FIX #3: Check if current time is suitable for new positions
    
    Avoid last 30 minutes before market close (3:00-3:30 PM)
    """
    now = datetime.now(IST)
    current_time = now.time()
    
    # Market closes at 3:30 PM
    close_time = dt_time(15, 30)
    buffer_time = dt_time(15, 0)  # Start avoiding at 3:00 PM
    
    if current_time >= buffer_time:
        minutes_left = (datetime.combine(now.date(), close_time) - now).seconds // 60
        return False, f"Too close to market close ({minutes_left} min left)"
    
    return True, ""


# ==================== Signal Generator ====================
class SignalGenerator:
    """Generate entry signals with ALL FIXES + ENHANCEMENTS"""
    
    def __init__(self):
        self.last_signal_time = None
        self.last_signal_type = None
        self.last_signal_strike = None
    
    def generate(self, **kwargs):
        """Generate CE_BUY or PE_BUY signal with comprehensive validation"""
        
        # 🔥 FIX #3: Check market timing FIRST
        timing_ok, timing_reason = check_market_timing()
        if not timing_ok:
            logger.info(f"⏰ {timing_reason} - No new positions")
            return None
        
        # 🔥 FIX #2: Check for reversal pattern
        reversal, reversal_reason = detect_reversal(
            kwargs.get('atm_ce_15m', 0),
            kwargs.get('atm_pe_15m', 0),
            kwargs.get('has_15m_atm', False)
        )
        if reversal:
            logger.warning(f"⚠️ REVERSAL DETECTED: {reversal_reason} - NO_TRADE")
            return None
        
        # 🔥 FIX #4: Check for trap pattern
        trap, trap_reason = detect_trap(
            kwargs.get('ce_total_15m', 0),
            kwargs.get('pe_total_15m', 0),
            kwargs.get('has_15m_total', False)
        )
        if trap:
            logger.warning(f"⚠️ {trap_reason} - NO_TRADE")
            return None
        
        # Try CE_BUY
        ce_signal = self._check_ce_buy(**kwargs)
        if ce_signal:
            return ce_signal
        
        # Try PE_BUY
        pe_signal = self._check_pe_buy(**kwargs)
        return pe_signal
    
    def _check_ce_buy(self, spot_price, futures_price, vwap, vwap_distance, pcr, atr,
                      atm_strike, atm_data, ce_total_5m, pe_total_5m, ce_total_15m, pe_total_15m,
                      atm_ce_5m, atm_pe_5m, atm_ce_15m, atm_pe_15m,
                      has_5m_total, has_15m_total, has_5m_atm, has_15m_atm,
                      volume_spike, volume_ratio, order_flow, candle_data, 
                      gamma_zone, momentum, multi_tf, oi_strength='weak', oi_scenario=None, **kwargs):
        """Check CE_BUY setup with COMPREHENSIVE VALIDATION"""
        
        # 🔥 FIX #1: STRICT VWAP Validation (BLOCKING CHECK)
        vwap_valid, vwap_reason, vwap_score = TechnicalAnalyzer.validate_signal_with_vwap(
            "CE_BUY", futures_price, vwap, atr
        )
        
        # HARD REJECT if price on wrong side of VWAP
        if futures_price <= vwap:
            logger.debug(f"  ❌ CE_BUY HARD REJECT: Entry ₹{futures_price:.2f} <= VWAP ₹{vwap:.2f}")
            return None
        
        # Raise VWAP score threshold
        if vwap_score < MIN_VWAP_SCORE:
            logger.debug(f"  ❌ CE_BUY rejected: VWAP score {vwap_score} < {MIN_VWAP_SCORE}")
            return None
        
        if not vwap_valid:
            logger.debug(f"  ❌ CE_BUY rejected: {vwap_reason}")
            return None
        
        logger.debug(f"  ✅ VWAP check passed: Entry ₹{futures_price:.2f} > VWAP ₹{vwap:.2f} (Score: {vwap_score})")
        
        # 🆕 PCR Bias Check
        pcr_bias, pcr_desc, pcr_modifier = get_pcr_bias(pcr)
        logger.debug(f"  📊 PCR Bias: {pcr_bias} - {pcr_desc}")
        
        # Reject CE_BUY if market OVERHEATED (PCR < 0.7)
        if pcr < 0.7:
            logger.debug(f"  ⚠️ CE_BUY cautious: PCR {pcr:.2f} too low (overheated)")
            # Don't hard reject, but reduce confidence
        
        # 🆕 OI Scenario boost
        oi_scenario_boost = 0
        oi_scenario_type = None
        
        if oi_scenario:
            primary_direction = oi_scenario.get('primary_direction', 'NEUTRAL')
            ce_signal = oi_scenario.get('ce_signal', 'NEUTRAL')
            ce_scenario = oi_scenario.get('ce_scenario')
            
            if 'BULLISH' in primary_direction or 'BULLISH' in ce_signal:
                if 'STRONG' in ce_signal:
                    oi_scenario_boost = 15
                    oi_scenario_type = f"{ce_scenario} (STRONG)"
                else:
                    oi_scenario_boost = 5
                    oi_scenario_type = f"{ce_scenario} (WEAK)"
                
                logger.debug(f"  🔥 OI Scenario: {oi_scenario_type} (+{oi_scenario_boost}%)")
        
        # Primary checks (STRICTER)
        primary_ce = ce_total_15m < -MIN_OI_15M_FOR_ENTRY and ce_total_5m < -MIN_OI_5M_FOR_ENTRY and has_15m_total and has_5m_total
        primary_atm = atm_ce_15m < -ATM_OI_THRESHOLD and has_15m_atm
        primary_vol = volume_spike
        
        primary_passed = sum([primary_ce, primary_atm, primary_vol])
        
        if primary_passed < MIN_PRIMARY_CHECKS:
            logger.debug(f"  ❌ CE_BUY: Only {primary_passed}/{MIN_PRIMARY_CHECKS} primary checks")
            return None
        
        # Secondary checks
        secondary_price = futures_price > vwap
        secondary_green = candle_data.get('color') == 'GREEN'
        
        # Bonus checks
        bonus_5m_strong = ce_total_5m < -STRONG_OI_5M_THRESHOLD and has_5m_total
        bonus_candle = candle_data.get('size', 0) >= MIN_CANDLE_SIZE
        bonus_vwap_above = vwap_distance > 0
        bonus_pcr = pcr > PCR_BULLISH
        bonus_momentum = momentum.get('consecutive_green', 0) >= 2
        bonus_flow = order_flow < 1.0
        bonus_vol_strong = volume_ratio >= VOL_SPIKE_STRONG
        
        bonus_passed = sum([bonus_5m_strong, bonus_candle, bonus_vwap_above, bonus_pcr, 
                           bonus_momentum, bonus_flow, multi_tf, gamma_zone, bonus_vol_strong])
        
        # Calculate confidence (IMPROVED with PCR)
        confidence = 40  # Base
        
        # Primary checks (60 points max)
        if primary_ce: 
            if oi_strength == 'strong':
                confidence += 25
            else:
                confidence += 20
        if primary_atm: confidence += 20
        if primary_vol: confidence += 15
        
        # VWAP score (20 points max)
        confidence += int(vwap_score / 5)
        
        # OI Scenario boost
        confidence += oi_scenario_boost
        
        # PCR modifier
        confidence += pcr_modifier
        
        # Secondary checks
        if secondary_green: confidence += 5
        if secondary_price: confidence += 5
        
        # Bonus checks
        confidence += min(bonus_passed * 2, 15)
        
        confidence = min(confidence, 98)
        
        if confidence < MIN_CONFIDENCE:
            logger.debug(f"  ❌ CE_BUY: Confidence {confidence}% < {MIN_CONFIDENCE}%")
            return None
        
        # Calculate levels
        sl_mult = ATR_SL_GAMMA_MULTIPLIER if gamma_zone else ATR_SL_MULTIPLIER
        entry = futures_price
        target = entry + int(atr * ATR_TARGET_MULTIPLIER)
        sl = entry - int(atr * sl_mult)
        
        premium = atm_data.get('ce_ltp', 150.0)
        premium_sl = premium * (1 - PREMIUM_SL_PERCENT / 100) if USE_PREMIUM_SL else 0
        
        signal = Signal(
            signal_type=SignalType.CE_BUY,
            timestamp=datetime.now(IST),
            entry_price=entry,
            target_price=target,
            stop_loss=sl,
            atm_strike=atm_strike,
            recommended_strike=atm_strike,
            option_premium=premium,
            premium_sl=premium_sl,
            vwap=vwap,
            vwap_distance=vwap_distance,
            vwap_score=vwap_score,
            atr=atr,
            oi_5m=ce_total_5m,
            oi_15m=ce_total_15m,
            oi_strength=oi_strength,
            atm_ce_change=atm_ce_15m,
            atm_pe_change=atm_pe_15m,
            pcr=pcr,
            pcr_bias=pcr_bias,  # 🆕 NEW
            volume_spike=volume_spike,
            volume_ratio=volume_ratio,
            order_flow=order_flow,
            confidence=confidence,
            primary_checks=primary_passed,
            bonus_checks=bonus_passed,
            oi_scenario_type=oi_scenario_type
        )
        
        logger.info(f"  ✅ CE_BUY signal generated!")
        logger.info(f"  Type: CE_BUY")
        logger.info(f"  Entry: ₹{entry:.2f}")
        logger.info(f"  Confidence: {confidence}%")
        logger.info(f"  VWAP Score: {vwap_score}/100 ✅")
        logger.info(f"  PCR Bias: {pcr_bias}")
        logger.info(f"  OI Strength: {oi_strength}")
        
        return signal
    
    def _check_pe_buy(self, spot_price, futures_price, vwap, vwap_distance, pcr, atr,
                      atm_strike, atm_data, ce_total_5m, pe_total_5m, ce_total_15m, pe_total_15m,
                      atm_ce_5m, atm_pe_5m, atm_ce_15m, atm_pe_15m,
                      has_5m_total, has_15m_total, has_5m_atm, has_15m_atm,
                      volume_spike, volume_ratio, order_flow, candle_data, 
                      gamma_zone, momentum, multi_tf, oi_strength='weak', oi_scenario=None, **kwargs):
        """Check PE_BUY setup with COMPREHENSIVE VALIDATION"""
        
        # 🔥 FIX #1: STRICT VWAP Validation
        vwap_valid, vwap_reason, vwap_score = TechnicalAnalyzer.validate_signal_with_vwap(
            "PE_BUY", futures_price, vwap, atr
        )
        
        # HARD REJECT if price on wrong side of VWAP
        if futures_price >= vwap:
            logger.debug(f"  ❌ PE_BUY HARD REJECT: Entry ₹{futures_price:.2f} >= VWAP ₹{vwap:.2f}")
            return None
        
        # Raise VWAP score threshold
        if vwap_score < MIN_VWAP_SCORE:
            logger.debug(f"  ❌ PE_BUY rejected: VWAP score {vwap_score} < {MIN_VWAP_SCORE}")
            return None
        
        if not vwap_valid:
            logger.debug(f"  ❌ PE_BUY rejected: {vwap_reason}")
            return None
        
        logger.debug(f"  ✅ VWAP check passed: Entry ₹{futures_price:.2f} < VWAP ₹{vwap:.2f} (Score: {vwap_score})")
        
        # 🆕 PCR Bias Check
        pcr_bias, pcr_desc, pcr_modifier = get_pcr_bias(pcr)
        logger.debug(f"  📊 PCR Bias: {pcr_bias} - {pcr_desc}")
        
        # Reject PE_BUY if market OVERSOLD (PCR > 1.3)
        if pcr > 1.3:
            logger.debug(f"  ⚠️ PE_BUY cautious: PCR {pcr:.2f} too high (oversold)")
        
        # OI Scenario boost
        oi_scenario_boost = 0
        oi_scenario_type = None
        
        if oi_scenario:
            primary_direction = oi_scenario.get('primary_direction', 'NEUTRAL')
            pe_signal = oi_scenario.get('pe_signal', 'NEUTRAL')
            pe_scenario = oi_scenario.get('pe_scenario')
            
            if 'BEARISH' in primary_direction or 'BEARISH' in pe_signal:
                if 'STRONG' in pe_signal:
                    oi_scenario_boost = 15
                    oi_scenario_type = f"{pe_scenario} (STRONG)"
                else:
                    oi_scenario_boost = 5
                    oi_scenario_type = f"{pe_scenario} (WEAK)"
                
                logger.debug(f"  🔥 OI Scenario: {oi_scenario_type} (+{oi_scenario_boost}%)")
        
        # Primary checks
        primary_pe = pe_total_15m < -MIN_OI_15M_FOR_ENTRY and pe_total_5m < -MIN_OI_5M_FOR_ENTRY and has_15m_total and has_5m_total
        primary_atm = atm_pe_15m < -ATM_OI_THRESHOLD and has_15m_atm
        primary_vol = volume_spike
        
        primary_passed = sum([primary_pe, primary_atm, primary_vol])
        
        if primary_passed < MIN_PRIMARY_CHECKS:
            logger.debug(f"  ❌ PE_BUY: Only {primary_passed}/{MIN_PRIMARY_CHECKS} primary checks")
            return None
        
        # Secondary checks
        secondary_price = futures_price < vwap
        secondary_red = candle_data.get('color') == 'RED'
        
        # Bonus checks
        bonus_5m_strong = pe_total_5m < -STRONG_OI_5M_THRESHOLD and has_5m_total
        bonus_candle = candle_data.get('size', 0) >= MIN_CANDLE_SIZE
        bonus_vwap_below = vwap_distance < 0
        bonus_pcr = pcr < PCR_BEARISH
        bonus_momentum = momentum.get('consecutive_red', 0) >= 2
        bonus_flow = order_flow > 1.0
        bonus_vol_strong = volume_ratio >= VOL_SPIKE_STRONG
        
        bonus_passed = sum([bonus_5m_strong, bonus_candle, bonus_vwap_below, bonus_pcr, 
                           bonus_momentum, bonus_flow, multi_tf, gamma_zone, bonus_vol_strong])
        
        # Calculate confidence
        confidence = 40
        
        if primary_pe:
            if oi_strength == 'strong':
                confidence += 25
            else:
                confidence += 20
        if primary_atm: confidence += 20
        if primary_vol: confidence += 15
        
        confidence += int(vwap_score / 5)
        confidence += oi_scenario_boost
        confidence += pcr_modifier
        
        if secondary_red: confidence += 5
        if secondary_price: confidence += 5
        
        confidence += min(bonus_passed * 2, 15)
        
        confidence = min(confidence, 98)
        
        if confidence < MIN_CONFIDENCE:
            logger.debug(f"  ❌ PE_BUY: Confidence {confidence}% < {MIN_CONFIDENCE}%")
            return None
        
        # Calculate levels
        sl_mult = ATR_SL_GAMMA_MULTIPLIER if gamma_zone else ATR_SL_MULTIPLIER
        entry = futures_price
        target = entry - int(atr * ATR_TARGET_MULTIPLIER)
        sl = entry + int(atr * sl_mult)
        
        premium = atm_data.get('pe_ltp', 150.0)
        premium_sl = premium * (1 - PREMIUM_SL_PERCENT / 100) if USE_PREMIUM_SL else 0
        
        signal = Signal(
            signal_type=SignalType.PE_BUY,
            timestamp=datetime.now(IST),
            entry_price=entry,
            target_price=target,
            stop_loss=sl,
            atm_strike=atm_strike,
            recommended_strike=atm_strike,
            option_premium=premium,
            premium_sl=premium_sl,
            vwap=vwap,
            vwap_distance=vwap_distance,
            vwap_score=vwap_score,
            atr=atr,
            oi_5m=pe_total_5m,
            oi_15m=pe_total_15m,
            oi_strength=oi_strength,
            atm_ce_change=atm_ce_15m,
            atm_pe_change=atm_pe_15m,
            pcr=pcr,
            pcr_bias=pcr_bias,
            volume_spike=volume_spike,
            volume_ratio=volume_ratio,
            order_flow=order_flow,
            confidence=confidence,
            primary_checks=primary_passed,
            bonus_checks=bonus_passed,
            oi_scenario_type=oi_scenario_type
        )
        
        logger.info(f"  ✅ PE_BUY signal generated!")
        logger.info(f"  Type: PE_BUY")
        logger.info(f"  Entry: ₹{entry:.2f}")
        logger.info(f"  Confidence: {confidence}%")
        logger.info(f"  VWAP Score: {vwap_score}/100 ✅")
        logger.info(f"  PCR Bias: {pcr_bias}")
        logger.info(f"  OI Strength: {oi_strength}")
        
        return signal


# Keep SignalValidator class unchanged (no modifications needed)
class SignalValidator:
    """Validate if signal should be executed - prevents re-entry too soon"""
    
    def __init__(self):
        self.last_signal_time = None
        self.last_signal_strike = None
        self.last_signal_type = None
    
    def should_execute(self, signal: Signal) -> tuple[bool, str]:
        """Check if signal should be executed"""
        
        # First signal always valid
        if not self.last_signal_time:
            return True, "First signal"
        
        # Check cooldown period
        time_since_last = (signal.timestamp - self.last_signal_time).total_seconds() / 60
        
        if time_since_last < REENTRY_COOLDOWN_MINUTES:
            return False, f"Cooldown: {REENTRY_COOLDOWN_MINUTES - int(time_since_last)} min left"
        
        # Check same strike
        if (signal.recommended_strike == self.last_signal_strike and 
            str(signal.signal_type) == self.last_signal_type):
            if time_since_last < REENTRY_SAME_STRIKE_MINUTES:
                return False, f"Same strike cooldown: {REENTRY_SAME_STRIKE_MINUTES - int(time_since_last)} min left"
        
        return True, "Validation passed"
    
    def record_signal(self, signal: Signal):
        """Record executed signal"""
        self.last_signal_time = signal.timestamp
        self.last_signal_strike = signal.recommended_strike
        self.last_signal_type = str(signal.signal_type)
