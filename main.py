"""
NIFTY Trading Bot - Main Orchestrator
FIXED: Data flow order, ATM OI tracking, exit-before-entry prevention
"""

import asyncio
from datetime import datetime

# Import all modules
from config import *
from utils import *
from data_manager import UpstoxClient, RedisBrain, DataFetcher
from analyzers import OIAnalyzer, VolumeAnalyzer, TechnicalAnalyzer, MarketAnalyzer
from signal_engine import SignalGenerator, SignalValidator
from position_tracker import PositionTracker
from alerts import TelegramBot, MessageFormatter

BOT_VERSION = "3.1.0-FIXED"

logger = setup_logger("main")


# ==================== Main Bot ====================
class NiftyTradingBot:
    """Main bot orchestrator with FIXED logic"""
    
    def __init__(self):
        # Core components
        self.memory = RedisBrain()
        self.upstox = None
        self.data_fetcher = None
        
        # Analyzers
        self.oi_analyzer = OIAnalyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.technical_analyzer = TechnicalAnalyzer()
        self.market_analyzer = MarketAnalyzer()
        
        # Signal & Position
        self.signal_gen = SignalGenerator()
        self.signal_validator = SignalValidator()
        self.position_tracker = PositionTracker()
        
        # Alerts
        self.telegram = TelegramBot()
        self.formatter = MessageFormatter()
        
        # State tracking - NEW
        self.previous_strike_data = None  # ✅ Track previous scan for ATM OI changes
        self.exit_triggered_this_cycle = False
    
    async def initialize(self):
        """Initialize bot with startup notification"""
        logger.info("=" * 60)
        logger.info(f"🚀 NIFTY Trading Bot v{BOT_VERSION}")
        logger.info("=" * 60)
        
        self.upstox = UpstoxClient()
        await self.upstox.__aenter__()
        
        self.data_fetcher = DataFetcher(self.upstox)
        
        # Send startup notification
        next_expiry = get_next_tuesday_expiry()
        futures_contract = get_futures_contract_name()
        current_time = format_time_ist(get_ist_time())
        
        startup_msg = f"""
🚀 <b>NIFTY BOT v{BOT_VERSION} STARTED</b>

📅 <b>Contract Details:</b>
• Next Expiry: {next_expiry}
• Futures: {futures_contract}
• Strike Range: ATM ± 5 (11 strikes)

🔧 <b>Configuration:</b>
• First Data: 9:16 AM (skip 9:15 freak trades)
• Warmup: {WARMUP_MINUTES} min from first snapshot
• Signal Window: 9:21 AM - 3:15 PM
• Scan Interval: {SCAN_INTERVAL}s
• Memory TTL: {MEMORY_TTL_HOURS}h

⚙️ <b>Risk Management:</b>
• Premium SL: {PREMIUM_SL_PERCENT}%
• Trailing SL: {'Enabled' if ENABLE_TRAILING_SL else 'Disabled'}
• Signal Cooldown: {SIGNAL_COOLDOWN_SECONDS}s
• Min Confidence: {MIN_CONFIDENCE}%
• Min Hold Time: {MIN_HOLD_TIME_MINUTES}min

🎯 <b>Thresholds (FIXED):</b>
• OI 5m/15m: {MIN_OI_5M_FOR_ENTRY}% / {MIN_OI_15M_FOR_ENTRY}%
• Exit OI Reversal: {EXIT_OI_REVERSAL_THRESHOLD}%
• Volume Spike: {VOL_SPIKE_MULTIPLIER}x
• VWAP Strict Mode: {'ON' if VWAP_STRICT_MODE else 'OFF'}

⏰ Bot started at {current_time}
"""
        
        if self.telegram.is_enabled():
            await self.telegram.send(startup_msg)
        
        logger.info("✅ Bot initialized")
        logger.info(f"📅 Next Expiry: {next_expiry}")
        logger.info(f"📊 Futures: {futures_contract}")
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
        """Single scan cycle - FIXED ORDER"""
        now = get_ist_time()
        status, _ = get_market_status()
        current_time = now.time()
        
        # Reset cycle flag
        self.exit_triggered_this_cycle = False
        
        logger.info(f"\n{'='*60}")
        logger.info(f"⏰ {format_time_ist(now)} | {status}")
        logger.info(f"{'='*60}")
        
        # Market closed
        if is_market_closed():
            logger.info("🌙 Market closed")
            return
        
        # Premarket
        if is_premarket():
            logger.info("🌅 Premarket - waiting for 9:16 AM")
            await self.memory.load_previous_day_data()
            return
        
        # Skip 9:15 (freak trades)
        if current_time >= time(9, 15) and current_time < time(9, 16):
            logger.info("⏭️ Skipping 9:15 AM (freak trade prevention)")
            return
        
        logger.info("📥 Fetching market data...")
        
        # ========== STEP 1: FETCH ALL DATA ==========
        
        # Fetch spot
        spot = await self.data_fetcher.fetch_spot()
        if not validate_price(spot):
            logger.error("❌ STOP: Spot validation failed")
            return
        logger.info(f"  ✅ Spot: ₹{spot:.2f}")
        
        # Fetch futures
        futures_df = await self.data_fetcher.fetch_futures()
        if not validate_candle_data(futures_df):
            logger.error("❌ STOP: Futures validation failed")
            return
        logger.info(f"  ✅ Futures: {len(futures_df)} candles")
        
        # Fetch option chain
        option_result = await self.data_fetcher.fetch_option_chain(spot)
        if not option_result:
            logger.error("❌ STOP: Option chain returned None")
            return
        
        atm, strike_data = option_result
        if not validate_strike_data(strike_data):
            logger.error(f"❌ STOP: Strike validation failed. Keys: {list(strike_data.keys()) if strike_data else 'None'}")
            return
        logger.info(f"  ✅ Strikes: {len(strike_data)} strikes around ATM {atm}")
        
        futures_price = futures_df['close'].iloc[-1]
        logger.info(f"\n💹 Prices: Spot={spot:.2f}, Futures={futures_price:.2f}, ATM={atm}")
        
        # ========== STEP 2: SAVE OI SNAPSHOTS (BEFORE CALCULATIONS) ==========
        
        logger.info("🔄 Saving OI snapshots...")
        total_ce, total_pe = self.oi_analyzer.calculate_total_oi(strike_data)
        self.memory.save_total_oi(total_ce, total_pe)
        
        for strike, data in strike_data.items():
            self.memory.save_strike(strike, data)
        
        logger.info(f"  ✅ Saved: CE={total_ce:,.0f}, PE={total_pe:,.0f}")
        
        # ========== STEP 3: CALCULATE OI CHANGES ==========
        
        logger.info("📊 Calculating OI changes...")
        
        # Total OI changes
        ce_5m, pe_5m, has_5m = self.memory.get_total_oi_change(total_ce, total_pe, 5)
        ce_15m, pe_15m, has_15m = self.memory.get_total_oi_change(total_ce, total_pe, 15)
        
        # ✅ ATM OI changes (FIXED - using previous_strike_data)
        atm_info = self.oi_analyzer.get_atm_oi_changes(
            strike_data, 
            atm, 
            self.previous_strike_data  # Pass previous scan data
        )
        
        # Also get from memory for redundancy
        atm_data = self.oi_analyzer.get_atm_data(strike_data, atm)
        atm_ce_5m, atm_pe_5m, has_atm_5m = self.memory.get_strike_oi_change(atm, atm_data, 5)
        atm_ce_15m, atm_pe_15m, has_atm_15m = self.memory.get_strike_oi_change(atm, atm_data, 15)
        
        # Use memory values if atm_info doesn't have previous data
        if not atm_info['has_previous_data']:
            atm_info['ce_change_pct'] = atm_ce_15m
            atm_info['pe_change_pct'] = atm_pe_15m
        
        logger.info(f"  5m:  CE={ce_5m:+.1f}% PE={pe_5m:+.1f}% {'✅' if has_5m else '⏳'}")
        logger.info(f"  15m: CE={ce_15m:+.1f}% PE={pe_15m:+.1f}% {'✅' if has_15m else '⏳'}")
        logger.info(f"  ATM {atm}: CE={atm_info['ce_change_pct']:+.1f}% PE={atm_info['pe_change_pct']:+.1f}%")
        
        # ✅ Store current strike_data for next cycle
        self.previous_strike_data = strike_data.copy()
        
        # ========== STEP 4: RUN ANALYSIS ==========
        
        logger.info("🔍 Running technical analysis...")
        
        pcr = self.oi_analyzer.calculate_pcr(total_pe, total_ce)
        vwap = self.technical_analyzer.calculate_vwap(futures_df)
        atr = self.technical_analyzer.calculate_atr(futures_df)
        vwap_dist = self.technical_analyzer.calculate_vwap_distance(futures_price, vwap) if vwap else 0
        candle = self.technical_analyzer.analyze_candle(futures_df)
        momentum = self.technical_analyzer.detect_momentum(futures_df)
        
        vol_trend = self.volume_analyzer.analyze_volume_trend(futures_df)
        vol_spike, vol_ratio = self.volume_analyzer.detect_volume_spike(
            vol_trend['current_volume'], vol_trend['avg_volume']
        )
        order_flow = self.volume_analyzer.calculate_order_flow(strike_data)
        
        gamma = self.market_analyzer.detect_gamma_zone()
        unwinding = self.oi_analyzer.detect_unwinding(ce_5m, ce_15m, pe_5m, pe_15m)
        
        # Determine OI strength
        if ce_15m < -STRONG_OI_15M_THRESHOLD or pe_15m < -STRONG_OI_15M_THRESHOLD:
            oi_strength = 'strong'
        elif ce_15m < -MIN_OI_15M_FOR_ENTRY or pe_15m < -MIN_OI_15M_FOR_ENTRY:
            oi_strength = 'medium'
        else:
            oi_strength = 'weak'
        
        # Log analysis
        logger.info(f"\n📊 ANALYSIS COMPLETE:")
        logger.info(f"  📈 PCR: {pcr:.2f}, VWAP: ₹{vwap:.2f}, ATR: {atr:.1f}")
        logger.info(f"  📍 Price vs VWAP: {vwap_dist:+.1f} pts")
        logger.info(f"  🔄 OI Changes:")
        logger.info(f"     5m:  CE {ce_5m:+.1f}% | PE {pe_5m:+.1f}%")
        logger.info(f"     15m: CE {ce_15m:+.1f}% | PE {pe_15m:+.1f}% (Strength: {oi_strength})")
        logger.info(f"  📊 Volume: {vol_ratio:.1f}x {'🔥SPIKE' if vol_spike else ''}")
        logger.info(f"  💨 Flow: {order_flow:.2f}, Momentum: {momentum['direction']}")
        logger.info(f"  🎯 Gamma Zone: {gamma}")
        
        # ========== STEP 5: CHECK WARMUP ==========
        
        stats = self.memory.get_stats()
        logger.info(f"\n⏱️  WARMUP STATUS:")
        if stats['first_snapshot_time']:
            logger.info(f"  Base Time: {stats['first_snapshot_time'].strftime('%H:%M')}")
        logger.info(f"  Elapsed: {stats['elapsed_minutes']:.1f} min")
        logger.info(f"  5m Ready: {'✅' if stats['warmed_up_5m'] else '⏳'}")
        logger.info(f"  10m Ready: {'✅' if stats['warmed_up_10m'] else '⏳'}")
        logger.info(f"  15m Ready: {'✅' if stats['warmed_up_15m'] else '⏳'}")
        
        full_warmup = stats['warmed_up_15m']
        early_warmup = stats['warmed_up_5m'] and stats['elapsed_minutes'] >= 5
        
        if not full_warmup and not early_warmup:
            remaining = WARMUP_MINUTES - stats['elapsed_minutes']
            logger.info(f"\n🚫 SIGNALS BLOCKED - Warmup: {remaining:.1f} min remaining")
            return
        
        if full_warmup:
            logger.info(f"\n✅ FULL WARMUP COMPLETE - All signals active!")
        else:
            logger.info(f"\n⚡ EARLY WARMUP READY - High confidence signals only!")
        
        # ========== STEP 6: CHECK EXIT CONDITIONS ==========
        
        if self.position_tracker.has_active_position():
            logger.info(f"📍 Active position exists - checking exit...")
            
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
                
                # Handle SL update notification (not exit)
                if reason == "SL_UPDATED" and not should_exit:
                    if self.telegram.is_enabled():
                        msg = f"🔒 <b>TRAILING SL UPDATED</b>\n\n{details}"
                        await self.telegram.send_update(msg)
                    logger.info(f"📢 Trailing SL updated: {details}")
                
                # Handle actual exit
                elif should_exit:
                    # Estimate exit premium
                    exit_premium = self.position_tracker._estimate_premium(current_data, 
                        self.position_tracker.active_position.signal)
                    
                    # Record exit in validator for re-entry protection
                    self.signal_validator.record_exit(
                        self.position_tracker.active_position.signal.signal_type,
                        self.position_tracker.active_position.signal.atm_strike
                    )
                    
                    self.position_tracker.close_position(reason, details, exit_premium)
                    
                    # Send exit alert
                    if self.telegram.is_enabled():
                        msg = self.formatter.format_exit_signal(
                            self.position_tracker.closed_positions[-1],
                            reason, details
                        )
                        await self.telegram.send_exit(msg)
                    
                    logger.info(f"🚪 EXIT TRIGGERED: {reason} - {details}")
                    
                    # ✅ Mark exit triggered - prevent entry this cycle
                    self.exit_triggered_this_cycle = True
            else:
                logger.info(f"✅ Position holding - no exit conditions met")
        
        # ========== STEP 7: GENERATE ENTRY SIGNAL ==========
        
        # ✅ Skip entry if exit happened this cycle
        if self.exit_triggered_this_cycle:
            logger.info(f"\n⏸️ EXIT TRIGGERED THIS CYCLE - Skipping entry check")
            return
        
        signal_allowed, signal_msg = is_signal_time(warmup_complete=full_warmup or early_warmup)
        
        if not self.position_tracker.has_active_position() and signal_allowed:
            logger.info(f"\n🔎 SIGNAL GENERATION:")
            logger.info(f"  No active position - checking for entry...")
            
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
                atm_ce_5m=atm_info['ce_change_pct'], 
                atm_pe_5m=atm_info['pe_change_pct'],
                atm_ce_15m=atm_ce_15m, 
                atm_pe_15m=atm_pe_15m,
                has_5m_total=has_5m, 
                has_15m_total=has_15m,
                has_5m_atm=has_atm_5m or atm_info['has_previous_data'], 
                has_15m_atm=has_atm_15m,
                volume_spike=vol_spike, 
                volume_ratio=vol_ratio,
                order_flow=order_flow, 
                candle_data=candle,
                gamma_zone=gamma, 
                momentum=momentum,
                multi_tf=unwinding['multi_timeframe'],
                oi_strength=oi_strength
            )
            
            # Apply higher threshold for early signals
            if not full_warmup and signal:
                if signal.confidence < EARLY_SIGNAL_CONFIDENCE:
                    logger.info(f"  ⚡ Early signal {signal.confidence}% < {EARLY_SIGNAL_CONFIDENCE}% threshold")
                    signal = None
            
            validated = self.signal_validator.validate(signal)
            
            if validated:
                logger.info(f"\n🔔 SIGNAL GENERATED!")
                logger.info(f"  Type: {validated.signal_type.value}")
                logger.info(f"  Entry: ₹{validated.entry_price:.2f}")
                logger.info(f"  Confidence: {validated.confidence}%")
                logger.info(f"  VWAP Score: {validated.vwap_score}/100")
                logger.info(f"  OI Strength: {validated.oi_strength}")
                if not full_warmup:
                    logger.info(f"  ⚡ EARLY SIGNAL (High Confidence)")
                
                # Open position
                self.position_tracker.open_position(validated)
                
                # Send alert
                if self.telegram.is_enabled():
                    msg = self.formatter.format_entry_signal(validated)
                    if not full_warmup:
                        msg = f"⚡ <b>EARLY SIGNAL</b> (High Confidence)\n\n" + msg
                    await self.telegram.send_signal(msg)
            else:
                logger.info(f"  ✋ No valid setup found")
        elif not signal_allowed:
            logger.info(f"\n⏰ {signal_msg}")
        elif self.position_tracker.has_active_position():
            logger.info(f"\n📍 Position already active - not generating new signals")


# ==================== Entry Point ====================
async def main():
    bot = NiftyTradingBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
