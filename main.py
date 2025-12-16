"""
NIFTY Trading Bot - Main Orchestrator
FIXED: ATM OI bug, VWAP validation, volume calculation
"""

import asyncio
from datetime import datetime

from config import *
from utils import *
from expiry_utils import get_next_weekly_expiry, get_next_monthly_expiry, format_expiry_display
from data_manager import UpstoxClient, RedisBrain, DataFetcher, InMemoryOITracker
from analyzers import OIAnalyzer, VolumeAnalyzer, TechnicalAnalyzer, MarketAnalyzer
from signal_engine import SignalGenerator, SignalValidator
from position_tracker import PositionTracker
from alerts import TelegramBot, MessageFormatter

BOT_VERSION = "5.1.0-FIXED"

logger = setup_logger("main")


class NiftyTradingBot:
    """Main bot orchestrator - FIXED EDITION"""
    
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
        self.formatter = MessageFormatter()
        
        self.exit_triggered_this_cycle = False
    
    async def initialize(self):
        """Initialize bot with startup notification"""
        logger.info("=" * 60)
        logger.info(f"🚀 NIFTY Trading Bot v{BOT_VERSION}")
        logger.info("=" * 60)
        
        self.upstox = UpstoxClient()
        await self.upstox.__aenter__()
        
        self.data_fetcher = DataFetcher(self.upstox)
        
        weekly_expiry = get_next_weekly_expiry()
        weekly_display = format_expiry_display(weekly_expiry)
        monthly_expiry = self.upstox.futures_expiry.strftime('%Y-%m-%d') if self.upstox.futures_expiry else "AUTO"
        futures_contract = self.upstox.futures_symbol if self.upstox.futures_symbol else "NIFTY FUTURES"
        
        current_time = format_time_ist(get_ist_time())
        
        example_atm = 24150
        deep_strikes = get_deep_analysis_strikes(example_atm)
        deep_range = f"{deep_strikes[0]}-{deep_strikes[-1]}"
        
        fetch_min, fetch_max = get_strike_range_fetch(example_atm)
        
        startup_msg = f"""
🚀 <b>NIFTY BOT v{BOT_VERSION}</b>

━━━━━━━━━━━━━━━━━━━━
🔧 <b>BUG FIXES IN THIS VERSION</b>
━━━━━━━━━━━━━━━━━━━━

✅ ATM OI 0.0% bug FIXED
✅ VWAP validation strengthened
✅ Volume calculation improved
✅ PE_BUY direction validation

━━━━━━━━━━━━━━━━━━━━
🆕 <b>PRICE-AWARE OI ANALYSIS</b>
━━━━━━━━━━━━━━━━━━━━

<b>6 OI Scenarios Detected:</b>

<b>STRONG Signals (Fresh Money):</b>
1️⃣ CE Long Buildup (OI↑ + Price↑)
2️⃣ PE Short Buildup (OI↑ + Price↓)

<b>WEAK Signals (Profit Booking):</b>
3️⃣ CE Short Covering (OI↓ + Price↑)
4️⃣ CE Long Unwinding (OI↓ + Price↓)
5️⃣ PE Short Covering (OI↓ + Price↓)
6️⃣ PE Long Unwinding (OI↓ + Price↑)

━━━━━━━━━━━━━━━━━━━━
📅 <b>CONTRACT DETAILS</b>
━━━━━━━━━━━━━━━━━━━━

<b>Futures (MONTHLY):</b>
• Contract: {futures_contract}
• Expiry: {monthly_expiry}

<b>Options (WEEKLY):</b>
• Expiry: {weekly_expiry}
• Display: {weekly_display}
• 🔄 Auto-selected (Nearest Tuesday)

━━━━━━━━━━━━━━━━━━━━
📊 <b>DATA STRATEGY</b>
━━━━━━━━━━━━━━━━━━━━

<b>MONTHLY Futures:</b>
✅ Candles for VWAP/ATR/EMA
✅ LIVE price for decisions
✅ Price history tracking

<b>WEEKLY Options:</b>
✅ Fetch: 11 strikes (ATM ± 5)
✅ Deep: 5 strikes (ATM ± 2)
✅ Total OI + Price context

━━━━━━━━━━━━━━━━━━━━
🔧 <b>TIMING &amp; WARMUP</b>
━━━━━━━━━━━━━━━━━━━━

• First Data: 9:16 AM
• Early Signals: 9:21 AM (≥85%)
• Full Signals: 9:31 AM (≥70%)
• Warmup: {WARMUP_MINUTES} min
• Scan: {SCAN_INTERVAL}s

━━━━━━━━━━━━━━━━━━━━
⚙️ <b>OI THRESHOLDS</b>
━━━━━━━━━━━━━━━━━━━━

<b>Entry:</b>
• 5m OI: &lt; -{MIN_OI_5M_FOR_ENTRY}%
• 15m OI: &lt; -{MIN_OI_15M_FOR_ENTRY}%

<b>Strong:</b>
• 5m: &lt; -{STRONG_OI_5M_THRESHOLD}%
• 15m: &lt; -{STRONG_OI_15M_THRESHOLD}%

━━━━━━━━━━━━━━━━━━━━
🎯 <b>RISK MANAGEMENT</b>
━━━━━━━━━━━━━━━━━━━━

• Premium SL: {PREMIUM_SL_PERCENT}%
• Trailing SL: {'ON' if ENABLE_TRAILING_SL else 'OFF'}
• Min Confidence: {MIN_CONFIDENCE}%

━━━━━━━━━━━━━━━━━━━━
⏰ Started at {current_time}
"""
        
        if self.telegram.is_enabled():
            await self.telegram.send(startup_msg)
        
        logger.info("✅ Bot initialized (FIXED)")
        logger.info(f"📅 Monthly: {futures_contract}")
        logger.info(f"📅 Weekly: {weekly_expiry}")
        logger.info("=" * 60)
    
    async def shutdown(self):
        """Shutdown bot"""
        logger.info("🛑 Shutting down...")
        self.running = False
        
        if self.upstox:
            await self.upstox.__aexit__(None, None, None)
        
        logger.info("✅ Shutdown complete")
    
    async def run(self):
        """Main loop"""
        self.running = True
        
        try:
            await self.initialize()
            
            while self.running:
                try:
                    await self._cycle()
                except Exception as e:
                    logger.error(f"❌ Cycle error: {e}", exc_info=True)
                
                await asyncio.sleep(SCAN_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("⚠️ Keyboard interrupt")
        finally:
            await self.shutdown()
    
    async def _cycle(self):
        """Single scan cycle - FIXED VERSION"""
        now = get_ist_time()
        status, _ = get_market_status()
        current_time = now.time()
        
        self.exit_triggered_this_cycle = False
        
        logger.info(f"\n{'='*60}")
        logger.info(f"⏰ {format_time_ist(now)} | {status}")
        logger.info(f"{'='*60}")
        
        if is_market_closed():
            logger.info("🌙 Market closed")
            return
        
        if is_premarket():
            logger.info("🌅 Premarket - waiting for 9:16 AM")
            await self.memory.load_previous_day_data()
            return
        
        if current_time >= time(9, 15) and current_time < time(9, 16):
            logger.info("⏭️ Skipping 9:15 AM")
            return
        
        logger.info("📥 Fetching market data...")
        
        # ========== FETCH DATA ==========
        
        spot = await self.data_fetcher.fetch_spot()
        if not validate_price(spot):
            logger.error("❌ Spot validation failed")
            return
        logger.info(f"  ✅ Spot: ₹{spot:.2f}")
        
        futures_df = await self.data_fetcher.fetch_futures_candles()
        if not validate_candle_data(futures_df):
            logger.error("❌ Futures candles validation failed")
            return
        logger.info(f"  ✅ Futures Candles: {len(futures_df)} bars")
        
        futures_ltp = await self.data_fetcher.fetch_futures_ltp()
        if not validate_price(futures_ltp):
            logger.error("❌ Live Futures price validation failed")
            return
        logger.info(f"  ✅ Futures LIVE: ₹{futures_ltp:.2f}")
        
        # Save price & get change
        self.memory.save_price(futures_ltp)
        
        price_5m, has_price_5m = self.memory.get_price_change(5)
        price_15m, has_price_15m = self.memory.get_price_change(15)
        price_stats = self.memory.get_price_stats()
        
        logger.info(f"  🆕 Price Changes:")
        logger.info(f"     5m:  {price_5m:+.2f}% {'✅' if has_price_5m else '⏳'}")
        logger.info(f"     15m: {price_15m:+.2f}% {'✅' if has_price_15m else '⏳'}")
        logger.info(f"     From Open: {price_stats['change_from_open']:+.2f}%")
        
        option_result = await self.data_fetcher.fetch_option_chain(spot)
        if not option_result:
            logger.error("❌ Option chain returned None")
            return
        
        atm, strike_data = option_result
        if not validate_strike_data(strike_data):
            logger.error(f"❌ Strike validation failed")
            return
        
        deep_strikes = get_deep_analysis_strikes(atm)
        logger.info(f"  ✅ Strikes: {len(strike_data)} total (ATM {atm})")
        logger.info(f"  🔍 Deep: {len(deep_strikes)} strikes")
        
        futures_price = futures_ltp
        logger.info(f"\n💹 Prices: Spot={spot:.2f}, Futures={futures_price:.2f}, ATM={atm}")
        
        # ========== SAVE OI SNAPSHOTS ==========
        
        logger.info("🔄 Saving OI snapshots...")
        total_ce, total_pe = self.oi_analyzer.calculate_total_oi(strike_data)
        deep_ce, deep_pe, _ = self.oi_analyzer.calculate_deep_analysis_oi(strike_data, atm)
        
        self.memory.save_total_oi(total_ce, total_pe)
        
        for strike, data in strike_data.items():
            self.memory.save_strike(strike, data)
        
        logger.info(f"  ✅ Total OI: CE={total_ce:,.0f}, PE={total_pe:,.0f}")
        logger.info(f"  🔍 Deep OI: CE={deep_ce:,.0f}, PE={deep_pe:,.0f}")
        
        # ========== 🔧 FIX #1: ATM OI CALCULATION ==========
        
        logger.info("📊 Calculating OI changes...")
        
        # 🆕 USE IN-MEMORY TRACKER instead of Redis
        prev_total_ce, prev_total_pe, prev_atm_ce, prev_atm_pe, has_history = self.oi_tracker.get_comparison(minutes_ago=5)
        
        if has_history:
            # Calculate 5-minute changes
            ce_5m = ((total_ce - prev_total_ce) / prev_total_ce * 100) if prev_total_ce > 0 else 0.0
            pe_5m = ((total_pe - prev_total_pe) / prev_total_pe * 100) if prev_total_pe > 0 else 0.0
            has_5m = True
            
            # ATM changes
            atm_data = self.oi_analyzer.get_atm_data(strike_data, atm)
            current_atm_ce = atm_data.get('ce_oi', 0)
            current_atm_pe = atm_data.get('pe_oi', 0)
            
            atm_ce_5m = ((current_atm_ce - prev_atm_ce) / prev_atm_ce * 100) if prev_atm_ce > 0 else 0.0
            atm_pe_5m = ((current_atm_pe - prev_atm_pe) / prev_atm_pe * 100) if prev_atm_pe > 0 else 0.0
            has_atm_5m = True
        else:
            ce_5m = pe_5m = atm_ce_5m = atm_pe_5m = 0.0
            has_5m = has_atm_5m = False
        
        # Get 15-minute comparison
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
        
        # 🆕 SAVE current snapshot for next comparison
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
        vwap_dist = self.technical_analyzer.calculate_vwap_distance(futures_price, vwap) if vwap else 0
        candle = self.technical_analyzer.analyze_candle(futures_df)
        momentum = self.technical_analyzer.detect_momentum(futures_df)
        
        vol_trend = self.volume_analyzer.analyze_volume_trend(futures_df, futures_ltp=futures_ltp)
        
        # ⚠️ VOLUME DISABLED (Upstox API returns stale data)
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
        
        logger.info(f"\n📊 TECHNICAL SUMMARY:")
        logger.info(f"  PCR: {pcr:.2f}, VWAP: ₹{vwap:.2f}, ATR: {atr:.1f}")
        logger.info(f"  Price vs VWAP: {vwap_dist:+.1f} pts")
        logger.info(f"  Volume: {vol_ratio:.1f}x {'🔥SPIKE' if vol_spike else ''}")
        logger.info(f"  Flow: {order_flow:.2f}, Momentum: {momentum['direction']}")
        logger.info(f"  OI Strength: {oi_strength}")
        
        # ========== WARMUP CHECK ==========
        
        stats = self.memory.get_stats()
        logger.info(f"\n⏱️  WARMUP STATUS:")
        if stats['first_snapshot_time']:
            logger.info(f"  Base: {stats['first_snapshot_time'].strftime('%H:%M')}")
        logger.info(f"  Elapsed: {stats['elapsed_minutes']:.1f} min")
        logger.info(f"  5m: {'✅' if stats['warmed_up_5m'] else '⏳'}")
        logger.info(f"  15m: {'✅' if stats['warmed_up_15m'] else '⏳'}")
        
        full_warmup = stats['warmed_up_15m']
        early_warmup = stats['warmed_up_5m'] and stats['elapsed_minutes'] >= 5
        
        if not full_warmup and not early_warmup:
            remaining = WARMUP_MINUTES - stats['elapsed_minutes']
            logger.info(f"\n🚫 SIGNALS BLOCKED - {remaining:.1f} min remaining")
            return
        
        if full_warmup:
            logger.info(f"\n✅ FULL WARMUP COMPLETE")
        else:
            logger.info(f"\n⚡ EARLY WARMUP READY")
        
        # ========== EXIT CHECK ==========
        
        if self.position_tracker.has_active_position():
            logger.info(f"📍 Checking exit conditions...")
            
            current_data = {
                'ce_oi_5m': ce_5m,
                'pe_oi_5m': pe_5m,
                'volume_ratio': vol_ratio,
                'candle_data': candle,
                'futures_price': futures_price,
                'atm_data': atm_data
            }
            
            exit_check = self.position_tracker.check_exit_conditions(current_data)
            
            if exit_check:
                should_exit, reason, details = exit_check
                
                if reason == "SL_UPDATED" and not should_exit:
                    if self.telegram.is_enabled():
                        msg = f"🔒 <b>TRAILING SL UPDATED</b>\n\n{details}"
                        await self.telegram.send_update(msg)
                    logger.info(f"📢 Trailing SL: {details}")
                
                elif should_exit:
                    exit_premium = self.position_tracker._estimate_premium(current_data, 
                        self.position_tracker.active_position.signal)
                    
                    self.signal_validator.record_exit(
                        self.position_tracker.active_position.signal.signal_type,
                        self.position_tracker.active_position.signal.atm_strike
                    )
                    
                    self.position_tracker.close_position(reason, details, exit_premium)
                    
                    if self.telegram.is_enabled():
                        msg = self.formatter.format_exit_signal(
                            self.position_tracker.closed_positions[-1],
                            reason, details
                        )
                        await self.telegram.send_exit(msg)
                    
                    logger.info(f"🚪 EXIT: {reason} - {details}")
                    self.exit_triggered_this_cycle = True
            else:
                logger.info(f"✅ Position holding")
        
        # ========== ENTRY SIGNAL ==========
        
        if self.exit_triggered_this_cycle:
            logger.info(f"\n⏸️ EXIT triggered - skipping entry")
            return
        
        signal_allowed, signal_msg = is_signal_time(warmup_complete=full_warmup or early_warmup)
        
        if not self.position_tracker.has_active_position() and signal_allowed:
            logger.info(f"\n🔎 SIGNAL GENERATION:")
            logger.info(f"  Checking for entry...")
            
            signal = self.signal_gen.generate(
                spot_price=spot, 
                futures_price=futures_price,
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
                multi_tf=unwinding['multi_timeframe'],
                oi_strength=oi_strength,
                oi_scenario=oi_scenario
            )
            
            if not full_warmup and signal:
                if signal.confidence < EARLY_SIGNAL_CONFIDENCE:
                    logger.info(f"  ⚡ Early signal {signal.confidence}% < {EARLY_SIGNAL_CONFIDENCE}%")
                    signal = None
            
            validated = self.signal_validator.validate(signal)
            
            if validated:
                logger.info(f"\n🔔 SIGNAL GENERATED!")
                logger.info(f"  Type: {validated.signal_type.value}")
                logger.info(f"  Entry: ₹{validated.entry_price:.2f}")
                logger.info(f"  Confidence: {validated.confidence}%")
                logger.info(f"  VWAP Score: {validated.vwap_score}/100")
                logger.info(f"  OI Strength: {validated.oi_strength}")
                
                if hasattr(validated, 'oi_scenario_type') and validated.oi_scenario_type:
                    logger.info(f"  🆕 OI Scenario: {validated.oi_scenario_type}")
                
                if not full_warmup:
                    logger.info(f"  ⚡ EARLY SIGNAL")
                
                self.position_tracker.open_position(validated)
                
                if self.telegram.is_enabled():
                    msg = self.formatter.format_entry_signal(validated)
                    if not full_warmup:
                        msg = f"⚡ <b>EARLY SIGNAL</b>\n\n" + msg
                    
                    if hasattr(validated, 'oi_scenario_type') and validated.oi_scenario_type:
                        msg += f"\n\n🔥 <b>OI Scenario:</b> {validated.oi_scenario_type}"
                    
                    await self.telegram.send_signal(msg)
            else:
                logger.info(f"  ✋ No valid setup")
        elif not signal_allowed:
            logger.info(f"\n⏰ {signal_msg}")
        elif self.position_tracker.has_active_position():
            logger.info(f"\n📍 Position active")


async def main():
    bot = NiftyTradingBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
