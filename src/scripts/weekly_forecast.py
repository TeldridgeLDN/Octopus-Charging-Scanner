#!/usr/bin/env python3
"""Weekly Forecast Script

Fetches 7-day price forecasts and sends a weekly planning notification.
Runs Monday mornings at 07:00 via launchd.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.forecast_api import ForecastAPIClient
from modules.octopus_api import OctopusAPIClient
from modules.data_store import DataStore
from modules.pushover import PushoverClient
from modules.analyzer import Analyzer
import yaml
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/weekly_forecast.log"),
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


def analyze_week(
    forecast_data: List[Dict[str, Any]], analyzer: Analyzer
) -> Dict[str, Any]:
    """Analyze weekly forecast and identify best charging days.

    Args:
        forecast_data: List of daily forecasts from Guy Lipman
        analyzer: Analyzer instance for scoring

    Returns:
        Dictionary with analysis results
    """
    daily_scores = []

    for day_forecast in forecast_data:
        date = day_forecast.get("date")
        avg_price = day_forecast.get("avg_price", 0)
        min_price = day_forecast.get("min_price", 0)

        # Use minimum price for the day as a proxy for best opportunity
        # Carbon data not available in weekly forecast
        score = analyzer.calculate_price_score(min_price)
        rating = analyzer.classify_opportunity(score)

        daily_scores.append(
            {
                "date": date,
                "avg_price": avg_price,
                "min_price": min_price,
                "score": score,
                "rating": rating.value,
            }
        )

    # Sort by score (best first)
    daily_scores.sort(key=lambda x: x["score"], reverse=True)

    # Identify best and worst days
    best_days = [d for d in daily_scores if d["score"] >= 75]
    avoid_days = [d for d in daily_scores if d["score"] < 50]

    return {
        "daily_scores": daily_scores,
        "best_days": best_days,
        "avoid_days": avoid_days,
        "avg_week_price": (
            sum(d["avg_price"] for d in daily_scores) / len(daily_scores)
            if daily_scores
            else 0.0
        ),
    }


def format_notification(analysis: Dict[str, Any], config: Dict[str, Any]) -> str:
    """Format weekly forecast notification message.

    Args:
        analysis: Weekly analysis results
        config: Configuration dictionary

    Returns:
        HTML-formatted notification message
    """
    best_days = analysis["best_days"]
    avoid_days = analysis["avoid_days"]
    avg_price = analysis["avg_week_price"]

    message = "<b>📅 Weekly Charging Forecast</b>\n\n"

    if best_days:
        message += "<b>✅ Best days to charge:</b>\n"
        for day in best_days[:3]:  # Top 3
            date_str = day["date"]
            message += f"  • {date_str}: {day['min_price']:.1f}p/kWh\n"
        message += "\n"

    if avoid_days:
        message += "<b>⚠️ Avoid charging on:</b>\n"
        for day in avoid_days[:2]:  # Worst 2
            date_str = day["date"]
            message += f"  • {date_str}: {day['min_price']:.1f}p/kWh\n"
        message += "\n"

    # Calculate weekly cost estimate
    charge_kwh = config["user"]["typical_charge_kwh"]
    weekly_charges = 2  # Assume 2 charges per week
    best_avg = (
        sum(d["min_price"] for d in best_days) / len(best_days)
        if best_days
        else avg_price
    )
    weekly_cost = (best_avg * charge_kwh * weekly_charges) / 100

    message += "<b>💰 Weekly outlook:</b>\n"
    message += f"  Average price: {avg_price:.1f}p/kWh\n"
    message += f"  Est. cost (2 charges): £{weekly_cost:.2f}\n"

    return message


def main():
    """Main execution function"""
    logger.info("Starting weekly forecast script")

    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded")

        # Initialize clients
        forecast_client = ForecastAPIClient()
        octopus_client = OctopusAPIClient()
        data_store = DataStore()
        pushover_client = PushoverClient(
            config["apis"]["pushover"]["user_key"],
            config["apis"]["pushover"]["api_token"],
        )

        # Initialize analyzer
        analyzer = Analyzer(
            price_weight=config["preferences"]["price_weight"],
            carbon_weight=config["preferences"]["carbon_weight"],
            price_excellent=config["thresholds"]["price_excellent"],
            price_good=config["thresholds"]["price_good"],
            carbon_excellent=config["thresholds"]["carbon_excellent"],
            carbon_good=config["thresholds"]["carbon_good"],
        )

        # Fetch 7-day forecast
        logger.info("Fetching 7-day forecast from Guy Lipman")
        region = config["user"]["region"]

        try:
            forecast_data = forecast_client.get_forecasts(region)
            logger.info(f"Fetched {len(forecast_data)} days of forecast data")
        except Exception as e:
            logger.warning(f"Guy Lipman forecast unavailable: {e}")
            logger.info("Falling back to Octopus next-day only")

            # Fallback: Use Octopus next-day prices only
            prices = octopus_client.get_prices(region)
            if not prices:
                logger.error("No price data available from any source")
                return 1

            # Convert to simple forecast format
            avg_price = sum(p["value_inc_vat"] for p in prices) / len(prices)
            min_price = min(p["value_inc_vat"] for p in prices)

            forecast_data = [
                {
                    "date": "Tomorrow",
                    "avg_price": avg_price,
                    "min_price": min_price,
                }
            ]

        # Analyze weekly forecast
        logger.info("Analyzing weekly forecast")
        analysis = analyze_week(forecast_data, analyzer)

        # Store forecast history
        forecast_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "forecast_data": forecast_data,
            "analysis": analysis,
        }
        data_store.save_forecast(forecast_entry)
        logger.info("Forecast saved to data store")

        # Format and send notification
        message = format_notification(analysis, config)
        logger.info("Sending weekly forecast notification")

        success = pushover_client.send_notification(
            title="EV Optimizer: Weekly Charging Forecast",
            message=message,
            priority=0,
            sound="pushover",
            html=True,
        )

        if success:
            logger.info("Weekly forecast notification sent successfully")
            return 0
        else:
            logger.error("Failed to send notification")
            return 1

    except Exception as e:
        logger.exception(f"Error in weekly forecast script: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
