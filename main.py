"""
NIFTY Trading Bot - Main Orchestrator v6.0
COMPREHENSIVE FIX: All validation improvements + No expiry_utils
"""

import asyncio
from datetime import datetime

from config import *
from utils import *
from data_manager import UpstoxClient, RedisBrain, DataFetcher, InMemoryOITracker
from analyzers import OIAnalyzer, VolumeAnalyzer, TechnicalAnalyzer, MarketAnalyzer
from signal_engine import SignalGenerator, SignalValidator  # 🔥 v6
from position_tracker import PositionTracker
from alerts import TelegramBot, MessageFormatter

BOT_VERSION = "6.0-COMPREHENSIVE-FIX"

logger = setup_logger("main")


class NiftyTradingBot:
    """Main bot orchestrator - v6.0 COMPREHENSIVE FIX"""
    
    def __init__(self):
        # 🆕 In-Memory OI Tracker (No Redis needed!)
        self.oi_tracker = InMemoryOITracker()
        
        # Redis Brain (deprecated, keeping for compatibility)
        self.memory = RedisBrain()
        
        self.upstox = None
        self.data_fetcher = None
        
        self.oi_analyzer = OIAnalyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.technical_analyzer = TechnicalAnalyzer()
        self.market_analyzer = MarketAnalyzer()
        
        self.signal_gen = SignalGenerator()
        self.signal_validator = SignalValidator()
        self.position_tracker = PositionTracker()
        self.telegram = TelegramBot()
        
        self.is_running = False
        self.in_position = False
        self.current_signal = None
    
    async def initialize(self):
        """Initialize bot and connections"""
        logger.info("=" * 60)
        logger.info(f"🚀 Initializing NIFTY Bot v{BOT_VERSION}")
        logger.info("=" * 60)
        
        # Initialize Upstox
        self.upstox = UpstoxClient()
        success = await self.upstox.initialize()
        
        if not success:
            raise Exception("Failed to initialize Upstox client")
        
        self.data_fetcher = DataFetcher(self.upstox)
        
        # Get contract details (expiry auto-detected by Upstox)
        futures_contract = self.upstox.futures_symbol if self.upstox.futures_symbol else "NIFTY FUTURES"
        weekly_expiry = self.upstox.weekly_expiry.strftime('%Y-%m-%d') if self.upstox.weekly_expiry else "AUTO"
        
        current_time = format_time_ist(get_ist_time())
        
        example_atm = 24150
        deep_strikes = get_deep_analysis_strikes(example_atm)
        deep_range = f"{deep_strikes[0]}-{deep_strikes[-1]}"
        
        fetch_min, fetch_max = get_strike_range_fetch(example_atm)
        
        startup_msg = f"""
🚀 <b>NIFTY BOT v{BOT_VERSION}</b>

━━━━━━━━━━━━━━━━━━━━
🔧 <b>v6.0 COMPREHENSIVE FIX</b>
━━━━━━━━━━━━━━━━━━━━

✅ VWAP Hard Validation (price MUST be correct side)
✅ Reversal Detection (both ATM unwinding = NO_TRADE)
✅ Time Filter (no trades after 3:00 PM)
✅ Trap Detection (one-sided spike = NO_TRADE)
✅ PCR Bias Bands (context-aware signals)
✅ Raised VWAP threshold (50 → 70)

━━━━━━━━━━━━━━━━━━━━
📅 <b>CONTRACT DETAILS</b>
━━━━━━━━━━━━━━━━━━━━

<b>Futures (MONTHLY):</b>
• Contract: {futures_contract}
• Expiry: Auto-detected

<b>Options (WEEKLY):</b>
• Expiry: {weekly_expiry}
• Auto-selected by Upstox

━━━━━━━━━━━━━━━━━━━━
📊 <b>DATA STRATEGY</b>
━━━━━━━━━━━━━━━━━━━━

<b>Analysis Window:</b>
• ATM ± 5 strikes (11 total)
• Deep: {deep_range}
• Fetch: {fetch_min}-{fetch_max}

<b>OI Tracking:</b>
• 5m changes (momentum)
• 15m changes (trend)
• ATM-specific analysis
• 🆕 In-Memory tracking

<b>Technical:</b>
• VWAP (strict validation)
• ATR stops
• Price action
• PCR bias

━━━━━━━━━━━━━━━━━━━━
⚙️ <b>RISK SETTINGS</b>
━━━━━━━━━━━━━━━━━━━━

• Min Confidence: {MIN_CONFIDENCE}%
• ATR Multiplier: {ATR_TARGET_MULTIPLIER}x
• Stop Loss: {ATR_SL_MULTIPLIER}x ATR
• PCR Range: {PCR_BEARISH}-{PCR_BULLISH}

━━━━━━━━━━━━━━━━━━━━
⏰ <b>STARTED</b>
━━━━━━━━━━━━━━━━━━━━

{current_time}
"""
        
        if self.telegram.is_enabled():
            await self.telegram.send(startup_msg)
        
        logger.info("✅ Bot initialized (v6.0 COMPREHENSIVE FIX)")
        logger.info(f"📅 Futures: {futures_contract}")
        logger.info(f"📅 Weekly: {weekly_expiry}")
        logger.info("=" * 60)
    
    async def shutdown(self):
        """Shutdown bot"""
        logger.info("🛑 Shutting down...")
        
        if self.telegram.is_enabled():
            await self.telegram.send("🛑 <b>Bot Stopped</b>")
        
        self.is_running = False
        logger.info("✅ Shutdown complete")
    
    async def scan_market(self):
        """Single market scan"""
        try:
            now_ist = get_ist_time()
            time_str = format_time_ist(now_ist)
            market_status = "OPEN" if is_market_open(now_ist) else "CLOSED"
            
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"⏰ {time_str} | {market_status}")
            logger.info("=" * 60)
            
            # Skip if market closed
            if market_status == "CLOSED":
                logger.info("⏸️ Market closed - Skipping scan")
                return
            
            # ========== DATA FETCHING ==========
            
            logger.info("📥 Fetching market data...")
            
            spot = await self.data_fetcher.fetch_spot()
            futures_df = await self.data_fetcher.fetch_futures_candles()
            futures_ltp = await self.data_fetcher.fetch_futures_ltp()
            
            if not spot or not futures_ltp or futures_df is None:
                logger.error("❌ Failed to fetch basic data")
                return
            
            logger.info(f"  ✅ Spot: ₹{spot:.2f}")
            logger.info(f"  ✅ Futures Candles: {len(futures_df)} bars")
            logger.info(f"  ✅ Futures LIVE: ₹{futures_ltp:.2f}")
            
            # Price changes
            price_5m, has_price_5m = self.memory.get_price_change(futures_ltp, 5)
            price_15m, has_price_15m = self.memory.get_price_change(futures_ltp, 15)
            price_open = ((futures_ltp - self.memory.session_open) / self.memory.session_open * 100) if self.memory.session_open else 0
            
            logger.info(f"  🆕 Price Changes:")
            logger.info(f"     5m:  {price_5m:+.2f}% {'✅' if has_price_5m else '⏳'}")
            logger.info(f"     15m: {price_15m:+.2f}% {'✅' if has_price_15m else '⏳'}")
            logger.info(f"     From Open: {price_open:+.2f}%")
            
            # ========== OPTION CHAIN ==========
            
            option_result = await self.data_fetcher.fetch_option_chain(spot)
            
            if not option_result:
                logger.error("❌ Failed to fetch option chain")
                return
            
            strike_data, atm, total_ce, total_pe = option_result
            
            logger.info(f"  ✅ Strikes: {len(strike_data)} total (ATM {atm})")
            logger.info(f"  ✅ Total OI: CE={total_ce:,.0f}, PE={total_pe:,.0f}")
            
            # Deep OI
            deep_ce, deep_pe = self.oi_analyzer.calculate_deep_oi(strike_data, atm)
            logger.info(f"  🔍 Deep OI: CE={deep_ce:,.0f}, PE={deep_pe:,.0f}")
            
            # ========== OI CALCULATION ==========
            
            logger.info("📊 Calculating OI changes...")
            
            # 🆕 USE IN-MEMORY TRACKER
            prev_total_ce, prev_total_pe, prev_atm_ce, prev_atm_pe, has_history = self.oi_tracker.get_comparison(minutes_ago=5)
            
            if has_history:
                ce_5m = ((total_ce - prev_total_ce) / prev_total_ce * 100) if prev_total_ce > 0 else 0.0
                pe_5m = ((total_pe - prev_total_pe) / prev_total_pe * 100) if prev_total_pe > 0 else 0.0
                has_5m = True
                
                atm_data = self.oi_analyzer.get_atm_data(strike_data, atm)
                current_atm_ce = atm_data.get('ce_oi', 0)
                current_atm_pe = atm_data.get('pe_oi', 0)
                
                atm_ce_5m = ((current_atm_ce - prev_atm_ce) / prev_atm_ce * 100) if prev_atm_ce > 0 else 0.0
                atm_pe_5m = ((current_atm_pe - prev_atm_pe) / prev_atm_pe * 100) if prev_atm_pe > 0 else 0.0
                has_atm_5m = True
            else:
                ce_5m = pe_5m = atm_ce_5m = atm_pe_5m = 0.0
                has_5m = has_atm_5m = False
            
            # 15-minute comparison
            prev_total_ce_15, prev_total_pe_15, prev_atm_ce_15, prev_atm_pe_15, has_history_15 = self.oi_tracker.get_comparison(minutes_ago=15)
            
            if has_history_15:
                ce_15m = ((total_ce - prev_total_ce_15) / prev_total_ce_15 * 100) if prev_total_ce_15 > 0 else 0.0
                pe_15m = ((total_pe - prev_total_pe_15) / prev_total_pe_15 * 100) if prev_total_pe_15 > 0 else 0.0
                
                atm_data = self.oi_analyzer.get_atm_data(strike_data, atm)
                current_atm_ce = atm_data.get('ce_oi', 0)
                current_atm_pe = atm_data.get('pe_oi', 0)
                
                atm_ce_15m = ((current_atm_ce - prev_atm_ce_15) / prev_atm_ce_15 * 100) if prev_atm_ce_15 > 0 else 0.0
                atm_pe_15m = ((current_atm_pe - prev_atm_pe_15) / prev_atm_pe_15 * 100) if prev_atm_pe_15 > 0 else 0.0
                has_15m = has_atm_15m = True
            else:
                ce_15m = pe_15m = atm_ce_15m = atm_pe_15m = 0.0
                has_15m = has_atm_15m = False
            
            # 🆕 SAVE current snapshot
            atm_data = self.oi_analyzer.get_atm_data(strike_data, atm)
            self.oi_tracker.save_snapshot(
                total_ce=total_ce,
                total_pe=total_pe,
                atm_strike=atm,
                atm_ce_oi=atm_data.get('ce_oi', 0),
                atm_pe_oi=atm_data.get('pe_oi', 0)
            )
            
            logger.info(f"  5m:  CE={ce_5m:+.1f}% PE={pe_5m:+.1f}% {'✅' if has_5m else '⏳'}")
            logger.info(f"  15m: CE={ce_15m:+.1f}% PE={pe_15m:+.1f}% {'✅' if has_15m else '⏳'}")
            logger.info(f"  ATM: CE={atm_ce_5m:+.1f}% PE={atm_pe_5m:+.1f}% {'✅' if has_atm_5m else '⏳'}")
            
            # ========== PRICE-AWARE OI ANALYSIS ==========
            
            logger.info("\n🔥 PRICE-AWARE OI ANALYSIS:")
            
            oi_scenario = self.oi_analyzer.analyze_oi_with_price(
                ce_5m=ce_5m,
                ce_15m=ce_15m,
                pe_5m=pe_5m,
                pe_15m=pe_15m,
                price_change_pct=price_5m if has_price_5m else 0.0
            )
            
            logger.info(f"  📊 Primary Direction: {oi_scenario['primary_direction']}")
            logger.info(f"  🎯 Confidence Boost: {oi_scenario['confidence_boost']:+d}%")
            
            if oi_scenario['ce_scenario']:
                ce_detail = oi_scenario['details'].get('ce', {})
                logger.info(f"\n  📞 CE: {oi_scenario['ce_scenario']} ({oi_scenario['ce_signal']})")
                if ce_detail.get('warning'):
                    logger.warning(f"     ⚠️ {ce_detail['warning']}")
            
            if oi_scenario['pe_scenario']:
                pe_detail = oi_scenario['details'].get('pe', {})
                logger.info(f"  📞 PE: {oi_scenario['pe_scenario']} ({oi_scenario['pe_signal']})")
                if pe_detail.get('warning'):
                    logger.warning(f"     ⚠️ {pe_detail['warning']}")
            
            # ========== TECHNICAL ANALYSIS ==========
            
            logger.info("\n🔍 Running technical analysis...")
            
            pcr = self.oi_analyzer.calculate_pcr(total_pe, total_ce)
            vwap = self.technical_analyzer.calculate_vwap(futures_df)
            atr = self.technical_analyzer.calculate_atr(futures_df)
            vwap_dist = self.technical_analyzer.calculate_vwap_distance(futures_ltp, vwap) if vwap else 0
            candle = self.technical_analyzer.analyze_candle(futures_df)
            momentum = self.technical_analyzer.detect_momentum(futures_df)
            
            vol_trend = self.volume_analyzer.analyze_volume_trend(futures_df, futures_ltp=futures_ltp)
            
            # ⚠️ VOLUME DISABLED (Upstox data stale)
            logger.info(f"\n⚠️ Volume analysis: DISABLED (unreliable data)")
            logger.info(f"  Confirmation via: OI + Price direction only")
            
            vol_spike, vol_ratio = False, 1.0  # Disabled
            order_flow = self.volume_analyzer.calculate_order_flow(strike_data)
            
            gamma = self.market_analyzer.detect_gamma_zone()
            unwinding = self.oi_analyzer.detect_unwinding(ce_5m, ce_15m, pe_5m, pe_15m)
            
            if ce_15m < -STRONG_OI_15M_THRESHOLD or pe_15m < -STRONG_OI_15M_THRESHOLD:
                oi_strength = 'strong'
            elif ce_15m < -MIN_OI_15M_FOR_ENTRY or pe_15m < -MIN_OI_15M_FOR_ENTRY:
                oi_strength = 'medium'
            else:
                oi_strength = 'weak'
            
            logger.info(f"  PCR: {pcr:.2f}, VWAP: ₹{vwap:.2f}, ATR: {atr:.1f}")
            logger.info(f"  Candle: {candle['color']} ({candle['type']})")
            logger.info(f"  OI Strength: {oi_strength}, Unwinding: {unwinding}")
            
            # ========== SIGNAL GENERATION ==========
            
            logger.info("\n🎯 Checking for entry setup...")
            
            if self.in_position:
                logger.info("  ⏸️ Already in position - Skipping")
                return
            
            multi_tf = has_5m and has_15m
            
            signal = self.signal_gen.generate(
                spot_price=spot,
                futures_price=futures_ltp,
                vwap=vwap,
                vwap_distance=vwap_dist,
                pcr=pcr,
                atr=atr,
                atm_strike=atm,
                atm_data=atm_data,
                ce_total_5m=ce_5m,
                pe_total_5m=pe_5m,
                ce_total_15m=ce_15m,
                pe_total_15m=pe_15m,
                atm_ce_5m=atm_ce_5m,
                atm_pe_5m=atm_pe_5m,
                atm_ce_15m=atm_ce_15m,
                atm_pe_15m=atm_pe_15m,
                has_5m_total=has_5m,
                has_15m_total=has_15m,
                has_5m_atm=has_atm_5m,
                has_15m_atm=has_atm_15m,
                volume_spike=vol_spike,
                volume_ratio=vol_ratio,
                order_flow=order_flow,
                candle_data=candle,
                gamma_zone=gamma,
                momentum=momentum,
                multi_tf=multi_tf,
                oi_strength=oi_strength,
                oi_scenario=oi_scenario
            )
            
            if not signal:
                logger.info("  ⏹️ No valid setup at this time")
                return
            
            # Validate signal
            should_execute, reason = self.signal_validator.should_execute(signal)
            
            if not should_execute:
                logger.info(f"  🚫 Signal rejected: {reason}")
                return
            
            # Execute signal
            logger.info("🔔 SIGNAL GENERATED!")
            await self._execute_signal(signal)
            
        except Exception as e:
            logger.error(f"❌ Scan error: {e}", exc_info=True)
    
    async def _execute_signal(self, signal):
        """Execute trading signal"""
        try:
            signal_type = str(signal.signal_type.value)
            
            # Format Telegram message
            msg = MessageFormatter.format_entry_signal(signal)
            
            if self.telegram.is_enabled():
                await self.telegram.send(msg)
            
            # Record signal
            self.signal_validator.record_signal(signal)
            self.position_tracker.open_position(signal)
            
            self.in_position = True
            self.current_signal = signal
            
            logger.info(f"📝 Position opened: {signal_type} @ ₹{signal.option_premium:.2f}")
            
        except Exception as e:
            logger.error(f"❌ Signal execution error: {e}")
    
    async def run(self):
        """Main bot loop"""
        self.is_running = True
        
        try:
            while self.is_running:
                await self.scan_market()
                await asyncio.sleep(SCAN_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("⚠️ Keyboard interrupt received")
        except Exception as e:
            logger.error(f"❌ Bot error: {e}", exc_info=True)
        finally:
            await self.shutdown()


# ==================== Main Entry Point ====================
async def main():
    """Bot entry point"""
    bot = NiftyTradingBot()
    
    try:
        await bot.initialize()
        await bot.run()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        if bot.telegram.is_enabled():
            await bot.telegram.send(f"❌ <b>Bot Error</b>\n\n{str(e)[:500]}")


if __name__ == "__main__":
    asyncio.run(main())
