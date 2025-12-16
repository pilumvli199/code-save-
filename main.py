"""
NIFTY Trading Bot - Main Orchestrator v7.0 - COMPREHENSIVE FIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆕 INTEGRATED:
1. 30m OI comparison
2. OI Velocity analysis
3. OTM strike analysis
4. All validation fixes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
from datetime import datetime

from config import *
from utils import *
from data_manager import UpstoxClient, RedisBrain, DataFetcher, InMemoryOITracker
from analyzers import OIAnalyzer, VolumeAnalyzer, TechnicalAnalyzer, MarketAnalyzer
from signal_engine import SignalGenerator, SignalValidator
from position_tracker import PositionTracker
from alerts import TelegramBot, MessageFormatter

BOT_VERSION = "7.0-COMPREHENSIVE-FIX"

logger = setup_logger("main")


class NiftyTradingBot:
    """Main bot orchestrator - v7.0 COMPREHENSIVE FIX"""
    
    def __init__(self):
        # 🆕 In-Memory OI Tracker with 35-scan capacity
        self.oi_tracker = InMemoryOITracker()
        
        # Redis Brain for price tracking
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
        
        try:
            # Initialize Upstox
            logger.info("📡 Connecting to Upstox API...")
            self.upstox = UpstoxClient()
            success = await self.upstox.initialize()
            
            if not success:
                error_msg = "❌ Failed to initialize Upstox client - Check API credentials!"
                logger.error(error_msg)
                if self.telegram.is_enabled():
                    await self.telegram.send(f"<b>⚠️ Bot Startup Failed</b>\n\n{error_msg}")
                raise Exception(error_msg)
            
            logger.info("✅ Upstox API connected")
            
            # Initialize data fetcher
            logger.info("📊 Initializing data fetcher...")
            self.data_fetcher = DataFetcher(self.upstox)
            logger.info("✅ Data fetcher ready")
            
            # Get contract details
            logger.info("📅 Loading contract details...")
            futures_contract = self.upstox.futures_symbol if self.upstox.futures_symbol else "NIFTY FUTURES"
            
            # Get expiry dates properly
            weekly_expiry_str = self.upstox.weekly_expiry.strftime('%d-%b-%Y (%A)') if self.upstox.weekly_expiry else "Auto"
            futures_expiry_str = self.upstox.futures_expiry.strftime('%d-%b-%Y') if self.upstox.futures_expiry else "Auto"
            futures_days = (self.upstox.futures_expiry - get_ist_time()).days if self.upstox.futures_expiry else 0
            
            logger.info(f"  📌 Futures: {futures_contract} (Expiry: {futures_expiry_str}, {futures_days} days left)")
            logger.info(f"  📌 Options: Weekly expiry {weekly_expiry_str}")
            logger.info(f"")
            logger.info(f"  ℹ️  DATA SOURCES:")
            logger.info(f"     📊 Candles: From MONTHLY futures ({futures_contract})")
            logger.info(f"     📈 Option Chain: From WEEKLY options (Exp: {weekly_expiry_str})")
            logger.info(f"     ✅ Analysis: OI + Price from both combined")
            
            current_time = format_time_ist(get_ist_time())
            
            example_atm = 24150
            deep_strikes = get_deep_analysis_strikes(example_atm)
            deep_range = f"{deep_strikes[0]}-{deep_strikes[-1]}"
            
            fetch_min, fetch_max = get_strike_range_fetch(example_atm)
            otm_above, otm_below = get_otm_strikes(example_atm)
            
            # Build startup message
            logger.info("📱 Preparing Telegram startup message...")
            
            # Escape HTML special characters for Telegram
            def escape_html(text):
                """Escape HTML special characters"""
                return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            startup_msg = f"""
🚀 <b>NIFTY BOT v{BOT_VERSION}</b>

━━━━━━━━━━━━━━━━━━━━
🔧 <b>v7.0 COMPREHENSIVE FIX</b>
━━━━━━━━━━━━━━━━━━━━

✅ 30m OI comparison
✅ OI Velocity (4 patterns)
✅ OTM strike analysis
✅ VWAP strict validation
✅ Reversal detection
✅ Trap detection
✅ Time filter (3:00 PM cutoff)

━━━━━━━━━━━━━━━━━━━━
📅 <b>CONTRACT DETAILS</b>
━━━━━━━━━━━━━━━━━━━━

