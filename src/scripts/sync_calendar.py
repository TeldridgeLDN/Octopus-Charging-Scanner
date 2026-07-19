#!/usr/bin/env python3
"""Google Calendar Sync Script

Syncs EV charging recommendations to Google Calendar.
Can be run standalone or called from daily_notification.py.

Usage:
    python src/scripts/sync_calendar.py              # Sync 7-day plan
    python src/scripts/sync_calendar.py --test       # Test connection
    python src/scripts/sync_calendar.py --clear      # Delete all events
    python src/scripts/sync_calendar.py --cleanup    # Delete old events
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import logging
import yaml
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.google_calendar import GoogleCalendarClient
from modules.multi_day_planner import MultiDayPlanner
from modules.analyzer import Analyzer
from modules.data_store import DataStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/sync_calendar.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml and .env."""
    load_dotenv()

    config_path = Path("config/config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Override calendar_id from environment if set
    if os.getenv("GOOGLE_CALENDAR_ID"):
        if "google_calendar" not in config:
            config["google_calendar"] = {}
        config["google_calendar"]["calendar_id"] = os.getenv("GOOGLE_CALENDAR_ID")

    return config


def get_calendar_client(config: Dict[str, Any]) -> GoogleCalendarClient:
    """Create and return a Google Calendar client.

    Args:
        config: Configuration dictionary

    Returns:
        Configured GoogleCalendarClient

    Raises:
        ValueError: If calendar not configured
    """
    cal_config = config.get("google_calendar", {})

    if not cal_config.get("enabled", False):
        raise ValueError(
            "Google Calendar not enabled. Set google_calendar.enabled: true in config.yaml"
        )

    credentials_path = cal_config.get(
        "credentials_path", "config/google_credentials.json"
    )
    calendar_id = cal_config.get("calendar_id")

    if not calendar_id:
        raise ValueError(
            "Calendar ID not configured. Set google_calendar.calendar_id in config.yaml"
        )

    return GoogleCalendarClient(credentials_path, calendar_id)


def sync_multi_day_plan(config: Dict[str, Any]) -> int:
    """Generate and sync a 7-day charging plan to Google Calendar.

    Args:
        config: Configuration dictionary

    Returns:
        Number of events created
    """
    logger.info("Starting 7-day calendar sync")

    # Initialize components
    analyzer = Analyzer(
        price_weight=config["preferences"]["price_weight"],
        carbon_weight=config["preferences"]["carbon_weight"],
        price_excellent=config["thresholds"]["price_excellent"],
        price_good=config["thresholds"]["price_good"],
        carbon_excellent=config["thresholds"]["carbon_excellent"],
        carbon_good=config["thresholds"]["carbon_good"],
    )

    data_store = DataStore()

    planner = MultiDayPlanner(
        config=config,
        analyzer=analyzer,
        data_store=data_store,
        num_days=7,
    )

    # Generate the plan
    kwh = config["user"]["typical_charge_kwh"]
    plan = planner.generate_plan(kwh)

    logger.info(
        f"Generated plan: {len(plan.days)} days, best day: {plan.best_day['day_name']}"
    )

    # Get calendar client
    client = get_calendar_client(config)

    # Get reminder settings
    cal_config = config.get("google_calendar", {})
    reminders = cal_config.get("reminders", [60, 15])

    # Convert days to dict format expected by create_multi_day_events
    days_data = []
    for day in plan.days:
        days_data.append(
            {
                "date": day.date,
                "day_name": day.day_name,
                "avg_price": day.avg_price,
                "optimal_window": day.optimal_window,
                "cost": day.cost,
                "rating": day.rating,
                "price_source": day.price_source,
                "savings_vs_today": day.savings_vs_today,
                "avg_carbon": day.avg_carbon,
            }
        )

    # Create events
    event_ids = client.create_multi_day_events(
        days=days_data,
        kwh=kwh,
        best_day=plan.best_day,
        reminders=reminders,
    )

    logger.info(f"Created/updated {len(event_ids)} calendar events")

    # Cleanup old events if enabled
    if cal_config.get("delete_past_events", True):
        retention_days = cal_config.get("retention_days", 7)
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        deleted = client.delete_old_events(cutoff)
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old events")

    return len(event_ids)


def test_connection(config: Dict[str, Any]) -> bool:
    """Test the Google Calendar connection.

    Args:
        config: Configuration dictionary

    Returns:
        True if connection successful
    """
    logger.info("Testing Google Calendar connection")

    try:
        client = get_calendar_client(config)
        success = client.test_connection()

        if success:
            print("✅ Google Calendar connection successful!")
            return True
        else:
            print("❌ Google Calendar connection failed")
            return False

    except FileNotFoundError as e:
        print(f"❌ Credentials file not found: {e}")
        print("\nTo set up Google Calendar integration:")
        print("1. Create a Google Cloud project")
        print("2. Enable the Google Calendar API")
        print("3. Create a service account and download credentials")
        print("4. Save credentials to config/google_credentials.json")
        return False

    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        return False


def clear_all_events(config: Dict[str, Any]) -> int:
    """Delete all EV charging events from the calendar.

    Args:
        config: Configuration dictionary

    Returns:
        Number of events deleted
    """
    logger.info("Clearing all calendar events")

    client = get_calendar_client(config)

    # Delete events up to far in the future
    future = datetime.now(timezone.utc) + timedelta(days=365)
    deleted = client.delete_old_events(future)

    logger.info(f"Deleted {deleted} events")
    print(f"✅ Deleted {deleted} events from calendar")

    return deleted


def cleanup_old_events(config: Dict[str, Any]) -> int:
    """Delete old events based on retention settings.

    Args:
        config: Configuration dictionary

    Returns:
        Number of events deleted
    """
    logger.info("Cleaning up old calendar events")

    client = get_calendar_client(config)

    cal_config = config.get("google_calendar", {})
    retention_days = cal_config.get("retention_days", 7)

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = client.delete_old_events(cutoff)

    logger.info(f"Deleted {deleted} old events")
    print(f"✅ Deleted {deleted} events older than {retention_days} days")

    return deleted


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync EV charging recommendations to Google Calendar"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test the calendar connection",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all EV charging events from calendar",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete old events based on retention settings",
    )

    args = parser.parse_args()

    try:
        config = load_config()

        if args.test:
            success = test_connection(config)
            return 0 if success else 1

        if args.clear:
            clear_all_events(config)
            return 0

        if args.cleanup:
            cleanup_old_events(config)
            return 0

        # Default: sync 7-day plan
        num_events = sync_multi_day_plan(config)
        print(f"✅ Synced {num_events} events to Google Calendar")
        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"❌ Error: {e}")
        return 1

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"❌ Error: {e}")
        return 1

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
