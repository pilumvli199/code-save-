"""
Signal Engine v7.0: COMPREHENSIVE FIX + VELOCITY + OTM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆕 INTEGRATED:
1. OI Velocity patterns in confidence scoring
2. OTM Strike analysis (support/resistance)
3. 30m OI validation
4. All previous fixes (VWAP, reversal, trap, timing)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, time as dt_time
from enum import Enum
from typing import Optional, Tuple

from config import *
from utils import IST, setup_logger
from analyzers import TechnicalAnalyzer, OIAnalyzer

logger = setup_logger("signal_engine")


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
    oi_30m: float  # 🆕 NEW
    oi_strength: str
    atm_ce_change: float
    atm_pe_change: float
    pcr: float
    pcr_bias: str
    volume_spike: bool
    volume_ratio: float
    order_flow: float
    confidence: int
    primary_checks: int
    bonus_checks: int
    oi_scenario_type: Optional[str] = None
    oi_velocity_pattern: Optional[str] = None  # 🆕 NEW
    otm_analysis: Optional[str] = None  # 🆕 NEW
    is_expiry_day: bool = False
    
    def get_rr_ratio(self):
        """Calculate risk-reward ratio"""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.target_price - self.entry_price)
        if risk == 0:
            return 0
        return round(reward / risk, 2)


# ==================== Helper Functions ====================
def get_pcr_bias(pcr: float) -> Tuple[str, str, int]:
    """Get PCR bias and confidence adjustment"""
    if pcr < PCR_OVERHEATED:
        return "OVERHEATED", "Too bullish - Look for PE_BUY at tops", -10
    elif pcr < PCR_BALANCED_BULL:
        return "BULLISH", "Healthy uptrend - CE_BUY on dips", +5
    elif pcr < PCR_NEUTRAL_HIGH:
        return "NEUTRAL", "Range-bound - Wait for breakout", 0
    elif pcr < PCR_BALANCED_BEAR:
        return "BEARISH", "Healthy downtrend - PE_BUY on rallies", +5
    else:
        return "OVERSOLD", "Too bearish - Look for CE_BUY at bottoms", -10


def detect_reversal(atm_ce_15m: float, atm_pe_15m: float, has_data: bool) -> Tuple[bool, str]:
    """Detect reversal/exhaustion pattern"""
    if not has_data:
        return False, ""
    
    # Both sides unwinding heavily
    REVERSAL_THRESHOLD = 5.0  # Both > 5% unwinding
    
    if abs(atm_ce_15m) > REVERSAL_THRESHOLD and abs(atm_pe_15m) > REVERSAL_THRESHOLD:
        if atm_ce_15m < 0 and atm_pe_15m < 0:
            return True, f"Both ATM unwinding (CE: {atm_ce_15m:.1f}%, PE: {atm_pe_15m:.1f}%)"
    
    return False, ""


def detect_trap(ce_15m: float, pe_15m: float, has_data: bool) -> Tuple[bool, str]:
    """Detect Bull/Bear trap"""
    if not has_data:
        return False, ""
    
    TRAP_SPIKE = 8.0
    TRAP_FLAT = 2.0
    
    # Bull Trap: CE spike + PE flat
    if abs(ce_15m) > TRAP_SPIKE and abs(pe_15m) < TRAP_FLAT:
        return True, f"BULL TRAP detected (CE: {ce_15m:.1f}%, PE: {pe_15m:.1f}%)"
    
    # Bear Trap: PE spike + CE flat  
    if abs(pe_15m) > TRAP_SPIKE and abs(ce_15m) < TRAP_FLAT:
        return True, f"BEAR TRAP detected (CE: {ce_15m:.1f}%, PE: {pe_15m:.1f}%)"
    
    return False, ""


def check_market_timing() -> Tuple[bool, str]:
    """Check if current time is suitable for new positions"""
    now = datetime.now(IST)
    current_time = now.time()
    
    close_time = dt_time(15, 30)
    buffer_time = dt_time(15, 0)  # Avoid last 30 min
    
    if current_time >= buffer_time:
        minutes_left = (datetime.combine(now.date(), close_time) - now).seconds // 60
        return False, f"Too close to market close ({minutes_left} min left)"
    
    return True, ""


# ==================== Signal Generator ====================
class SignalGenerator:
    """Generate entry signals with ALL FIXES + VELOCITY + OTM"""
    
    def __init__(self):
        self.last_signal_time = None
        self.last_signal_type = None
        self.last_signal_strike = None
    
    def generate(self, **kwargs):
        """Generate CE_BUY or PE_BUY signal with comprehensive validation"""
        
        # Check market timing FIRST
        timing_ok, timing_reason = check_market_timing()
        if not timing_ok:
            logger.info(f"⏰ {timing_reason} - No new positions")
            return None
        
        # Check for reversal pattern
        reversal, reversal_reason = detect_reversal(
            kwargs.get('atm_ce_15m', 0),
            kwargs.get('atm_pe_15m', 0),
            kwargs.get('has_15m_atm', False)
        )
        if reversal:
            logger.warning(f"⚠️ REVERSAL DETECTED: {reversal_reason} - NO_TRADE")
            return None
        
        # Check for trap pattern
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
                      atm_strike, atm_data, strike_data,
                      ce_total_5m, pe_total_5m, ce_total_15m, pe_total_15m, ce_total_30m, pe_total_30m,
                      atm_ce_5m, atm_pe_5m, atm_ce_15m, atm_pe_15m,
                      has_5m_total, has_15m_total, has_30m_total, has_5m_atm, has_15m_atm,
                      volume_spike, volume_ratio, order_flow, candle_data, 
                      gamma_zone, momentum, multi_tf, oi_strength='weak', oi_scenario=None, **kwargs):
        """Check CE_BUY setup with COMPREHENSIVE VALIDATION + VELOCITY + OTM"""
        
        # ━━━━━━━━━━━━ VWAP VALIDATION (BLOCKING) ━━━━━━━━━━━━
        vwap_valid, vwap_reason, vwap_score = TechnicalAnalyzer.validate_signal_with_vwap(
            "CE_BUY", futures_price, vwap, atr
        )
        
        if futures_price <= vwap:
            logger.debug(f"  ❌ CE_BUY HARD REJECT: Entry ₹{futures_price:.2f} <= VWAP ₹{vwap:.2f}")
            return None
        
        if vwap_score < MIN_VWAP_SCORE:
            logger.debug(f"  ❌ CE_BUY rejected: VWAP score {vwap_score} < {MIN_VWAP_SCORE}")
            return None
        
        if not vwap_valid:
            logger.debug(f"  ❌ CE_BUY rejected: {vwap_reason}")
            return None
        
        logger.debug(f"  ✅ VWAP check passed: Entry ₹{futures_price:.2f} > VWAP ₹{vwap:.2f} (Score: {vwap_score})")
        
        # ━━━━━━━━━━━━ PCR BIAS ━━━━━━━━━━━━
        pcr_bias, pcr_desc, pcr_modifier = get_pcr_bias(pcr)
        logger.debug(f"  📊 PCR Bias: {pcr_bias} - {pcr_desc}")
        
        if pcr < PCR_OVERHEATED:
            logger.debug(f"  ⚠️ CE_BUY cautious: PCR {pcr:.2f} too low (overheated)")
        
        # ━━━━━━━━━━━━ OI VELOCITY ANALYSIS ━━━━━━━━━━━━
        ce_velocity, vel_strength, vel_desc, vel_confidence = OIAnalyzer.classify_oi_velocity(
            ce_total_5m, ce_total_15m, ce_total_30m, has_30m_total, 'CE'
        )
        
        logger.debug(f"  🚀 CE Velocity: {ce_velocity} ({vel_strength}) - {vel_desc}")
        
        # Reject DECELERATION or EXHAUSTION for CE_BUY
        if ce_velocity in ['DECELERATION', 'EXHAUSTION']:
            logger.debug(f"  ❌ CE_BUY rejected: {ce_velocity} pattern (losing momentum)")
            return None
        
        # ━━━━━━━━━━━━ OTM STRIKE ANALYSIS ━━━━━━━━━━━━
        has_support, has_resistance, otm_modifier, otm_details = OIAnalyzer.analyze_otm_levels(
            strike_data, atm_strike, "CE_BUY"
        )
        
        logger.debug(f"  🎯 OTM: {otm_details}")
        
        # ━━━━━━━━━━━━ OI SCENARIO ━━━━━━━━━━━━
        oi_scenario_boost = 0
        oi_scenario_type = None
        
        if oi_scenario:
            primary_direction = oi_scenario.get('primary_direction', 'NEUTRAL')
            ce_signal = oi_scenario.get('ce_signal', 'NEUTRAL')
            ce_scenario = oi_scenario.get('ce_scenario')
            human_name = oi_scenario.get('human_name', '')
            
            if 'BULLISH' in primary_direction or 'BULLISH' in ce_signal:
                if 'STRONG' in ce_signal:
                    oi_scenario_boost = 15
                    oi_scenario_type = f"{human_name} (STRONG)"
                else:
                    oi_scenario_boost = 5
                    oi_scenario_type = f"{human_name} (WEAK)"
                
                logger.debug(f"  🔥 OI Scenario: {oi_scenario_type} (+{oi_scenario_boost}%)")
        
        # ━━━━━━━━━━━━ PRIMARY CHECKS ━━━━━━━━━━━━
        # 🆕 ADD: 30m validation
        primary_ce = (ce_total_15m < -MIN_OI_15M_FOR_ENTRY and 
                     ce_total_5m < -MIN_OI_5M_FOR_ENTRY and 
                     has_15m_total and has_5m_total)
        
        primary_atm = atm_ce_15m < -ATM_OI_THRESHOLD and has_15m_atm
        primary_vol = volume_spike
        
        # 🆕 NEW: 30m confirmation (bonus if available)
        primary_30m_confirm = False
        if has_30m_total and ce_total_30m < -MIN_OI_30M_FOR_ENTRY:
            primary_30m_confirm = True
            logger.debug(f"  ✅ 30m confirmation: CE {ce_total_30m:.1f}%")
        
        primary_passed = sum([primary_ce, primary_atm, primary_vol])
        
        if primary_passed < MIN_PRIMARY_CHECKS:
            logger.debug(f"  ❌ CE_BUY: Only {primary_passed}/{MIN_PRIMARY_CHECKS} primary checks")
            return None
        
        # ━━━━━━━━━━━━ BONUS CHECKS ━━━━━━━━━━━━
        bonus_5m_strong = ce_total_5m < -STRONG_OI_5M_THRESHOLD and has_5m_total
        bonus_candle = candle_data.get('size', 0) >= MIN_CANDLE_SIZE
        bonus_vwap_above = vwap_distance > 0
        bonus_pcr = pcr > PCR_BULLISH
        bonus_momentum = momentum.get('consecutive_green', 0) >= 2
        bonus_flow = order_flow < 1.0
        bonus_vol_strong = volume_ratio >= VOL_SPIKE_STRONG
        bonus_30m = primary_30m_confirm  # 🆕 NEW
        
        bonus_passed = sum([bonus_5m_strong, bonus_candle, bonus_vwap_above, bonus_pcr, 
                           bonus_momentum, bonus_flow, multi_tf, gamma_zone, bonus_vol_strong, bonus_30m])
        
        # ━━━━━━━━━━━━ CONFIDENCE CALCULATION ━━━━━━━━━━━━
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
        
        # 🆕 NEW: OI Velocity boost
        confidence += vel_confidence
        
        # 🆕 NEW: OTM analysis
        confidence += otm_modifier
        
        # OI Scenario boost
        confidence += oi_scenario_boost
        
        # PCR modifier
        confidence += pcr_modifier
        
        # Bonus checks
        confidence += min(bonus_passed * 2, 15)
        
        confidence = min(confidence, 98)
        
        if confidence < MIN_CONFIDENCE:
            logger.debug(f"  ❌ CE_BUY: Confidence {confidence}% < {MIN_CONFIDENCE}%")
            return None
        
        # ━━━━━━━━━━━━ CALCULATE LEVELS ━━━━━━━━━━━━
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
            oi_30m=ce_total_30m,  # 🆕 NEW
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
            oi_scenario_type=oi_scenario_type,
            oi_velocity_pattern=f"{ce_velocity} ({vel_strength})",  # 🆕 NEW
            otm_analysis=otm_details,  # 🆕 NEW
            is_expiry_day=gamma_zone
        )
        
        logger.info(f"  ✅ CE_BUY signal generated!")
        logger.info(f"  Confidence: {confidence}%")
        logger.info(f"  VWAP Score: {vwap_score}/100 ✅")
        logger.info(f"  PCR Bias: {pcr_bias}")
        logger.info(f"  OI Velocity: {ce_velocity} ({vel_strength})")
        logger.info(f"  OTM: {otm_details}")
        
        return signal
    
    def _check_pe_buy(self, spot_price, futures_price, vwap, vwap_distance, pcr, atr,
                      atm_strike, atm_data, strike_data,
                      ce_total_5m, pe_total_5m, ce_total_15m, pe_total_15m, ce_total_30m, pe_total_30m,
                      atm_ce_5m, atm_pe_5m, atm_ce_15m, atm_pe_15m,
                      has_5m_total, has_15m_total, has_30m_total, has_5m_atm, has_15m_atm,
                      volume_spike, volume_ratio, order_flow, candle_data, 
                      gamma_zone, momentum, multi_tf, oi_strength='weak', oi_scenario=None, **kwargs):
        """Check PE_BUY setup with COMPREHENSIVE VALIDATION + VELOCITY + OTM"""
        
        # ━━━━━━━━━━━━ VWAP VALIDATION ━━━━━━━━━━━━
        vwap_valid, vwap_reason, vwap_score = TechnicalAnalyzer.validate_signal_with_vwap(
            "PE_BUY", futures_price, vwap, atr
        )
        
        if futures_price >= vwap:
            logger.debug(f"  ❌ PE_BUY HARD REJECT: Entry ₹{futures_price:.2f} >= VWAP ₹{vwap:.2f}")
            return None
        
        if vwap_score < MIN_VWAP_SCORE:
            logger.debug(f"  ❌ PE_BUY rejected: VWAP score {vwap_score} < {MIN_VWAP_SCORE}")
            return None
        
        if not vwap_valid:
            logger.debug(f"  ❌ PE_BUY rejected: {vwap_reason}")
            return None
        
        logger.debug(f"  ✅ VWAP check passed: Entry ₹{futures_price:.2f} < VWAP ₹{vwap:.2f} (Score: {vwap_score})")
        
        # ━━━━━━━━━━━━ PCR BIAS ━━━━━━━━━━━━
        pcr_bias, pcr_desc, pcr_modifier = get_pcr_bias(pcr)
        logger.debug(f"  📊 PCR Bias: {pcr_bias} - {pcr_desc}")
        
        if pcr > PCR_OVERSOLD:
            logger.debug(f"  ⚠️ PE_BUY cautious: PCR {pcr:.2f} too high (oversold)")
        
        # ━━━━━━━━━━━━ OI VELOCITY ANALYSIS ━━━━━━━━━━━━
        pe_velocity, vel_strength, vel_desc, vel_confidence = OIAnalyzer.classify_oi_velocity(
            pe_total_5m, pe_total_15m, pe_total_30m, has_30m_total, 'PE'
        )
        
        logger.debug(f"  🚀 PE Velocity: {pe_velocity} ({vel_strength}) - {vel_desc}")
        
        if pe_velocity in ['DECELERATION', 'EXHAUSTION']:
            logger.debug(f"  ❌ PE_BUY rejected: {pe_velocity} pattern (losing momentum)")
            return None
        
        # ━━━━━━━━━━━━ OTM STRIKE ANALYSIS ━━━━━━━━━━━━
        has_support, has_resistance, otm_modifier, otm_details = OIAnalyzer.analyze_otm_levels(
            strike_data, atm_strike, "PE_BUY"
        )
        
        logger.debug(f"  🎯 OTM: {otm_details}")
        
        # ━━━━━━━━━━━━ OI SCENARIO ━━━━━━━━━━━━
        oi_scenario_boost = 0
        oi_scenario_type = None
        
        if oi_scenario:
            primary_direction = oi_scenario.get('primary_direction', 'NEUTRAL')
            pe_signal = oi_scenario.get('pe_signal', 'NEUTRAL')
            pe_scenario = oi_scenario.get('pe_scenario')
            human_name = oi_scenario.get('human_name', '')
            
            if 'BEARISH' in primary_direction or 'BEARISH' in pe_signal:
                if 'STRONG' in pe_signal:
                    oi_scenario_boost = 15
                    oi_scenario_type = f"{human_name} (STRONG)"
                else:
                    oi_scenario_boost = 5
                    oi_scenario_type = f"{human_name} (WEAK)"
                
                logger.debug(f"  🔥 OI Scenario: {oi_scenario_type} (+{oi_scenario_boost}%)")
        
        # ━━━━━━━━━━━━ PRIMARY CHECKS ━━━━━━━━━━━━
        primary_pe = (pe_total_15m < -MIN_OI_15M_FOR_ENTRY and 
                     pe_total_5m < -MIN_OI_5M_FOR_ENTRY and 
                     has_15m_total and has_5m_total)
        
        primary_atm = atm_pe_15m < -ATM_OI_THRESHOLD and has_15m_atm
        primary_vol = volume_spike
        
        primary_30m_confirm = False
        if has_30m_total and pe_total_30m < -MIN_OI_30M_FOR_ENTRY:
            primary_30m_confirm = True
            logger.debug(f"  ✅ 30m confirmation: PE {pe_total_30m:.1f}%")
        
        primary_passed = sum([primary_pe, primary_atm, primary_vol])
        
        if primary_passed < MIN_PRIMARY_CHECKS:
            logger.debug(f"  ❌ PE_BUY: Only {primary_passed}/{MIN_PRIMARY_CHECKS} primary checks")
            return None
        
        # ━━━━━━━━━━━━ BONUS CHECKS ━━━━━━━━━━━━
        bonus_5m_strong = pe_total_5m < -STRONG_OI_5M_THRESHOLD and has_5m_total
        bonus_candle = candle_data.get('size', 0) >= MIN_CANDLE_SIZE
        bonus_vwap_below = vwap_distance < 0
        bonus_pcr = pcr < PCR_BEARISH
        bonus_momentum = momentum.get('consecutive_red', 0) >= 2
        bonus_flow = order_flow > 1.0
        bonus_vol_strong = volume_ratio >= VOL_SPIKE_STRONG
        bonus_30m = primary_30m_confirm
        
        bonus_passed = sum([bonus_5m_strong, bonus_candle, bonus_vwap_below, bonus_pcr, 
                           bonus_momentum, bonus_flow, multi_tf, gamma_zone, bonus_vol_strong, bonus_30m])
        
        # ━━━━━━━━━━━━ CONFIDENCE CALCULATION ━━━━━━━━━━━━
        confidence = 40
        
        if primary_pe:
            if oi_strength == 'strong':
                confidence += 25
            else:
                confidence += 20
        if primary_atm: confidence += 20
        if primary_vol: confidence += 15
        
        confidence += int(vwap_score / 5)
        confidence += vel_confidence
        confidence += otm_modifier
        confidence += oi_scenario_boost
        confidence += pcr_modifier
        confidence += min(bonus_passed * 2, 15)
        
        confidence = min(confidence, 98)
        
        if confidence < MIN_CONFIDENCE:
            logger.debug(f"  ❌ PE_BUY: Confidence {confidence}% < {MIN_CONFIDENCE}%")
            return None
        
        # ━━━━━━━━━━━━ CALCULATE LEVELS ━━━━━━━━━━━━
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
            oi_30m=pe_total_30m,
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
            oi_scenario_type=oi_scenario_type,
            oi_velocity_pattern=f"{pe_velocity} ({vel_strength})",
            otm_analysis=otm_details,
            is_expiry_day=gamma_zone
        )
        
        logger.info(f"  ✅ PE_BUY signal generated!")
        logger.info(f"  Confidence: {confidence}%")
        logger.info(f"  VWAP Score: {vwap_score}/100 ✅")
        logger.info(f"  PCR Bias: {pcr_bias}")
        logger.info(f"  OI Velocity: {pe_velocity} ({vel_strength})")
        logger.info(f"  OTM: {otm_details}")
        
        return signal


# ==================== Signal Validator ====================
class SignalValidator:
    """Validate if signal should be executed"""
    
    def __init__(self):
        self.last_signal_time = None
        self.last_signal_strike = None
        self.last_signal_type = None
    
    def should_execute(self, signal: Signal) -> tuple[bool, str]:
        """Check if signal should be executed"""
        
        if not self.last_signal_time:
            return True, "First signal"
        
        time_since_last = (signal.timestamp - self.last_signal_time).total_seconds() / 60
        
        if time_since_last < SAME_DIRECTION_COOLDOWN_MINUTES:
            return False, f"Cooldown: {SAME_DIRECTION_COOLDOWN_MINUTES - int(time_since_last)} min left"
        
        if (signal.recommended_strike == self.last_signal_strike and 
            str(signal.signal_type) == self.last_signal_type):
            if time_since_last < SAME_STRIKE_COOLDOWN_MINUTES:
                return False, f"Same strike cooldown: {SAME_STRIKE_COOLDOWN_MINUTES - int(time_since_last)} min left"
        
        return True, "Validation passed"
    
    def record_signal(self, signal: Signal):
        """Record executed signal"""
        self.last_signal_time = signal.timestamp
        self.last_signal_strike = signal.recommended_strike
        self.last_signal_type = str(signal.signal_type)