<b>Futures (MONTHLY):</b>
• {escape_html(futures_contract)}
• Expiry: {escape_html(futures_expiry_str)}
• Days Left: {futures_days}

<b>Options (WEEKLY):</b>
• Expiry: {escape_html(weekly_expiry_str)}
• Strike Gap: ₹{STRIKE_GAP}

━━━━━━━━━━━━━━━━━━━━
📊 <b>OI ANALYSIS ENGINE</b>
━━━━━━━━━━━━━━━━━━━━

<b>Multi-Timeframe OI:</b>
• 5m (Momentum)
• 15m (Trend Confirmation)
• 🆕 30m (Velocity Pattern)

<b>Strike Coverage:</b>
• Fetch: {fetch_min}-{fetch_max} (11 strikes)
• Deep Analysis: {deep_range} (5 strikes)
• 🆕 OTM: {otm_above}/{otm_below} (Support/Resistance)

<b>🆕 OI Velocity Patterns:</b>
• Acceleration (15m &gt; 30m) → Speed ↑
• Monster Loading (both &gt; 8%) → Explosive
• Deceleration (15m &lt; 30m) → Speed ↓
• Exhaustion (30m high, 15m low) → Slowing

<b>OI Scenarios:</b>
• Support Bounce (CE↑ Price↑)
• Resistance Reject (PE↑ Price↓)
• Bull/Bear Trap Detection
• Strong Bull/Bear Patterns

━━━━━━━━━━━━━━━━━━━━
🎯 <b>SIGNAL FILTERS</b>
━━━━━━━━━━━━━━━━━━━━

<b>Primary Checks (need 2/3):</b>
✅ Multi-TF OI unwinding (5m+15m)
✅ ATM OI threshold: {ATM_OI_THRESHOLD}%
✅ Volume confirmation

<b>VWAP Validation:</b>
• Min Score: {MIN_VWAP_SCORE}/100 (strict)
• CE_BUY: Price MUST be &gt; VWAP
• PE_BUY: Price MUST be &lt; VWAP

<b>PCR Bias Bands:</b>
• &lt; {PCR_OVERHEATED}: OVERHEATED (avoid CE)
• {PCR_BALANCED_BULL}-{PCR_NEUTRAL_HIGH}: NEUTRAL
• &gt; {PCR_OVERSOLD}: OVERSOLD (avoid PE)

<b>Additional Filters:</b>
• Reversal: Both ATM unwinding → NO_TRADE
• Trap: One-sided spike → NO_TRADE
• Time: No new trades after 3:00 PM

━━━━━━━━━━━━━━━━━━━━
⚙️ <b>RISK MANAGEMENT</b>
━━━━━━━━━━━━━━━━━━━━

<b>Entry:</b>
• Min Confidence: {MIN_CONFIDENCE}%
• ATR Target: {ATR_TARGET_MULTIPLIER}x
• ATR Stop: {ATR_SL_MULTIPLIER}x

<b>Exit:</b>
• Trailing SL: {int(TRAILING_SL_DISTANCE * 100)}% from peak
• Min Hold: {MIN_HOLD_TIME_MINUTES} min
• Max Loss: {PREMIUM_SL_PERCENT}% of premium

━━━━━━━━━━━━━━━━━━━━
💾 <b>MEMORY STATUS</b>
━━━━━━━━━━━━━━━━━━━━

OI Tracker: {OI_MEMORY_SCANS} scans capacity
Warmup: 5m ⏳ | 15m ⏳ | 30m ⏳

━━━━━━━━━━━━━━━━━━━━
⏰ <b>BOT STARTED</b>
━━━━━━━━━━━━━━━━━━━━

{current_time}

