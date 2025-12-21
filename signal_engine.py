"""
Signal Engine - Trading Signal Generation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Implements: 9 Scenarios from PDF Guide
Logic: Price Movement + OI Change + PCR = Signal
"""

import logging
from config import *
from utils import *

logger = logging.getLogger("NiftyBot.SignalEngine")

class TradingSignal:
    """Trading signal data structure"""
    
    def __init__(self, signal_type, confidence, reason, analysis):
        self.signal_type = signal_type
        self.confidence = confidence
        self.reason = reason
        self.timestamp = get_ist_time()
        self.analysis = analysis
        
        # Will be set later
        self.entry_strike = None
        self.entry_price = None
        self.target_price = None
        self.stop_loss = None
    
    def __repr__(self):
        return f"Signal({self.signal_type}, {self.confidence}%)"


class SignalEngine:
    """
    Generate trading signals
    Based on: 9 Scenarios from PDF
    """
    
    def __init__(self):
        self.last_signal = None
        self.signals_today = 0
    
    def generate_signal(self, analysis):
        """
        Main signal generation logic
        Implements 9 scenarios from PDF
        
        Returns: TradingSignal or None
        """
        # Check if we have enough data
        if not analysis or not analysis.get('oi') or not analysis.get('pcr'):
            logger.debug("Insufficient data for signal generation")
            return None
        
        # Check max trades
        if self.signals_today >= MAX_TRADES_PER_DAY:
            logger.info(f"⏸️ Max trades ({MAX_TRADES_PER_DAY}) reached today")
            return None
        
        # Extract data
        price_change = analysis.get('price_change', 0)
        oi = analysis['oi']
        pcr_data = analysis['pcr']
        
        ce_change = oi['ce_change']
        pe_change = oi['pe_change']
        pcr = pcr_data['pcr']
        
        # Determine price direction
        if price_change is None or abs(price_change) < 5:
            price_direction = 'SIDEWAYS'
        elif price_change > PRICE_SIGNIFICANT_MOVE:
            price_direction = 'STRONG_UP'
        elif price_change > 0:
            price_direction = 'UP'
        elif price_change < -PRICE_SIGNIFICANT_MOVE:
            price_direction = 'STRONG_DOWN'
        else:
            price_direction = 'DOWN'
        
        logger.info(f"")
        logger.info(f"📊 SIGNAL ANALYSIS:")
        logger.info(f"  Price: {price_direction} ({price_change:+.1f} pts)")
        logger.info(f"  OI: CE={ce_change:+.1f}%, PE={pe_change:+.1f}%")
        logger.info(f"  PCR: {pcr:.3f} ({pcr_data['zone']})")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SCENARIO MATCHING (9 Scenarios from PDF)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        signal = None
        
        # SCENARIO 1: Price UP + Put OI DOWN + PCR DOWN
        # 🟢🟢 STRONG BULLISH - Put Unwinding
        if (price_direction in ['UP', 'STRONG_UP'] and 
            pe_change < -OI_SIGNIFICANT_CHANGE and 
            ce_change > -OI_SIGNIFICANT_CHANGE):
            
            signal = TradingSignal(
                signal_type=SignalType.CE_BUY,
                confidence=90,
                reason=[
                    "🟢🟢 SCENARIO 1: STRONG BULLISH",
                    f"Put Unwinding detected ({pe_change:.1f}%)",
                    f"Price rising ({price_change:+.1f} pts)",
                    "Bulls winning - puts being closed"
                ],
                analysis=analysis
            )
        
        # SCENARIO 2: Price UP + Call OI DOWN + PCR UP
        # 🟢🟢 STRONG BULLISH - Call Unwinding
        elif (price_direction in ['UP', 'STRONG_UP'] and 
              ce_change < -OI_SIGNIFICANT_CHANGE and 
              pe_change > -OI_SIGNIFICANT_CHANGE):
            
            signal = TradingSignal(
                signal_type=SignalType.CE_BUY,
                confidence=90,
                reason=[
                    "🟢🟢 SCENARIO 2: STRONG BULLISH",
                    f"Call Unwinding detected ({ce_change:.1f}%)",
                    f"Price rising ({price_change:+.1f} pts)",
                    "Bears losing - resistance broken"
                ],
                analysis=analysis
            )
        
        # SCENARIO 3: Price UP + Call OI UP + PCR DOWN
        # 🔴 Bearish (Resistance Building)
        elif (price_direction in ['UP', 'STRONG_UP'] and 
              ce_change > OI_SIGNIFICANT_CHANGE):
            
            signal = TradingSignal(
                signal_type=SignalType.NO_TRADE,
                confidence=0,
                reason=[
                    "🔴 SCENARIO 3: RESISTANCE BUILDING",
                    f"Call Writing detected ({ce_change:+.1f}%)",
                    f"Price rising but resistance ahead",
                    "⚠️ CAUTION - Exit longs or wait"
                ],
                analysis=analysis
            )
        
        # SCENARIO 4: Price DOWN + Put OI UP + PCR UP
        # 🟢 Bullish (Support Building)
        elif (price_direction in ['DOWN', 'STRONG_DOWN'] and 
              pe_change > OI_SIGNIFICANT_CHANGE):
            
            signal = TradingSignal(
                signal_type=SignalType.CE_BUY,
                confidence=75,
                reason=[
                    "🟢 SCENARIO 4: SUPPORT BUILDING",
                    f"Put Writing detected ({pe_change:+.1f}%)",
                    f"Price falling but support forming",
                    "Good zone for buy on dip"
                ],
                analysis=analysis
            )
        
        # SCENARIO 5: Price DOWN + Call OI DOWN + PCR UP
        # 🔴🔴 STRONG BEARISH - Call Unwinding
        elif (price_direction in ['DOWN', 'STRONG_DOWN'] and 
              ce_change < -OI_SIGNIFICANT_CHANGE):
            
            signal = TradingSignal(
                signal_type=SignalType.PE_BUY,
                confidence=90,
                reason=[
                    "🔴🔴 SCENARIO 5: STRONG BEARISH",
                    f"Call Unwinding detected ({ce_change:.1f}%)",
                    f"Price falling ({price_change:+.1f} pts)",
                    "Bulls losing - calls being closed"
                ],
                analysis=analysis
            )
        
        # SCENARIO 6: Price DOWN + Put OI DOWN + PCR DOWN
        # 🔴🔴 STRONG BEARISH - Put Unwinding
        elif (price_direction in ['DOWN', 'STRONG_DOWN'] and 
              pe_change < -OI_SIGNIFICANT_CHANGE):
            
            signal = TradingSignal(
                signal_type=SignalType.PE_BUY,
                confidence=90,
                reason=[
                    "🔴🔴 SCENARIO 6: STRONG BEARISH",
                    f"Put Unwinding (panic) ({pe_change:.1f}%)",
                    f"Price falling ({price_change:+.1f} pts)",
                    "Bears winning - panic selling"
                ],
                analysis=analysis
            )
        
        # SCENARIO 7: Price UP + Put OI UP + PCR UP
        # ⚠️ Weak Bullish / Caution
        elif (price_direction in ['UP', 'STRONG_UP'] and 
              pe_change > OI_SIGNIFICANT_CHANGE):
            
            signal = TradingSignal(
                signal_type=SignalType.NO_TRADE,
                confidence=0,
                reason=[
                    "⚠️ SCENARIO 7: WEAK BULLISH / CAUTION",
                    f"Put Buying detected ({pe_change:+.1f}%)",
                    "Price rising but protection being bought",
                    "Doubt in rally - wait for confirmation"
                ],
                analysis=analysis
            )
        
        # SCENARIO 8: Price SIDEWAYS + Put OI UP (High) + PCR High
        # 🟢 Support Zone
        elif (price_direction == 'SIDEWAYS' and 
              pe_change > OI_STRONG_CHANGE and 
              pcr > PCR_STRONG_SUPPORT):
            
            signal = TradingSignal(
                signal_type=SignalType.CE_BUY,
                confidence=80,
                reason=[
                    "🟢 SCENARIO 8: SUPPORT ZONE",
                    f"Heavy Put Writing ({pe_change:+.1f}%)",
                    f"PCR very high ({pcr:.3f})",
                    "Strong support zone - buy here"
                ],
                analysis=analysis
            )
        
        # SCENARIO 9: Price SIDEWAYS + Call OI UP (High) + PCR Low
        # 🔴 Resistance Zone
        elif (price_direction == 'SIDEWAYS' and 
              ce_change > OI_STRONG_CHANGE and 
              pcr < PCR_STRONG_RESISTANCE):
            
            signal = TradingSignal(
                signal_type=SignalType.NO_TRADE,
                confidence=0,
                reason=[
                    "🔴 SCENARIO 9: RESISTANCE ZONE",
                    f"Heavy Call Writing ({ce_change:+.1f}%)",
                    f"PCR very low ({pcr:.3f})",
                    "Strong resistance - avoid longs"
                ],
                analysis=analysis
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ADDITIONAL FILTERS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if signal and signal.signal_type != SignalType.NO_TRADE:
            
            # VWAP confirmation (if enabled)
            if VWAP_FILTER_ENABLED and analysis.get('vwap'):
                vwap_data = analysis['vwap']
                
                if signal.signal_type == SignalType.CE_BUY:
                    if vwap_data['bias'] == 'BEARISH':
                        logger.warning("  ⚠️ VWAP filter: Price below VWAP - reducing confidence")
                        signal.confidence -= 15
                
                elif signal.signal_type == SignalType.PE_BUY:
                    if vwap_data['bias'] == 'BULLISH':
                        logger.warning("  ⚠️ VWAP filter: Price above VWAP - reducing confidence")
                        signal.confidence -= 15
            
            # Expiry day caution
            if CAUTIOUS_EXPIRY_DAY and is_expiry_day():
                logger.warning("  ⚠️ Expiry day - reducing confidence")
                signal.confidence -= 10
            
            # Check minimum confidence
            if signal.confidence < MIN_CONFIDENCE:
                logger.info(f"  ❌ Confidence too low: {signal.confidence}% < {MIN_CONFIDENCE}%")
                return None
            
            # Add entry/exit levels
            self._add_entry_exit_levels(signal, analysis)
            
            # Log signal
            logger.info(f"")
            logger.info(f"🎯 SIGNAL GENERATED:")
            logger.info(f"  Type: {signal.signal_type}")
            logger.info(f"  Confidence: {signal.confidence}%")
            for r in signal.reason:
                logger.info(f"  {r}")
            
            self.signals_today += 1
            self.last_signal = signal
            
            return signal
        
        else:
            logger.info(f"  ⏹️ No clear signal at this time")
            return None
    
    def _add_entry_exit_levels(self, signal, analysis):
        """Add entry, target, stop loss levels"""
        atm_strike = round_to_strike(analysis['price'])
        
        # For CE_BUY: Use ATM CE
        # For PE_BUY: Use ATM PE
        signal.entry_strike = atm_strike
        
        # Get option premium (simplified - you'd fetch from chain)
        # Using ATM OI data from analysis
        atm_oi = analysis.get('atm_oi')
        if atm_oi:
            # Estimate premium (simplified)
            estimated_premium = 100  # You'd get actual LTP from chain
            
            signal.entry_price = estimated_premium
            signal.target_price = estimated_premium * TARGET_MULTIPLIER
            signal.stop_loss = estimated_premium * (1 - STOP_LOSS_PERCENT/100)
        
        logger.debug(f"  Entry: {signal.entry_strike} @ ₹{signal.entry_price:.2f}")
        logger.debug(f"  Target: ₹{signal.target_price:.2f} | SL: ₹{signal.stop_loss:.2f}")
    
    def reset_daily_count(self):
        """Reset signal count at start of day"""
        self.signals_today = 0
        logger.info("📊 Daily signal count reset")
