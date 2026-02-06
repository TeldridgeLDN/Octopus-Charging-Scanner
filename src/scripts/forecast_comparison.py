#!/usr/bin/env python3
"""Daily Forecast Comparison Script

Compares Guy Lipman forecast vs Octopus Agile actual prices.
Runs daily at 23:59 to record accuracy metrics.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.octopus_api import OctopusAPIClient
from modules.forecast_api import ForecastAPIClient
from modules.forecast_tracker import ForecastTracker
import yaml
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/forecast_comparison.log"),
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

    return config


def get_today_actual_prices(region: str) -> List[float]:
    """Fetch today's actual prices from Octopus API.

    Args:
        region: DNO region code

    Returns:
        List of 24 hourly average prices

    Raises:
        RuntimeError: If price data unavailable
    """
    octopus_client = OctopusAPIClient()

    # Get today's full 24 hours
    today = datetime.now(timezone.utc).date()
    period_from = datetime.combine(today, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    period_to = period_from + timedelta(hours=24)

    try:
        # Fetch half-hourly prices
        response = octopus_client.fetch(
            f"{octopus_client.BASE_URL}/{octopus_client.PRODUCT_CODE}/"
            f"electricity-tariffs/{octopus_client.TARIFF_CODE}-{region}/"
            f"standard-unit-rates/",
            params={
                "period_from": period_from.isoformat(),
                "period_to": period_to.isoformat(),
            },
        )

        results = response.get("results", [])

        if not results:
            raise RuntimeError("No price data available for today")

        # Sort by time
        results.sort(key=lambda x: x["valid_from"])

        # Group by hour and average
        hourly_prices = {}
        for slot in results:
            time = datetime.fromisoformat(slot["valid_from"].replace("Z", "+00:00"))
            hour = time.hour
            price = slot["value_inc_vat"]

            if hour not in hourly_prices:
                hourly_prices[hour] = []
            hourly_prices[hour].append(price)

        # Average each hour
        prices_24h = []
        for hour in range(24):
            if hour in hourly_prices:
                avg = sum(hourly_prices[hour]) / len(hourly_prices[hour])
                prices_24h.append(avg)
            else:
                # Fill missing hours with None (will be filtered later)
                prices_24h.append(None)

        # Check if we have complete data
        if None in prices_24h:
            missing_hours = [i for i, p in enumerate(prices_24h) if p is None]
            raise RuntimeError(
                f"Incomplete price data for today: missing hours {missing_hours}"
            )

        logger.info(f"Fetched {len(prices_24h)} hours of actual prices for today")
        return prices_24h

    except Exception as e:
        logger.error(f"Failed to fetch actual prices: {e}")
        raise RuntimeError(f"Cannot fetch actual prices: {e}") from e


def get_yesterday_forecast(region: str) -> List[float]:
    """Get yesterday's forecast for today.

    Args:
        region: DNO region code

    Returns:
        List of 24 hourly forecast prices

    Raises:
        RuntimeError: If forecast unavailable
    """
    # For now, we'll need to store forecasts daily to compare later
    # This is a simplified version - in production, daily_notification
    # should store the forecast it uses

    forecast_client = ForecastAPIClient()

    try:
        # Fetch current forecast
        forecast_data = forecast_client.get_forecasts(region)

        if not forecast_data:
            raise RuntimeError("No forecast data available")

        # Guy Lipman forecasts are hourly
        # Extract today's prices
        today = datetime.now(timezone.utc).date()

        # Group by date
        forecast_by_date = {}
        for entry in forecast_data:
            entry_date = entry.get("date")
            if entry_date:
                if entry_date not in forecast_by_date:
                    forecast_by_date[entry_date] = []
                forecast_by_date[entry_date].append(entry.get("price", 0))

        # Get today's forecast
        today_str = today.isoformat()
        if today_str in forecast_by_date:
            prices = forecast_by_date[today_str]
            logger.info(f"Found {len(prices)} hours of forecast for today")
            return prices[:24]  # Take first 24 hours
        else:
            raise RuntimeError(f"No forecast found for {today_str}")

    except Exception as e:
        logger.error(f"Failed to fetch forecast: {e}")
        raise RuntimeError(f"Cannot fetch forecast: {e}") from e


def main():
    """Main execution function"""
    logger.info("Starting daily forecast comparison")

    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded")

        region = config["user"]["region"]
        today = datetime.now(timezone.utc).date()

        logger.info(f"Comparing forecast vs actual for {today}")

        # Initialize tracker
        tracker = ForecastTracker()

        # Fetch actual prices for today
        logger.info("Fetching actual prices from Octopus")
        actual_prices = get_today_actual_prices(region)

        # Fetch forecast (this is current forecast, not yesterday's)
        # NOTE: This is a limitation - ideally we'd compare against
        # yesterday's forecast FOR today
        logger.info("Fetching forecast prices")
        try:
            forecast_prices = get_yesterday_forecast(region)
        except RuntimeError as e:
            logger.warning(f"Forecast unavailable: {e}")
            logger.info("Skipping comparison - no forecast data")
            return 0

        # Ensure both lists are same length
        min_len = min(len(forecast_prices), len(actual_prices))
        forecast_prices = forecast_prices[:min_len]
        actual_prices = actual_prices[:min_len]

        if min_len < 20:  # Need at least 20 hours for meaningful comparison
            logger.warning(f"Insufficient data: only {min_len} hours available")
            return 0

        # Record comparison
        logger.info(f"Recording comparison for {min_len} hours")
        metrics = tracker.record_comparison(
            comparison_date=today,
            forecast_prices=forecast_prices,
            actual_prices=actual_prices,
            forecast_source="guy_lipman",
        )

        # Log key metrics
        logger.info(
            f"Comparison complete: MAE={metrics['mean_absolute_error']:.2f}p/kWh, "
            f"Bias={metrics['mean_error']:.2f}p/kWh"
        )

        # Get recent accuracy stats
        accuracy = tracker.get_recent_accuracy(days=7)
        grade = tracker.get_reliability_grade(days=7)

        logger.info(
            f"7-day accuracy: MAE={accuracy['mean_absolute_error']:.2f}p/kWh, "
            f"Grade={grade}"
        )

        # Log warning if forecast reliability is poor
        if not tracker.should_trust_forecast(days=7):
            logger.warning(
                "⚠️  Forecast reliability is POOR - consider using caution with "
                "Guy Lipman forecasts"
            )

        return 0

    except Exception as e:
        logger.exception(f"Error in forecast comparison script: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
