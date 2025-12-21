"""
Analyzers - OI + PCR + VWAP Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Implements: 9 Scenarios from PDF Guide
Logic: Price + OI Change + PCR = Signal
"""

import logging
from config import *
from utils import *

logger = logging.getLogger("NiftyBot.Analyzers")

class OIAnalyzer:
    """
    OI Change Analysis
    Tracks: Call OI, Put OI changes
    Detects: Writing, Unwinding
    """
    
    def __init__(self, data_manager):
        self.dm = data_manager
    
    def analyze_oi_changes(self, current_chain, minutes_ago=5):
        """
        Analyze OI changes
        Returns: {ce_change, pe_change, interpretation}
        """
        ce_change, pe_change = self.dm.get_oi_change(minutes_ago)
        
        if ce_change is None or pe_change is None:
            return {
                'ce_change': 0,
                'pe_change': 0,
                'ce_status': 'UNKNOWN',
                'pe_status': 'UNKNOWN',
                'interpretation': 'Insufficient data'
            }
        
        # Interpret CE OI change
        if ce_change > OI_STRONG_CHANGE:
            ce_status = 'STRONG_WRITING'  # Call writing (bearish)
        elif ce_change > OI_SIGNIFICANT_CHANGE:
            ce_status = 'WRITING'
        elif ce_change < -OI_STRONG_CHANGE:
            ce_status = 'STRONG_UNWINDING'  # Call unwinding (bullish)
        elif ce_change < -OI_SIGNIFICANT_CHANGE:
            ce_status = 'UNWINDING'
        else:
            ce_status = 'STABLE'
        
        # Interpret PE OI change
        if pe_change > OI_STRONG_CHANGE:
            pe_status = 'STRONG_WRITING'  # Put writing (bullish)
        elif pe_change > OI_SIGNIFICANT_CHANGE:
            pe_status = 'WRITING'
        elif pe_change < -OI_STRONG_CHANGE:
            pe_status = 'STRONG_UNWINDING'  # Put unwinding (bearish)
        elif pe_change < -OI_SIGNIFICANT_CHANGE:
            pe_status = 'UNWINDING'
        else:
            pe_status = 'STABLE'
        
        # Overall interpretation
        if ce_status in ['STRONG_UNWINDING', 'UNWINDING']:
            interpretation = 'Call Unwinding - Bullish'
        elif pe_status in ['STRONG_UNWINDING', 'UNWINDING']:
            interpretation = 'Put Unwinding - Bearish'
        elif ce_status in ['STRONG_WRITING', 'WRITING']:
            interpretation = 'Call Writing - Resistance'
        elif pe_status in ['STRONG_WRITING', 'WRITING']:
            interpretation = 'Put Writing - Support'
        else:
            interpretation = 'Neutral'
        
        result = {
            'ce_change': ce_change,
            'pe_change': pe_change,
            'ce_status': ce_status,
            'pe_status': pe_status,
            'interpretation': interpretation,
            'minutes_ago': minutes_ago
        }
        
        logger.debug(f"OI Change ({minutes_ago}m): CE={ce_change:+.1f}%, PE={pe_change:+.1f}% → {interpretation}")
        
        return result
    
    def get_atm_strike_oi(self, chain_data, spot_price):
        """Get ATM strike OI data"""
        atm_strike = round_to_strike(spot_price)
        
        for strike in chain_data['strikes']:
            if strike['strike'] == atm_strike:
                return {
                    'strike': atm_strike,
                    'ce_oi': strike['CE'].get('oi', 0),
                    'pe_oi': strike['PE'].get('oi', 0),
                    'ce_volume': strike['CE'].get('volume', 0),
                    'pe_volume': strike['PE'].get('volume', 0)
                }
        
        return None


