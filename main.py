"""
NIFTY 50 Trading Bot - Main Orchestrator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strategy: Price + OI + PCR Combined
Based on: 9 Scenarios PDF Guide
Author: Yellow Flash
Version: 1.0
"""

import asyncio
import logging
from datetime import datetime

# Import modules
from config import *
from utils import *
from data_manager import DataManager
from analyzers import MarketAnalyzer
from signal_engine import SignalEngine
from alerts import TelegramBot

# Setup logger
logger = setup_logger()

class NiftyTradingBot:
    """Main trading bot orchestrator"""
    
    def __init__(self):
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"🤖 Initializing {BOT_NAME} v{BOT_VERSION}")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # Initialize components
        self.data_manager = DataManager()
        self.market_analyzer = MarketAnalyzer(self.data_manager)
        self.signal_engine = SignalEngine()
        self.telegram = TelegramBot()
        
        # State
        self.is_running = False
        self.scan_count = 0
        self.current_signal = None
        
        logger.info("✅ All components initialized")
    
    async def initialize(self):
        """Initialize bot and connections"""
        logger.info("")
        logger.info("🔧 Running initialization checks...")
        
        # Validate config
        errors = validate_config()
        if errors:
            logger.error("❌ Configuration errors found:")
            for error in errors:
                logger.error(f"   - {error}")
            return False
        
        logger.info("✅ Configuration valid")
        
        # Test Telegram
        if SEND_TELEGRAM_ALERTS:
            try:
                await self.telegram.send_startup_message()
                logger.info("✅ Telegram connection OK")
            except Exception as e:
                logger.error(f"❌ Telegram test failed: {e}")
                return False
        
        # Check market status
        market_status = get_market_status()
        logger.info(f"📊 Market Status: {market_status}")
        
        logger.info("")
        logger.info("✅ Initialization complete!")
        logger.info("")
        
        return True
    
    async def scan_market(self):
        """Main market scanning loop"""
        self.scan_count += 1
        now = get_ist_time()
        
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"⏰ SCAN #{self.scan_count} | {now.strftime('%H:%M:%S')} IST")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 1: Fetch Market Data
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            logger.info("📥 Fetching market data...")
            
            # Get spot price
            spot_price = await self.data_manager.fetch_spot_price()
            if not spot_price:
                logger.error("❌ Failed to fetch spot price")
                return
            
            logger.info(f"  ✅ NIFTY Spot: ₹{spot_price:.2f}")
            
            # Get futures price
            futures_price = await self.data_manager.fetch_futures_price()
            if not futures_price:
                logger.warning("⚠️ Futures price unavailable, using spot")
                futures_price = spot_price
            else:
                logger.info(f"  ✅ NIFTY Futures: ₹{futures_price:.2f}")
            
            # Get option chain
            option_chain = await self.data_manager.fetch_option_chain(spot_price)
            if not option_chain:
                logger.error("❌ Failed to fetch option chain")
                return
            
            logger.info(f"  ✅ Option Chain: {len(option_chain['strikes'])} strikes")
            logger.info(f"  ✅ PCR: {option_chain['pcr']:.3f}")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 2: Check Data Availability
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            status = self.data_manager.get_status()
            
            if not status['has_data']:
                logger.info(f"⏳ Building history: {status['history_count']}/{MIN_HISTORY_FOR_SIGNAL}")
                return
            
            logger.info(f"  ✅ History: {status['history_count']} data points")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 3: Market Analysis
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            logger.info("")
            logger.info("🔍 Running market analysis...")
            
            # Calculate VWAP (simplified - you'd get from candles)
            vwap = futures_price  # Placeholder
            
            # Run comprehensive analysis
            analysis = self.market_analyzer.comprehensive_analysis(
                option_chain,
                futures_price,
                vwap
            )
            
            # Log analysis summary
            logger.info(f"")
            logger.info(f"📊 MARKET SUMMARY:")
            logger.info(f"  Price: ₹{analysis['price']:.2f} ({analysis['price_change']:+.1f} pts)")
            logger.info(f"  PCR: {analysis['pcr']['pcr']:.3f} ({analysis['pcr']['zone']})")
            logger.info(f"  OI: CE={analysis['oi']['ce_change']:+.1f}%, PE={analysis['oi']['pe_change']:+.1f}%")
            logger.info(f"  Interpretation: {analysis['oi']['interpretation']}")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 4: Signal Generation
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            signal = self.signal_engine.generate_signal(analysis)
            
            if signal and signal.signal_type != SignalType.NO_TRADE:
                # Send alert
                await self.telegram.send_signal_alert(signal)
                self.current_signal = signal
            
            logger.info("")
            
        except Exception as e:
            logger.error(f"❌ Error in scan_market: {e}")
            await self.telegram.send_error_alert(f"Scan error: {str(e)}")
    
    async def run(self):
        """Main bot loop"""
        logger.info("")
        logger.info("🚀 Starting bot main loop...")
        logger.info("")
        
        self.is_running = True
        
        while self.is_running:
            try:
                # Check if market is open
                if not is_trading_hours():
                    if self.scan_count == 0:
                        logger.info("⏸️ Market not open yet. Waiting...")
                    await asyncio.sleep(60)  # Check every minute
                    continue
                
                # Check if first scan of the day
                now = get_ist_time()
                if now.time() >= TRADING_START and self.scan_count == 0:
                    logger.info("📈 Trading hours started!")
                    self.signal_engine.reset_daily_count()
                
                # Run market scan
                await self.scan_market()
                
                # Wait for next scan
                await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                
                # Check if market closing
                if now.time() >= TRADING_END:
                    logger.info("📴 Trading hours ended")
                    
                    # Send daily summary (if implemented)
                    # await self.telegram.send_daily_summary({})
                    
                    # Wait until next day
                    self.scan_count = 0
                    await asyncio.sleep(3600)  # Sleep 1 hour
            
            except KeyboardInterrupt:
                logger.info("⚠️ Keyboard interrupt received")
                break
            
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """Start the bot"""
        # Initialize
        if not await self.initialize():
            logger.error("❌ Initialization failed. Exiting.")
            return
        
        # Run main loop
        await self.run()
    
    def stop(self):
        """Stop the bot"""
        logger.info("🛑 Stopping bot...")
        self.is_running = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    """Main entry point"""
    bot = NiftyTradingBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("⚠️ Keyboard interrupt")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        bot.stop()
        logger.info("👋 Bot stopped. Goodbye!")

if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
