#!/usr/bin/env python3
"""User Action Logging Utility

Simple CLI tool for users to log when they charged their EV.
This enables tracking adherence to recommendations.

Usage:
    python log_charge.py                  # Log charge for today
    python log_charge.py --date 2025-12-08  # Log charge for specific date
    python log_charge.py --kwh 35          # Log charge with specific kWh
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import Optional
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.data_store import DataStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/log_charge.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Log EV charging action",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python log_charge.py                    # Log charge for today
  python log_charge.py --date 2025-12-08  # Log charge for specific date
  python log_charge.py --kwh 35           # Log with specific kWh amount
  python log_charge.py --note "Charged at home"  # Add a note
        """,
    )

    parser.add_argument(
        "--date",
        type=str,
        help="Date of charge in YYYY-MM-DD format (default: today)",
        default=None,
    )

    parser.add_argument(
        "--kwh",
        type=float,
        help="Amount charged in kWh (optional)",
        default=None,
    )

    parser.add_argument(
        "--note",
        type=str,
        help="Optional note about the charge",
        default=None,
    )

    return parser.parse_args()


def log_charge(
    charge_date: Optional[str] = None,
    kwh_charged: Optional[float] = None,
    note: Optional[str] = None,
) -> bool:
    """Log a charging action.

    Args:
        charge_date: Date in YYYY-MM-DD format (default: today)
        kwh_charged: Amount charged in kWh (optional)
        note: Optional note about the charge

    Returns:
        True if successful, False otherwise
    """
    try:
        # Initialize data store
        data_store = DataStore()

        # Use today if no date specified
        if not charge_date:
            charge_date = date.today().isoformat()

        # Validate date format
        try:
            datetime.fromisoformat(charge_date)
        except ValueError:
            logger.error(f"Invalid date format: {charge_date}. Use YYYY-MM-DD")
            return False

        # Build action record
        action = {
            "timestamp": datetime.now().isoformat(),
            "date": charge_date,
            "action": "charged",
        }

        if kwh_charged is not None:
            action["kwh_charged"] = kwh_charged

        if note:
            action["note"] = note

        # Save action
        data_store.save_user_action(action)

        # Display confirmation
        print("\n✅ Charge logged successfully!")
        print(f"   Date: {charge_date}")
        if kwh_charged:
            print(f"   Amount: {kwh_charged} kWh")
        if note:
            print(f"   Note: {note}")

        # Check if there was a recommendation for this date
        recommendation = data_store.get_recommendation_by_date(charge_date)
        if recommendation:
            rating = recommendation.get("rating", "UNKNOWN")
            cost = recommendation.get("total_cost", 0)
            savings = recommendation.get("savings", 0)

            print(f"\n📊 Recommendation for {charge_date}:")
            print(f"   Rating: {rating}")
            print(f"   Recommended cost: £{cost:.2f}")
            if savings > 0:
                print(f"   Potential savings: £{savings:.2f}")
        else:
            print(f"\n⚠️  No recommendation found for {charge_date}")

        print()
        return True

    except Exception as e:
        logger.exception(f"Error logging charge: {e}")
        print(f"\n❌ Error: {e}\n")
        return False


def main():
    """Main execution function"""
    args = parse_args()

    logger.info(f"Logging charge: date={args.date}, kwh={args.kwh}, note={args.note}")

    success = log_charge(charge_date=args.date, kwh_charged=args.kwh, note=args.note)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