class PCRAnalyzer:
    """
    PCR (Put-Call Ratio) Analysis
    From PDF: PCR = Put OI / Call OI
    """
    
    def __init__(self):
        pass
    
    def analyze_pcr(self, chain_data):
        """
        Analyze PCR value
        Returns: {pcr, zone, bias, strength}
        """
        pcr = chain_data['pcr']
        
        # Determine zone (from PDF)
        if pcr > PCR_STRONG_SUPPORT:
            zone = 'STRONG_SUPPORT'
            bias = 'BULLISH'
            strength = 'STRONG'
            action = 'BUY'
        elif pcr > PCR_SUPPORT:
            zone = 'SUPPORT'
            bias = 'BULLISH'
            strength = 'MEDIUM'
            action = 'BUY_DIP'
        elif pcr > PCR_NEUTRAL_HIGH:
            zone = 'NEUTRAL_BULLISH'
            bias = 'BULLISH'
            strength = 'WEAK'
            action = 'HOLD'
        elif pcr > PCR_NEUTRAL_LOW:
            zone = 'NEUTRAL'
            bias = 'NEUTRAL'
            strength = 'NONE'
            action = 'WAIT'
        elif pcr > PCR_RESISTANCE:
            zone = 'NEUTRAL_BEARISH'
            bias = 'BEARISH'
            strength = 'WEAK'
            action = 'CAUTION'
        else:
            zone = 'STRONG_RESISTANCE'
            bias = 'BEARISH'
            strength = 'STRONG'
            action = 'SELL'
        
        result = {
            'pcr': pcr,
            'zone': zone,
            'bias': bias,
            'strength': strength,
            'action': action
        }
        
        logger.debug(f"PCR: {pcr:.3f} → {zone} ({bias})")
        
        return result
    
    def get_pcr_change(self, data_manager, minutes_ago=5):
        """Calculate PCR change"""
        old_data = data_manager.get_oi_history(minutes_ago)
        
        if not old_data or len(data_manager.oi_history) == 0:
            return None
        
        current_data = data_manager.oi_history[-1]
        
        pcr_change = current_data['pcr'] - old_data['pcr']
        
        # Interpret
        if pcr_change > 0.3:
            momentum = 'STRONG_BEARISH'  # PCR increasing = bearish
        elif pcr_change > 0.1:
            momentum = 'BEARISH'
        elif pcr_change < -0.3:
            momentum = 'STRONG_BULLISH'  # PCR decreasing = bullish
        elif pcr_change < -0.1:
            momentum = 'BULLISH'
        else:
            momentum = 'NEUTRAL'
        
        return {
            'old_pcr': old_data['pcr'],
            'new_pcr': current_data['pcr'],
            'change': pcr_change,
            'momentum': momentum
        }


class VWAPAnalyzer:
    """
    VWAP (Volume Weighted Average Price) Analysis
    Confirms: Price position relative to VWAP
    """
    
    def __init__(self):
        self.vwap_history = []
    
    def calculate_vwap(self, candles):
        """
        Calculate VWAP from candle data
        VWAP = Σ(Price × Volume) / Σ(Volume)
        """
        if not candles or len(candles) == 0:
            return None
        
        total_pv = sum(c['close'] * c['volume'] for c in candles)
        total_v = sum(c['volume'] for c in candles)
        
        if total_v == 0:
            return None
        
        vwap = total_pv / total_v
        return vwap
    
    def analyze_price_vs_vwap(self, current_price, vwap):
        """
        Check if price above/below VWAP
        Returns: {position, deviation, bias}
        """
        if vwap is None:
            return {
                'position': 'UNKNOWN',
                'deviation': 0,
                'bias': 'NEUTRAL'
            }
        
        deviation = ((current_price - vwap) / vwap) * 100
        
        if deviation > VWAP_DEVIATION_MAX:
            position = 'STRONG_ABOVE'
            bias = 'BULLISH'
        elif deviation > 0:
            position = 'ABOVE'
            bias = 'BULLISH'
        elif deviation < -VWAP_DEVIATION_MAX:
            position = 'STRONG_BELOW'
            bias = 'BEARISH'
        elif deviation < 0:
            position = 'BELOW'
            bias = 'BEARISH'
        else:
            position = 'AT_VWAP'
            bias = 'NEUTRAL'
        
        return {
            'vwap': vwap,
            'position': position,
            'deviation': deviation,
            'bias': bias
        }


class MarketAnalyzer:
    """
    Combined Market Analysis
    Integrates: OI + PCR + VWAP
    Implements: 9 Scenarios from PDF
    """
    
    def __init__(self, data_manager):
        self.dm = data_manager
        self.oi_analyzer = OIAnalyzer(data_manager)
        self.pcr_analyzer = PCRAnalyzer()
        self.vwap_analyzer = VWAPAnalyzer()
    
    def comprehensive_analysis(self, chain_data, current_price, vwap=None):
        """
        Complete market analysis
        Returns: Full analysis dict
        """
        # Get price change
        price_change = self.dm.get_price_change(5)
        
        # OI analysis
        oi_analysis = self.oi_analyzer.analyze_oi_changes(chain_data, 5)
        
        # PCR analysis
        pcr_analysis = self.pcr_analyzer.analyze_pcr(chain_data)
        pcr_change = self.pcr_analyzer.get_pcr_change(self.dm, 5)
        
        # VWAP analysis
        vwap_analysis = self.vwap_analyzer.analyze_price_vs_vwap(current_price, vwap)
        
        # ATM strike OI
        atm_oi = self.oi_analyzer.get_atm_strike_oi(chain_data, current_price)
        
        return {
            'timestamp': get_ist_time(),
            'price': current_price,
            'price_change': price_change,
            'oi': oi_analysis,
            'pcr': pcr_analysis,
            'pcr_change': pcr_change,
            'vwap': vwap_analysis,
            'atm_oi': atm_oi,
            'total_ce_oi': chain_data['total_ce_oi'],
            'total_pe_oi': chain_data['total_pe_oi']
        }
