"""
NIFTY Trading Bot - Main Orchestrator
ULTIMATE FIX: Active strikes filtering, ATM OI tracking, exit-before-entry prevention
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
from alerts import TelegramBot

logger = setup_logger("main")


# ==================== Main Bot ====================
class NIFTYBot:
    """Main trading bot orchestrator with ACTIVE STRIKES filtering"""
    
    def __init__(self):
        self.client = None
        self.fetcher = None
        self.memory = RedisBrain()
        
        self.oi_analyzer = OIAnalyzer()
        self.vol_analyzer = VolumeAnalyzer()
        self.tech_analyzer = TechnicalAnalyzer()
        self.market_analyzer = MarketAnalyzer()
        
        self.signal_gen = SignalGenerator()
        self.signal_validator = SignalValidator()
        self.position_tracker = PositionTracker()
        
        self.telegram = TelegramBot() if TELEGRAM_ENABLED else None
        
        self.warmup_start_time = None
        self.scan_count = 0
        
        # ✅ NEW: Track previous strike data for ATM OI changes
        self.previous_strike_data = None
        self.previous_scan_time = None
    
    async def initialize(self):
        """Initialize bot"""
        logger.info("=" * 60)
        logger.info("🚀 NIFTY Trading Bot - ULTIMATE FIXED VERSION")
        logger.info("=" * 60)
        logger.info("")
        logger.info("📋 Configuration:")
        logger.info(f"   Storage: {STORAGE_STRIKE_RANGE * 2 + 1} strikes (ATM ± {STORAGE_STRIKE_RANGE})")
        logger.info(f"   Analysis: {ANALYSIS_STRIKE_RANGE * 2 + 1} strikes (ATM ± {ANALYSIS_STRIKE_RANGE})")
        logger.info(f"   OI Thresholds: 5m={MIN_OI_5M_FOR_ENTRY}%, 15m={MIN_OI_15M_FOR_ENTRY}%")
        logger.info(f"   Exit OI Threshold: {EXIT_OI_REVERSAL_THRESHOLD}%")
        logger.info(f"   Volume Spike: {VOL_SPIKE_MULTIPLIER}x")
        logger.info(f"   VWAP Strict Mode: {VWAP_STRICT_MODE}")
        logger.info(f"   Min Hold Time: {MIN_HOLD_TIME_MINUTES} min")
        logger.info("")
        
        self.client = UpstoxClient()
        await self.client.__aenter__()
        
        self.fetcher = DataFetcher(self.client)
        
        if not self.client.spot_key or not self.client.futures_key:
            logger.error("❌ Failed to detect instruments")
            return False
        
        logger.info("✅ Initialization complete")
        logger.info("")
        
        return True
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.client:
            await self.client.__aexit__(None, None, None)
    
    async def run(self):
        """Main bot loop"""
        if not await self.initialize():
            return
        
        if self.telegram:
            await self.telegram.send_startup_notification()
        
        try:
            while True:
                now = datetime.now(IST)
                current_time = now.time()
                
                if not is_market_open(current_time):
                    if current_time < PREMARKET_START:
                        wait = (datetime.combine(now.date(), PREMARKET_START) - now).total_seconds()
                        logger.info(f"💤 Market opens in {wait/60:.0f} min")
                        await asyncio.sleep(min(wait, 300))
                    else:
                        logger.info("🏁 Market closed for the day")
                        break
                    continue
                
                market_state = get_market_state(current_time)
                await self.scan_cycle(market_state)
                
                await asyncio.sleep(SCAN_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("\n⏹️ Shutting down...")
        
        finally:
            await self.cleanup()
            logger.info("👋 Bot stopped")
    
    async def scan_cycle(self, market_state):
        """Single scan cycle with ACTIVE STRIKES filtering"""
        self.scan_count += 1
        now = datetime.now(IST)
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"⏰ {now.strftime('%I:%M:%S %p')} IST | {market_state.upper()}")
        logger.info("=" * 60)
        
        # Step 1: Fetch data
        logger.info("📥 Fetching market data...")
        
        spot = await self.fetcher.fetch_spot()
        if not spot:
            logger.error("❌ Spot fetch failed")
            return
        logger.info(f"   ✅ Spot: ₹{spot:.2f}")
        
        futures_df = await self.fetcher.fetch_futures()
        if futures_df is None or len(futures_df) == 0:
            logger.error("❌ Futures candles failed")
            return
        logger.info(f"   ✅ Futures Candles: {len(futures_df)} bars (for VWAP/EMA)")
        
        futures_ltp = await self.fetcher.fetch_futures_ltp()
        if not futures_ltp:
            logger.error("❌ Futures LTP failed")
            return
        logger.info(f"   ✅ Futures LIVE: ₹{futures_ltp:.2f} (REAL-TIME)")
        
        candle_close = futures_df['close'].iloc[-1]
        diff = futures_ltp - candle_close
        logger.info(f"   📊 Price Check: Candle Close={candle_close:.2f}, Live={futures_ltp:.2f}, Diff={diff:+.2f}")
        
        result = await self.fetcher.fetch_option_chain(spot)
        if not result:
            logger.error("❌ Option chain failed")
            return
        
        atm, strike_data = result
        logger.info(f"   ✅ Strikes: {len(strike_data)} strikes around ATM {atm}")
        logger.info("")
        logger.info(f"💹 Prices: Spot={spot:.2f}, Futures(LIVE)={futures_ltp:.2f}, ATM={atm}")
        
        # ✅ Step 2: Save OI snapshots (ALL 11 strikes)
        logger.info("🔄 Saving OI snapshots...")
        ce_total_oi, pe_total_oi = self.oi_analyzer.calculate_total_oi(strike_data)
        self.memory.save_total_oi(ce_total_oi, pe_total_oi)
        
        for strike, data in strike_data.items():
            self.memory.save_strike(strike, data)
        
        logger.info(f"   ✅ Saved: CE={ce_total_oi:,.0f}, PE={pe_total_oi:,.0f}")
        
        # ✅ Step 3: Calculate OI changes
        logger.info("📊 Calculating OI changes...")
        
        ce_total_5m, pe_total_5m, has_5m_total = self.memory.get_total_oi_change(ce_total_oi, pe_total_oi, 5)
        ce_total_15m, pe_total_15m, has_15m_total = self.memory.get_total_oi_change(ce_total_oi, pe_total_oi, 15)
        
        atm_data = self.oi_analyzer.get_atm_data(strike_data, atm)
        
        # ✅ NEW: Get ATM OI changes using previous scan data
        atm_info = self.oi_analyzer.get_atm_oi_changes(
            strike_data,
            atm,
            self.previous_strike_data  # Compare with previous
        )
        
        # Fallback to Redis memory if no previous
        atm_ce_5m, atm_pe_5m, has_5m_atm = self.memory.get_strike_oi_change(atm, atm_data, 5)
        atm_ce_15m, atm_pe_15m, has_15m_atm = self.memory.get_strike_oi_change(atm, atm_data, 15)
        
        # Use scan-to-scan comparison if available
        if atm_info['has_previous_data']:
            logger.info(f"   ✅ ATM OI changes from previous scan")
            atm_ce_pct = atm_info['ce_change_pct']
            atm_pe_pct = atm_info['pe_change_pct']
        else:
            logger.info(f"   ⚠️ Using Redis memory for ATM changes")
            atm_ce_pct = atm_ce_15m
            atm_pe_pct = atm_pe_15m
        
        logger.info(f"   5m:  CE={ce_total_5m:+.1f}% PE={pe_total_5m:+.1f}% {'✅' if has_5m_total else '⏳'}")
        logger.info(f"   15m: CE={ce_total_15m:+.1f}% PE={pe_total_15m:+.1f}% {'✅' if has_15m_total else '⏳'}")
        logger.info(f"   ATM {atm}: CE={atm_ce_pct:+.1f}% PE={atm_pe_pct:+.1f}%")
        
        # ✅ Step 4: Filter to ACTIVE STRIKES (ATM ± 2)
        active_strike_data = self.oi_analyzer.get_active_strikes_for_analysis(strike_data, atm)
        
        # Calculate metrics on ACTIVE strikes only
        ce_active_oi, pe_active_oi = self.oi_analyzer.calculate_total_oi(active_strike_data)
        pcr = self.oi_analyzer.calculate_pcr(pe_active_oi, ce_active_oi)
        
        ce_vol, pe_vol = self.vol_analyzer.calculate_total_volume(active_strike_data)
        order_flow = self.vol_analyzer.calculate_order_flow(active_strike_data)
        
        vol_trend = self.vol_analyzer.analyze_volume_trend(futures_df)
        volume_spike, volume_ratio = self.vol_analyzer.detect_volume_spike(
            vol_trend['current_volume'], 
            vol_trend['avg_volume']
        )
        
        # ✅ Step 5: Technical analysis
        logger.info("🔍 Running technical analysis...")
        
        vwap = self.tech_analyzer.calculate_vwap(futures_df)
        vwap_distance = self.tech_analyzer.calculate_vwap_distance(futures_ltp, vwap)
        atr = self.tech_analyzer.calculate_atr(futures_df)
        candle_data = self.tech_analyzer.analyze_candle(futures_df)
        momentum = self.tech_analyzer.detect_momentum(futures_df)
        
        unwinding = self.oi_analyzer.detect_unwinding(ce_total_5m, ce_total_15m, pe_total_5m, pe_total_15m)
        gamma_zone = self.market_analyzer.detect_gamma_zone()
        
        logger.info("")
        logger.info("📊 ANALYSIS COMPLETE:")
        logger.info(f"   📈 PCR: {pcr:.2f}, VWAP: ₹{vwap:.2f}, ATR: {atr:.1f}")
        logger.info(f"   📍 Price vs VWAP: {vwap_distance:+.1f} pts (LIVE price used)")
        logger.info(f"   🔄 OI Changes:")
        logger.info(f"      5m:  CE {ce_total_5m:+.1f}% | PE {pe_total_5m:+.1f}%")
        logger.info(f"      15m: CE {ce_total_15m:+.1f}% | PE {pe_total_15m:+.1f}% (Strength: {unwinding.get('pe_strength', 'weak')})")
        logger.info(f"   📊 Volume: {volume_ratio:.1f}x {'✅' if volume_spike else ''}")
        logger.info(f"   💨 Flow: {order_flow:.2f}, Momentum: {momentum['direction']}")
        logger.info(f"   🎯 Gamma Zone: {gamma_zone}")
        
        # ✅ Step 6: Warmup status
        stats = self.memory.get_stats()
        logger.info("")
        logger.info("⏱️  WARMUP STATUS:")
        
        if stats['first_snapshot_time']:
            logger.info(f"   Base Time: {stats['first_snapshot_time'].strftime('%H:%M')}")
            logger.info(f"   Elapsed: {stats['elapsed_minutes']:.1f} min")
            logger.info(f"   5m Ready: {'✅' if stats['warmed_up_5m'] else '⏳'}")
            logger.info(f"   10m Ready: {'✅' if stats['warmed_up_10m'] else '⏳'}")
            logger.info(f"   15m Ready: {'✅' if stats['warmed_up_15m'] else '⏳'}")
        else:
            logger.info("   ⏳ Collecting first snapshot...")
        
        full_warmup = stats['warmed_up_15m']
        
        if full_warmup:
            logger.info("")
            logger.info("✅ FULL WARMUP COMPLETE - All signals active!")
        
        # ✅ Step 7: Position tracking (check exit BEFORE entry)
        logger.info("")
        logger.info("🔎 SIGNAL GENERATION:")
        
        exit_triggered = False
        
        if self.position_tracker.has_active_position():
            logger.info("   Checking exit conditions...")
            
            current_data = {
                'futures_price': futures_ltp,
                'futures_df': futures_df,
                'vwap': vwap,
                'atr': atr,
                'candle_data': candle_data,
                'ce_oi_5m': ce_total_5m,
                'pe_oi_5m': pe_total_5m,
                'ce_oi_15m': ce_total_15m,
                'pe_oi_15m': pe_total_15m,
                'volume_ratio': volume_ratio,
                'atm_data': atm_data
            }
            
            should_exit, exit_reason, exit_details = self.position_tracker.check_exit_conditions(current_data)
            
            if should_exit:
                exit_triggered = True
                position = self.position_tracker.current_position
                
                await self.position_tracker.exit_position(exit_reason, exit_details)
                
                # ✅ Record exit for re-entry protection
                self.signal_validator.record_exit(position.signal.signal_type, position.signal.atm_strike)
                
                if self.telegram:
                    await self.telegram.send_exit_alert(
                        position,
                        exit_reason,
                        exit_details
                    )
        
        # ✅ Step 8: Entry signal (only if no exit in this cycle)
        if not self.position_tracker.has_active_position() and not exit_triggered:
            logger.info("   No active position - checking for entry...")
            
            signal = self.signal_gen.generate(
                spot_price=spot,
                futures_price=futures_ltp,
                vwap=vwap,
                vwap_distance=vwap_distance,
                pcr=pcr,
                atr=atr,
                atm_strike=atm,
                atm_data=atm_data,
                active_strike_data=active_strike_data,  # ✅ Pass active strikes
                ce_total_5m=ce_total_5m,
                pe_total_5m=pe_total_5m,
                ce_total_15m=ce_total_15m,
                pe_total_15m=pe_total_15m,
                atm_ce_5m=atm_ce_5m,
                atm_pe_5m=atm_pe_5m,
                atm_ce_15m=atm_ce_pct,  # Use scan-to-scan if available
                atm_pe_15m=atm_pe_pct,
                has_5m_total=has_5m_total,
                has_15m_total=has_15m_total,
                has_5m_atm=has_5m_atm,
                has_15m_atm=has_15m_atm or atm_info['has_previous_data'],
                volume_spike=volume_spike,
                volume_ratio=volume_ratio,
                order_flow=order_flow,
                candle_data=candle_data,
                gamma_zone=gamma_zone,
                momentum=momentum,
                multi_tf=unwinding['multi_timeframe'],
                oi_strength=unwinding.get('pe_strength', 'weak') if pe_total_15m < ce_total_15m else unwinding.get('ce_strength', 'weak')
            )
            
            # Early signal confidence adjustment
            if signal and not full_warmup:
                if signal.confidence < EARLY_SIGNAL_CONFIDENCE:
                    logger.info(f"   ⏳ Early signal confidence too low: {signal.confidence}% < {EARLY_SIGNAL_CONFIDENCE}%")
                    signal = None
            
            validated_signal = self.signal_validator.validate(signal)
            
            if validated_signal:
                self.position_tracker.enter_position(validated_signal)
                
                if self.telegram:
                    await self.telegram.send_signal_alert(validated_signal)
            else:
                logger.info("   ✋ No valid setup found")
        
        elif exit_triggered:
            logger.info("   ⏸️ Exit triggered this cycle - skipping entry check")
        
        # ✅ Step 9: Store current data for next scan (ATM OI comparison)
        self.previous_strike_data = strike_data.copy()
        self.previous_scan_time = now


# ==================== Entry Point ====================
async def main():
    """Entry point"""
    bot = NIFTYBot()
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Goodbye!")
