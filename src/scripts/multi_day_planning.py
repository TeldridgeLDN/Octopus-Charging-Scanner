#!/usr/bin/env python3
"""Multi-Day Planning Script

Generates multi-day charging cost comparison to help users decide when to charge.
Default is 7 days using Guy Lipman forecasts. Can be run on-demand or scheduled.

Usage:
    python multi_day_planning.py              # 7-day plan with default kWh
    python multi_day_planning.py --days 3     # 3-day plan only
    python multi_day_planning.py --kwh 40     # Specify custom kWh
    python multi_day_planning.py --dry-run    # Display only, no notification
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.multi_day_planner import MultiDayPlanner, MultiDayPlan
from modules.analyzer import Analyzer
from modules.data_store import DataStore
from modules.pushover import PushoverClient
import yaml
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/multi_day_planning.log"),
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


def parse_args():
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Generate multi-day charging cost comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python multi_day_planning.py              # 7-day plan with default kWh
  python multi_day_planning.py --days 3     # 3-day plan only
  python multi_day_planning.py --kwh 40     # Custom charge amount
  python multi_day_planning.py --dry-run    # Display only, no notification
        """,
    )

    parser.add_argument(
        "--days",
        type=int,
        help="Number of days to plan (default: 7, max: 7)",
        default=7,
        choices=range(1, 8),
        metavar="DAYS",
    )

    parser.add_argument(
        "--kwh",
        type=float,
        help="Amount to charge in kWh (default: from config)",
        default=None,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display plan without sending notification",
        default=False,
    )

    return parser.parse_args()


def format_notification(plan: MultiDayPlan) -> tuple[str, str]:
    """Format multi-day plan as Pushover notification.

    Args:
        plan: MultiDayPlan to format

    Returns:
        Tuple of (title, message)
    """
    kwh = plan.kwh_amount
    num_days = plan.num_days

    # Build message with HTML formatting
    title = f"📅 {num_days}-Day Charging Plan ({kwh:.0f}kWh)"

    message = "<b>💰 Price Comparison:</b>\n\n"

    # Format each day
    for day in plan.days:
        # Parse window times
        start_dt = datetime.fromisoformat(day.optimal_window["start"])
        end_dt = datetime.fromisoformat(day.optimal_window["end"])
        start_str = start_dt.strftime("%H:%M")
        end_str = end_dt.strftime("%H:%M")

        # Get day of week
        date_obj = datetime.fromisoformat(day.date)
        day_of_week = date_obj.strftime("%a %b %d")

        # Emoji for rating
        rating_emoji = {
            "EXCELLENT": "⚡",
            "GOOD": "✅",
            "AVERAGE": "⚠️",
            "POOR": "❌",
        }.get(day.rating, "")

        # Special formatting for best day
        if day.day_name == plan.best_day["day_name"]:
            message += f"<b>✨ {day.day_name} ({day_of_week})</b>\n"
        else:
            message += f"<b>{day.day_name} ({day_of_week})</b>\n"

        message += f"⚡ Window: {start_str} - {end_str}\n"
        message += f"💵 Cost: £{day.cost:.2f} ({day.avg_price:.1f}p/kWh)\n"
        message += f"⭐ Rating: {day.rating} {rating_emoji}\n"

        # Data source indicator
        if day.price_source == "octopus_actual":
            message += "📊 Data: Actual prices ✅\n"
        else:
            message += "📊 Data: Forecast (predicted)\n"

        # Savings info (skip for today)
        if day.savings_vs_today > 0:
            percentage = (day.savings_vs_today / plan.days[0].cost) * 100
            message += (
                f"💚 Save: £{day.savings_vs_today:.2f} ({percentage:.0f}% cheaper)\n"
            )
        elif day.savings_vs_today < 0:
            percentage = abs(day.savings_vs_today / plan.days[0].cost) * 100
            message += f"💸 More: £{abs(day.savings_vs_today):.2f} ({percentage:.0f}% pricier)\n"

        message += "\n"

    # Add recommendation
    best = plan.best_day
    message += f"<b>🎯 BEST DAY: {best['day_name'].upper()}</b>\n"

    if best["savings"] > 0:
        message += f"💰 Savings: £{best['savings']:.2f} vs today ({best['percentage']:.0f}% cheaper)\n"
        if best["savings"] >= 2.0:
            message += "✨ Excellent savings opportunity!\n"
        elif best["savings"] >= 1.0:
            message += "👍 Good savings available\n"
    elif best["day_name"] == "Today":
        message += "💡 Today has the best prices\n"
    else:
        message += f"💡 {best['reason']}\n"

    message += "\n<i>💡 Decision is yours - you know your battery!</i>"

    return title, message


def main():
    """Main execution function"""
    args = parse_args()

    logger.info("Starting multi-day planning script")
    logger.info(f"Parameters: days={args.days}, kwh={args.kwh}, dry_run={args.dry_run}")

    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded")

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
        planner = MultiDayPlanner(config, analyzer, data_store, num_days=args.days)

        # Generate multi-day plan
        logger.info(f"Generating {args.days}-day plan...")
        plan = planner.generate_plan(kwh=args.kwh)

        # Format notification
        title, message = format_notification(plan)

        # Display to console
        print("\n" + "=" * 50)
        print(title)
        print("=" * 50)
        # Strip HTML tags for console display
        console_msg = (
            message.replace("<b>", "")
            .replace("</b>", "")
            .replace("<i>", "")
            .replace("</i>", "")
        )
        print(console_msg)
        print("=" * 50 + "\n")

        # Send notification unless dry-run
        if not args.dry_run:
            logger.info("Sending Pushover notification")

            pushover_client = PushoverClient(
                config["apis"]["pushover"]["user_key"],
                config["apis"]["pushover"]["api_token"],
            )

            success = pushover_client.send_notification(
                title=title,
                message=message,
                priority=0,  # Normal priority
                sound="cosmic",  # Gentle sound for planning info
                html=True,
            )

            if success:
                logger.info("Notification sent successfully")
                print("✅ Notification sent!")
                return 0
            else:
                logger.error("Failed to send notification")
                print("❌ Failed to send notification")
                return 1
        else:
            logger.info("Dry-run mode: notification not sent")
            print("ℹ️  Dry-run mode: notification not sent")
            return 0

    except Exception as e:
        logger.exception(f"Error in multi-day planning script: {e}")
        print(f"\n❌ Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
