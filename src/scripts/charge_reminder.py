#!/usr/bin/env python3
"""Evening Charge Reminder Script

Sends a gentle reminder if today had a good charging opportunity.
Runs daily at 20:00 via launchd.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, Optional
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.data_store import DataStore
from modules.pushover import PushoverClient
from modules.analyzer import OpportunityRating
import yaml
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/charge_reminder.log"),
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


def get_today_recommendation(data_store: DataStore) -> Optional[Dict[str, Any]]:
    """Get today's charging recommendation.

    Args:
        data_store: DataStore instance

    Returns:
        Recommendation dictionary or None if not found
    """
    today = date.today().isoformat()
    logger.info(f"Looking for recommendation for {today}")

    recommendation = data_store.get_recommendation_by_date(today)

    if recommendation:
        logger.info(
            f"Found recommendation: rating={recommendation.get('rating')}, "
            f"window={recommendation.get('window_start')}"
        )
    else:
        logger.info("No recommendation found for today")

    return recommendation


def should_send_reminder(recommendation: Optional[Dict[str, Any]]) -> bool:
    """Determine if a reminder should be sent.

    Args:
        recommendation: Today's recommendation

    Returns:
        True if reminder should be sent
    """
    if not recommendation:
        logger.info("No recommendation - skipping reminder")
        return False

    rating = recommendation.get("rating", "POOR")

    # Only remind for EXCELLENT or GOOD opportunities
    if rating in [OpportunityRating.EXCELLENT.value, OpportunityRating.GOOD.value]:
        logger.info(f"Rating is {rating} - sending reminder")
        return True

    logger.info(f"Rating is {rating} - skipping reminder")
    return False


def format_reminder(
    recommendation: Dict[str, Any], config: Dict[str, Any]
) -> tuple[str, str]:
    """Format reminder notification.

    Args:
        recommendation: Today's recommendation
        config: Configuration dictionary

    Returns:
        Tuple of (title, message)
    """
    rating = recommendation.get("rating", "GOOD")
    window_start = recommendation.get("window_start", "")
    window_end = recommendation.get("window_end", "")
    total_cost = recommendation.get("total_cost", 0)
    savings = recommendation.get("savings", 0)

    # Parse times for display
    try:
        start_dt = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(window_end.replace("Z", "+00:00"))
        start_time = start_dt.strftime("%H:%M")
        end_time = end_dt.strftime("%H:%M")
    except Exception:
        start_time = "tonight"
        end_time = "morning"

    # Emoji based on rating
    emoji = "🔋⚡" if rating == "EXCELLENT" else "🔋"

    title = f"EV Optimizer: {emoji} Reminder: Good charging opportunity tonight"

    message = f"<b>Best window:</b> {start_time} - {end_time}\n"
    message += f"<b>Cost:</b> £{total_cost:.2f}\n"

    if savings > 0:
        message += f"<b>Savings:</b> £{savings:.2f} vs evening\n"

    message += "\n<b>Action:</b> Plug in before bed!"

    return title, message


def main():
    """Main execution function"""
    logger.info("Starting charge reminder script")

    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded")

        # Initialize clients
        data_store = DataStore()

        # Get today's recommendation
        recommendation = get_today_recommendation(data_store)

        # Check if reminder should be sent
        if not should_send_reminder(recommendation):
            logger.info("No reminder needed - exiting")
            return 0

        # Format reminder
        title, message = format_reminder(recommendation, config)

        # Send notification
        logger.info("Sending reminder notification")
        pushover_client = PushoverClient(
            config["apis"]["pushover"]["user_key"],
            config["apis"]["pushover"]["api_token"],
        )

        success = pushover_client.send_notification(
            title=title,
            message=message,
            priority=0,  # Normal priority
            sound="pushover",
            html=True,
        )

        if success:
            logger.info("Reminder sent successfully")
            return 0
        else:
            logger.error("Failed to send reminder")
            return 1

    except Exception as e:
        logger.exception(f"Error in charge reminder script: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