🔄 Scan Interval: {SCAN_INTERVAL}s
📡 Ready for market data...
"""
            
            # Send startup message
            if self.telegram.is_enabled():
                logger.info("📤 Sending startup message to Telegram...")
                sent = await self.telegram.send(startup_msg)
                if sent:
                    logger.info("✅ Startup message sent to Telegram")
                else:
                    logger.warning("⚠️ Failed to send Telegram message (check bot token/chat ID)")
            else:
                logger.info("⏸️ Telegram disabled - Skipping startup message")
            
            logger.info("✅ Bot initialized (v7.0 COMPREHENSIVE FIX)")
            logger.info(f"📅 Futures: {futures_contract}")
            logger.info("=" * 60)
            
        except Exception as e:
            error_msg = f"❌ Initialization failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if self.telegram.is_enabled():
                await self.telegram.send(f"<b>⚠️ Bot Startup Failed</b>\n\n{error_msg[:500]}")
            raise
    
    async def shutdown(self):
        """Shutdown bot"""
        logger.info("🛑 Shutting down...")
        
        if self.telegram.is_enabled():
            await self.telegram.send("🛑 <b>Bot Stopped</b>")
        
        self.is_running = False
        logger.info("✅ Shutdown complete")
    
    async def scan_market(self):
        """Single market scan with 30m OI support"""
        try:
            now_ist = get_ist_time()
            time_str = format_time_ist(now_ist)
            market_status = "OPEN" if is_market_open() else "CLOSED"
            
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"⏰ SCAN #{self.oi_tracker.get_status()['scans']+1} | {time_str} | {market_status}")
            logger.info("=" * 60)
            
            if market_status == "CLOSED":
                logger.info("⏸️ Market closed - Skipping scan")
                return
            
            # ========== DATA FETCHING ==========
            
            logger.info("📥 Fetching market data...")
            
            spot = await self.data_fetcher.fetch_spot()
            if not spot:
                logger.error("❌ Failed to fetch spot price")
                return
            
            logger.info(f"  ✅ Spot: ₹{spot:.2f}")
            
            futures_df = await self.data_fetcher.fetch_futures_candles()
            if futures_df is None:
                logger.error("❌ Failed to fetch futures candles")
                return
            
            logger.info(f"  ✅ Futures Candles: {len(futures_df)} bars")
            
            futures_ltp = await self.data_fetcher.fetch_futures_ltp()
            if not futures_ltp:
                logger.error("❌ Failed to fetch futures LTP")
                return
            
            logger.info(f"  ✅ Futures LIVE: ₹{futures_ltp:.2f}")
            
            # Save price
            self.memory.save_price(futures_ltp)
            
            # Price changes
            price_5m, has_price_5m = self.memory.get_price_change(futures_ltp, 5)
            price_15m, has_price_15m = self.memory.get_price_change(futures_ltp, 15)
            price_30m, has_price_30m = self.memory.get_price_change(futures_ltp, 30)
            
            logger.info(f"")
            logger.info(f"📈 PRICE CHANGES:")
            logger.info(f"  5m:  {price_5m:+.2f}% {'✅' if has_price_5m else '⏳'}")
            logger.info(f"  15m: {price_15m:+.2f}% {'✅' if has_price_15m else '⏳'}")
            logger.info(f"  30m: {price_30m:+.2f}% {'✅' if has_price_30m else '⏳'}")
            
            # ========== OPTION CHAIN ==========
            
            logger.info("")
            logger.info("📡 Fetching option chain...")
            
            option_result = await self.data_fetcher.fetch_option_chain(spot)
            
            if not option_result:
                logger.error("❌ Failed to fetch option chain")
                return
            
            strike_data, atm, total_ce, total_pe = option_result
            
            logger.info(f"  ✅ Strikes: {len(strike_data)} total (ATM {atm})")
            logger.info(f"  ✅ Total OI: CE={total_ce:,.0f}, PE={total_pe:,.0f}")
            
            # Deep OI
            deep_ce, deep_pe, deep_strikes = self.oi_analyzer.calculate_deep_analysis_oi(strike_data, atm)
            logger.info(f"  🔍 Deep OI: CE={deep_ce:,.0f}, PE={deep_pe:,.0f}")
            
            # ========== OI CALCULATION (5m, 15m, 30m) ==========
            
            logger.info("")
            logger.info("📊 CALCULATING OI CHANGES...")
            
            # Get ATM data first
            atm_data = self.oi_analyzer.get_atm_data(strike_data, atm)
            current_atm_ce = atm_data.get('ce_oi', 0)
            current_atm_pe = atm_data.get('pe_oi', 0)
            
            # 5-minute comparison
            prev_total_ce_5m, prev_total_pe_5m, prev_atm_ce_5m, prev_atm_pe_5m, has_5m = self.oi_tracker.get_comparison(minutes_ago=5)
            
            if has_5m:
                ce_5m = ((total_ce - prev_total_ce_5m) / prev_total_ce_5m * 100) if prev_total_ce_5m > 0 else 0.0
                pe_5m = ((total_pe - prev_total_pe_5m) / prev_total_pe_5m * 100) if prev_total_pe_5m > 0 else 0.0
                
                atm_ce_5m = ((current_atm_ce - prev_atm_ce_5m) / prev_atm_ce_5m * 100) if prev_atm_ce_5m > 0 else 0.0
                atm_pe_5m = ((current_atm_pe - prev_atm_pe_5m) / prev_atm_pe_5m * 100) if prev_atm_pe_5m > 0 else 0.0
            else:
                ce_5m = pe_5m = atm_ce_5m = atm_pe_5m = 0.0
            
            # 15-minute comparison
            prev_total_ce_15m, prev_total_pe_15m, prev_atm_ce_15m, prev_atm_pe_15m, has_15m = self.oi_tracker.get_comparison(minutes_ago=15)
            
            if has_15m:
                ce_15m = ((total_ce - prev_total_ce_15m) / prev_total_ce_15m * 100) if prev_total_ce_15m > 0 else 0.0
                pe_15m = ((total_pe - prev_total_pe_15m) / prev_total_pe_15m * 100) if prev_total_pe_15m > 0 else 0.0
                
                atm_ce_15m = ((current_atm_ce - prev_atm_ce_15m) / prev_atm_ce_15m * 100) if prev_atm_ce_15m > 0 else 0.0
                atm_pe_15m = ((current_atm_pe - prev_atm_pe_15m) / prev_atm_pe_15m * 100) if prev_atm_pe_15m > 0 else 0.0
            else:
                ce_15m = pe_15m = atm_ce_15m = atm_pe_15m = 0.0
            
            # 30-minute comparison
            prev_total_ce_30m, prev_total_pe_30m, prev_atm_ce_30m, prev_atm_pe_30m, has_30m = self.oi_tracker.get_comparison(minutes_ago=30)
            
            if has_30m:
                ce_30m = ((total_ce - prev_total_ce_30m) / prev_total_ce_30m * 100) if prev_total_ce_30m > 0 else 0.0
                pe_30m = ((total_pe - prev_total_pe_30m) / prev_total_pe_30m * 100) if prev_total_pe_30m > 0 else 0.0
            else:
                ce_30m = pe_30m = 0.0
            
            # Save current snapshot
            self.oi_tracker.save_snapshot(
                total_ce=total_ce,
                total_pe=total_pe,
                atm_strike=atm,
                atm_ce_oi=current_atm_ce,
                atm_pe_oi=current_atm_pe
            )
            
            # Display tracker status
            tracker_status = self.oi_tracker.get_status()
            logger.info(f"  💾 Tracker: {tracker_status['scans']}/{OI_MEMORY_SCANS} scans | 5m✅ 15m{'✅' if tracker_status['ready_15m'] else '⏳'} 30m{'✅' if tracker_status['ready_30m'] else '⏳'}")
            
            logger.info(f"")
            logger.info(f"  TOTAL OI CHANGES:")
            logger.info(f"    5m:  CE={ce_5m:+.1f}% PE={pe_5m:+.1f}% {'✅' if has_5m else '⏳'}")
            logger.info(f"    15m: CE={ce_15m:+.1f}% PE={pe_15m:+.1f}% {'✅' if has_15m else '⏳'}")
            logger.info(f"    30m: CE={ce_30m:+.1f}% PE={pe_30m:+.1f}% {'✅' if has_30m else '⏳'}")
            
            logger.info(f"")
            logger.info(f"  ATM {atm} OI CHANGES:")
            logger.info(f"    15m: CE={atm_ce_15m:+.1f}% PE={atm_pe_15m:+.1f}% {'✅' if has_15m else '⏳'}")
            
            # ========== PRICE-AWARE OI ANALYSIS ==========
            
            logger.info("\n🔥 PRICE-AWARE OI ANALYSIS:")
            
            oi_scenario = self.oi_analyzer.analyze_oi_with_price(
                ce_5m=ce_5m,
                ce_15m=ce_15m,
                pe_5m=pe_5m,
                pe_15m=pe_15m,
                price_change_pct=price_5m if has_price_5m else 0.0
            )
            
            logger.info(f"  📊 Pattern: {oi_scenario['human_name']}")
            logger.info(f"  🎯 Direction: {oi_scenario['primary_direction']}")
            logger.info(f"  💪 Confidence Boost: {oi_scenario['confidence_boost']:+d}%")
            
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
            
            # ========== 🆕 OI VELOCITY ANALYSIS ==========
            
            logger.info("\n🚀 OI VELOCITY ANALYSIS:")
            
            ce_velocity, ce_vel_strength, ce_vel_desc, ce_vel_conf = self.oi_analyzer.classify_oi_velocity(
                ce_5m, ce_15m, ce_30m, has_30m, 'CE'
            )
            
            pe_velocity, pe_vel_strength, pe_vel_desc, pe_vel_conf = self.oi_analyzer.classify_oi_velocity(
                pe_5m, pe_15m, pe_30m, has_30m, 'PE'
            )
            
            logger.info(f"  📞 CE: {ce_velocity} ({ce_vel_strength}) | {ce_vel_desc}")
            logger.info(f"  📞 PE: {pe_velocity} ({pe_vel_strength}) | {pe_vel_desc}")
            
            # ========== TECHNICAL ANALYSIS ==========
            
            logger.info("\n🔍 Running technical analysis...")
            
            pcr = self.oi_analyzer.calculate_pcr(total_pe, total_ce)
            vwap = self.technical_analyzer.calculate_vwap(futures_df)
            atr = self.technical_analyzer.calculate_atr(futures_df)
            vwap_dist = self.technical_analyzer.calculate_vwap_distance(futures_ltp, vwap) if vwap else 0
            candle = self.technical_analyzer.analyze_candle(futures_df)
            momentum = self.technical_analyzer.detect_momentum(futures_df)
            
            vol_spike, vol_ratio = False, 1.0
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
            logger.info(f"  Candle: {candle['color']} | OI Strength: {oi_strength}")
            
            # ========== SIGNAL GENERATION ==========
            
            logger.info("\n🎯 Checking for entry setup...")
            
            if self.in_position:
                logger.info("  ⏸️ Already in position - Skipping")
                return
            
            # 🔥 NEW: Check warmup status
            tracker_status = self.oi_tracker.get_status()
            is_fully_warmed = tracker_status['ready_15m']  # 15m warmup
            current_time = get_ist_time().time()
            is_early_time = SIGNAL_START <= current_time < time(9, 31)  # 9:21 - 9:30 = early period
            
            if not is_fully_warmed:
                if is_early_time:
                    logger.info(f"  ⚡ EARLY SIGNAL MODE: Need {EARLY_SIGNAL_CONFIDENCE}%+ confidence")
                else:
                    logger.info(f"  ⏳ Warmup incomplete: {tracker_status['elapsed_min']:.0f}/{WARMUP_MINUTES} min")
                    logger.info(f"     5m: {'✅' if tracker_status['ready_5m'] else '⏳'} | 15m: {'✅' if tracker_status['ready_15m'] else '⏳'}")
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
                strike_data=strike_data,  # 🆕 NEW: Pass for OTM analysis
                ce_total_5m=ce_5m,
                pe_total_5m=pe_5m,
                ce_total_15m=ce_15m,
                pe_total_15m=pe_15m,
                ce_total_30m=ce_30m,  # 🆕 NEW
                pe_total_30m=pe_30m,  # 🆕 NEW
                atm_ce_5m=atm_ce_5m,
                atm_pe_5m=atm_pe_5m,
                atm_ce_15m=atm_ce_15m,
                atm_pe_15m=atm_pe_15m,
                has_5m_total=has_5m,
                has_15m_total=has_15m,
                has_30m_total=has_30m,  # 🆕 NEW
                has_5m_atm=has_5m,
                has_15m_atm=has_15m,
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
            
            # 🔥 NEW: Early signal filter (9:21-9:30)
            if is_early_time and not is_fully_warmed:
                if signal.confidence < EARLY_SIGNAL_CONFIDENCE:
                    logger.info(f"  🚫 Early signal rejected: Confidence {signal.confidence}% < {EARLY_SIGNAL_CONFIDENCE}% (early threshold)")
                    return
                else:
                    logger.info(f"  ⚡ EARLY HIGH-CONFIDENCE SIGNAL: {signal.confidence}% ≥ {EARLY_SIGNAL_CONFIDENCE}%")
            
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
