#!/usr/bin/env python3
"""Daily Charging Recommendation Script

Analyzes next-day electricity prices and carbon intensity to provide
optimal charging recommendations. Runs daily at 16:00 via launchd.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.octopus_api import OctopusAPIClient
from modules.carbon_api import CarbonAPIClient
from modules.forecast_api import ForecastAPIClient
from modules.data_store import DataStore
from modules.pushover import PushoverClient
from modules.analyzer import (
    Analyzer,
    PriceSlot,
    CarbonSlot,
    ChargingWindow,
    OpportunityRating,
    WindowStatus,
)
import yaml
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/daily_notification.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml and .env

    Returns:
        Configuration dictionary
    """
    load_dotenv()

    config_path = Path("config/config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Add environment variables
    config["apis"]["pushover"]["user_key"] = os.getenv("PUSHOVER_USER")
    config["apis"]["pushover"]["api_token"] = os.getenv("PUSHOVER_API_TOKEN")

    return config


def has_next_day_prices(prices: List[Dict[str, Any]]) -> bool:
    """Check if Octopus API has published next-day prices.

    Args:
        prices: List of Octopus price slots

    Returns:
        True if prices cover beyond 6 AM tomorrow
    """
    if not prices:
        return False

    # Get latest time covered by prices
    latest_time = max(
        datetime.fromisoformat(p["valid_from"].replace("Z", "+00:00")) for p in prices
    )

    # Next day 6 AM is our threshold (coverage for overnight charging)
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    next_day_6am = tomorrow.replace(hour=6, minute=0, second=0, microsecond=0)

    has_coverage = latest_time >= next_day_6am
    logger.info(
        f"Price coverage until {latest_time.strftime('%Y-%m-%d %H:%M')} UTC "
        f"({'covers' if has_coverage else 'does not cover'} next-day charging)"
    )

    return has_coverage


def fetch_data(config: Dict[str, Any]) -> tuple[list[PriceSlot], list[CarbonSlot], str]:
    """Fetch price and carbon data with intelligent fallback to forecasts.

    Strategy:
    1. Try Octopus API first (actual prices when available)
    2. Check if we have next-day coverage
    3. Fall back to Guy Lipman forecast if needed

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (price_slots, carbon_slots, price_source)
        price_source: "octopus_actual" or "forecast"

    Raises:
        RuntimeError: If all data sources fail
    """
    region = config["user"]["region"]
    postcode = config["user"]["postcode"]
    price_source = "unknown"

    # Try Octopus API first (actual prices)
    logger.info(f"Attempting to fetch Octopus actual prices for region {region}")
    octopus_client = OctopusAPIClient()

    try:
        prices = octopus_client.get_prices(region, hours=48)
        logger.info(f"Fetched {len(prices)} Octopus price slots")

        # Check if we have next-day coverage
        if has_next_day_prices(prices):
            logger.info("✅ Using Octopus ACTUAL prices (published)")
            price_source = "octopus_actual"

            # Convert to PriceSlot objects
            price_slots = []
            for p in prices:
                time = datetime.fromisoformat(p["valid_from"].replace("Z", "+00:00"))
                price_slots.append(PriceSlot(time, p["value_inc_vat"], "octopus"))

        else:
            logger.warning(
                "⚠️ Octopus prices incomplete - falling back to Guy Lipman forecast"
            )
            price_slots, price_source = fetch_forecast_prices(region)

    except Exception as e:
        logger.error(f"Failed to fetch Octopus prices: {e}")
        logger.info("Falling back to Guy Lipman forecast")
        price_slots, price_source = fetch_forecast_prices(region)

    if not price_slots:
        raise RuntimeError("Failed to fetch prices from all sources")

    # Fetch carbon intensity (same for both price sources)
    carbon_region_id = config["user"].get("carbon_region_id", None)
    if carbon_region_id:
        logger.info(f"Fetching carbon intensity for region ID {carbon_region_id}")
    else:
        logger.info(f"Fetching carbon intensity for postcode {postcode}")
    carbon_client = CarbonAPIClient()
    try:
        carbon_data = carbon_client.get_intensity(postcode, region_id=carbon_region_id)
        logger.info(f"Fetched {len(carbon_data)} carbon slots")
    except Exception as e:
        logger.warning(f"Failed to fetch carbon data: {e}")
        logger.info("Proceeding with price-only analysis")
        carbon_data = []

    # Convert to CarbonSlot objects
    carbon_slots = []
    for c in carbon_data:
        time = datetime.fromisoformat(c["time"].replace("Z", "+00:00"))
        carbon_slots.append(CarbonSlot(time, c["intensity"]))

    # If no carbon data, create dummy slots (neutral carbon score)
    if not carbon_slots:
        logger.info("Creating neutral carbon slots for price-only analysis")
        for price_slot in price_slots:
            # Use 175 gCO2/kWh as UK grid average
            carbon_slots.append(CarbonSlot(price_slot.time, 175))

    return price_slots, carbon_slots, price_source


def fetch_forecast_prices(region: str) -> tuple[list[PriceSlot], str]:
    """Fetch prices from Guy Lipman forecast as fallback.

    Args:
        region: DNO region code

    Returns:
        Tuple of (price_slots, price_source)

    Raises:
        RuntimeError: If forecast fetch fails
    """
    logger.info(f"Fetching Guy Lipman forecast for region {region}")
    forecast_client = ForecastAPIClient()

    try:
        forecasts = forecast_client.get_forecasts(region)

        if not forecasts:
            raise RuntimeError("Forecast returned no data")

        logger.info(f"✅ Using Guy Lipman FORECAST ({len(forecasts)} slots)")

        # Convert forecast format to PriceSlot objects
        price_slots = []
        for f in forecasts:
            # Parse date and time
            date_str = f["date"]
            time_str = f["time"]
            dt_str = f"{date_str}T{time_str}:00+00:00"
            time = datetime.fromisoformat(dt_str)

            price_slots.append(PriceSlot(time, f["price"], "forecast"))

        return price_slots, "forecast"

    except Exception as e:
        logger.error(f"Failed to fetch forecast: {e}")
        raise RuntimeError("Forecast API failed") from e


def format_notification(
    window: ChargingWindow,
    config: Dict[str, Any],
    price_source: str = "octopus_actual",
    current_time: datetime = None,
) -> tuple[str, str, int, str]:
    """Format charging recommendation notification.

    Args:
        window: Optimal charging window
        config: Configuration dictionary
        price_source: Source of price data ("octopus_actual" or "forecast")
        current_time: Current time for status checking (defaults to now)

    Returns:
        Tuple of (title, message, priority, sound)
    """
    rating = window.rating
    kwh = config["user"]["typical_charge_kwh"]

    # Check window status
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    window_status = window.get_status(current_time)
    time_until_start = window.time_until_start(current_time)
    time_until_end = window.time_until_end(current_time)

    # Check for negative pricing (SPECIAL ALERT!)
    if window.has_negative_pricing():
        priority = 2  # Emergency priority for negative pricing!
        sound = "cashregister"  # Money sound
        emoji = "💰💸⚡"
        action = "CHARGE NOW - You'll get PAID!"
    # Determine notification priority and sound
    elif rating == OpportunityRating.EXCELLENT:
        priority = 1  # High
        sound = config["apis"]["pushover"]["sounds"]["excellent"]
        emoji = "🔋⚡"
        action = "Definitely charge tonight!"
    elif rating == OpportunityRating.GOOD:
        priority = 0  # Normal
        sound = config["apis"]["pushover"]["sounds"]["good"]
        emoji = "🔋"
        action = "Good time to charge"
    elif rating == OpportunityRating.AVERAGE:
        priority = -1  # Quiet
        sound = "none"
        emoji = "🔌"
        action = "Consider waiting if possible"
    else:
        priority = -1  # Quiet
        sound = "none"
        emoji = "⏸️"
        action = "Wait for better prices"

    # Format time window (12-hour with AM/PM for clarity)
    start_time = window.start.strftime("%I:%M %p")
    end_time = window.end.strftime("%I:%M %p")

    # Add window status context to action
    if window_status == WindowStatus.ACTIVE:
        action = f"🟢 ACTIVE NOW! {action}"
        status_prefix = "⚡ CHARGING WINDOW IS ACTIVE! "
    elif window_status == WindowStatus.PASSED:
        action = "⏰ Window passed - see next best time below"
        status_prefix = "⚠️ LATE NOTIFICATION: "
    else:  # UPCOMING
        hours_until = int(time_until_start.total_seconds() / 3600)
        if hours_until < 2:
            status_prefix = f"🕐 Starts in {hours_until}h - "
        else:
            status_prefix = ""

    # Build message - SPECIAL FORMAT for negative pricing
    if window.has_negative_pricing():
        earnings = window.get_earnings_estimate(kwh)
        title = f"🚨 NEGATIVE PRICING ALERT! 💰 You'll GET PAID £{earnings:.2f}!"

        message = f"<b>⚡ Window:</b> {start_time} - {end_time}\n"
        message += f"<b>💸 EARNINGS:</b> £{earnings:.2f} for {kwh}kWh!\n"
        message += f"<b>📊 Price:</b> {window.avg_price:.1f}p/kWh (NEGATIVE!)\n"
        message += "\n<b>🎉 RARE OPPORTUNITY!</b>\n"
        message += "Grid will PAY YOU to charge.\n"
        message += "Charge as much as possible!\n"
    else:
        title = (
            f"{status_prefix}EV Optimizer: {emoji} Tonight: {rating.value} opportunity"
        )

        message = f"<b>⚡ Best window:</b> {start_time} - {end_time}\n"

        # Add status-specific context
        if window_status == WindowStatus.ACTIVE:
            remaining_hours = int(time_until_end.total_seconds() / 3600)
            remaining_mins = int((time_until_end.total_seconds() % 3600) / 60)
            message += f"<b>⏰ Status:</b> ACTIVE ({remaining_hours}h {remaining_mins}m remaining)\n"
        elif window_status == WindowStatus.PASSED:
            message += "<b>⚠️ Status:</b> Window has passed\n"

        message += f"<b>💰 Cost:</b> £{window.total_cost:.2f} for {kwh}kWh\n"
        message += f"<b>📊 Avg price:</b> {window.avg_price:.1f}p/kWh\n"

        if window.savings_vs_baseline > 0:
            message += f"<b>💵 Save:</b> £{window.savings_vs_baseline:.2f} vs evening\n"

    # Only add carbon/reason for normal pricing
    if not window.has_negative_pricing():
        message += f"<b>🌱 Carbon:</b> {window.avg_carbon} gCO2/kWh"

        if window.avg_carbon <= 100:
            message += " (very clean)\n"
        elif window.avg_carbon <= 150:
            message += " (clean)\n"
        else:
            message += "\n"

        # Add reason
        reason_text = {
            "both": "Both cheap AND clean",
            "cheap": "Cheap electricity",
            "clean": "Clean energy",
            "neither": "Limited options",
        }
        message += f"\n<b>Why:</b> {reason_text.get(window.reason, window.reason)}\n"

    # Add data source indicator
    if price_source == "octopus_actual":
        message += "<b>📊 Data:</b> Actual prices (published) ✅\n"
    else:
        message += "<b>📊 Data:</b> Forecast prices (predicted)\n"

    message += f"<b>Action:</b> {action}"

    return title, message, priority, sound


def main():
    """Main execution function"""
    logger.info("Starting daily notification script")

    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded")

        # Initialize analyzer
        analyzer = Analyzer(
            price_weight=config["preferences"]["price_weight"],
            carbon_weight=config["preferences"]["carbon_weight"],
            price_excellent=config["thresholds"]["price_excellent"],
            price_good=config["thresholds"]["price_good"],
            carbon_excellent=config["thresholds"]["carbon_excellent"],
            carbon_good=config["thresholds"]["carbon_good"],
        )

        # Fetch data (with intelligent fallback)
        price_slots, carbon_slots, price_source = fetch_data(config)
        logger.info(f"📊 Data source: {price_source}")

        # Calculate charge duration
        kwh = config["user"]["typical_charge_kwh"]
        kw_rate = config["user"]["charging_rate_kw"]
        charge_hours = kwh / kw_rate
        logger.info(
            f"Analyzing for {kwh}kWh charge at {kw_rate}kW ({charge_hours:.1f} hours)"
        )

        # Find optimal window
        logger.info("Finding optimal charging window")
        baseline_time = datetime.now(timezone.utc).replace(
            hour=18, minute=0, second=0, microsecond=0
        )

        window = analyzer.find_optimal_window(
            price_slots, carbon_slots, charge_hours, baseline_time
        )

        logger.info(
            f"Optimal window: {window.start.strftime('%H:%M')} - "
            f"{window.end.strftime('%H:%M')}, rating={window.rating.value}"
        )

        # Save recommendation
        data_store = DataStore()

        # Determine day type (weekend vs weekday)
        day_of_week = window.start.weekday()  # 0=Monday, 6=Sunday
        day_type = "weekend" if day_of_week >= 5 else "weekday"

        recommendation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": window.start.date().isoformat(),
            "day_type": day_type,
            "price_source": price_source,  # NEW: Track data source
            "window_start": window.start.isoformat(),
            "window_end": window.end.isoformat(),
            "avg_price": window.avg_price,
            "avg_carbon": window.avg_carbon,
            "total_cost": window.total_cost,
            "total_carbon": window.total_carbon,
            "rating": window.rating.value,
            "reason": window.reason,
            "savings": window.savings_vs_baseline,
            "score": window.opportunity_score,
        }
        data_store.save_recommendation(recommendation)
        logger.info(f"Recommendation saved ({day_type}, {price_source})")

        # Check for negative pricing (money-making opportunity!)
        has_negative_pricing = any(slot.price < 0 for slot in price_slots)
        negative_slots = [slot for slot in price_slots if slot.price < 0]

        pushover_client = PushoverClient(
            config["apis"]["pushover"]["user_key"],
            config["apis"]["pushover"]["api_token"],
        )

        # Send special alert for negative pricing
        if has_negative_pricing:
            logger.info(f"⚡ NEGATIVE PRICING DETECTED! {len(negative_slots)} slots")
            earnings = sum(abs(slot.price) for slot in negative_slots) * kwh / 100

            neg_title = "💰 MONEY-MAKING ALERT: Negative Pricing Tonight!"
            neg_message = "<b>⚡ You'll be PAID to charge tonight!</b>\n\n"
            neg_message += (
                f"<b>💵 Expected earnings:</b> £{earnings:.2f} for {kwh}kWh\n"
            )
            neg_message += f"<b>📊 Negative price slots:</b> {len(negative_slots)}\n\n"
            neg_message += "<b>Best negative slots:</b>\n"

            # Show up to 5 best negative slots
            sorted_neg = sorted(negative_slots, key=lambda x: x.price)[:5]
            for slot in sorted_neg:
                time_str = slot.time.strftime("%H:%M")
                neg_message += f"  • {time_str}: {slot.price:.2f}p/kWh (PAID £{abs(slot.price * kwh / 100):.2f})\n"

            neg_message += "\n<b>🔋 Action:</b> Plug in tonight - you'll make money!"

            # Send high-priority alert
            pushover_client.send_notification(
                title=neg_title,
                message=neg_message,
                priority=1,  # High priority
                sound="cashregister",
                html=True,
            )
            logger.info("Negative pricing alert sent!")

        # Determine if this is worth a notification (exceptional opportunities only)
        is_exceptional = (
            window.rating == OpportunityRating.EXCELLENT  # EXCELLENT rating
            or window.avg_price <= 8.0  # Very cheap (<8p/kWh)
            or window.savings_vs_baseline >= 1.50  # Significant savings (>£1.50)
            or has_negative_pricing  # Already handled above, but included for clarity
        )

        # Always send notification for exceptional opportunities
        # For normal/poor opportunities, skip to reduce notification spam
        if is_exceptional or has_negative_pricing:
            # Format and send normal notification
            title, message, priority, sound = format_notification(
                window, config, price_source
            )

            logger.info(
                f"Sending notification (priority={priority}, reason: "
                f"{'negative pricing' if has_negative_pricing else 'exceptional opportunity'})"
            )
            success = pushover_client.send_notification(
                title=title,
                message=message,
                priority=priority,
                sound=sound,
                html=True,
            )

            if success:
                logger.info("Daily notification sent successfully")
                return 0
            else:
                logger.error("Failed to send notification")
                return 1
        else:
            logger.info(
                f"⏸️  Skipping notification - not exceptional "
                f"(rating={window.rating.value}, price={window.avg_price:.1f}p/kWh, "
                f"savings=£{window.savings_vs_baseline:.2f})"
            )
            logger.info(
                "💡 Tip: Use './charge <current%> <target%> --notify' for personalized recommendations"
            )
            return 0

    except Exception as e:
        logger.exception(f"Error in daily notification script: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
