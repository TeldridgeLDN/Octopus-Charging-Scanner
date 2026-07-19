#!/usr/bin/env python3
"""ACIX Usage Data Fetch Script

Fetches electricity consumption data from Octopus Energy API and stores
it for EV charging detection analysis. Runs every 6 hours via launchd.

Part of the ACIX (Adaptive Charging Intelligence Extension) system.
"""

import sys
from pathlib import Path
from typing import Dict, Any
import logging
import argparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.octopus_api import OctopusConsumptionClient
from modules.data_store import DataStore
import yaml
from dotenv import load_dotenv

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "acix_fetch_usage.log"),
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


def fetch_and_store_usage(days: int = 2, backfill: bool = False) -> Dict[str, Any]:
    """Fetch consumption data and store it.

    Args:
        days: Number of days to fetch (default 2 = 48 hours)
        backfill: If True, fetch more historical data

    Returns:
        Summary of the operation
    """
    logger.info(f"Starting usage fetch for {days} days (backfill={backfill})")

    # Initialize clients
    try:
        consumption_client = OctopusConsumptionClient()
    except ValueError as e:
        logger.error(f"Failed to initialize consumption client: {e}")
        return {"success": False, "error": str(e)}

    data_store = DataStore()

    # Determine fetch period
    if backfill:
        # For backfill, fetch specified days
        usage_records = consumption_client.get_historical_consumption(days=days)
    else:
        # Normal operation: fetch last 48 hours
        usage_records = consumption_client.get_consumption()

    if not usage_records:
        logger.warning("No consumption records returned from API")
        return {
            "success": True,
            "records_fetched": 0,
            "records_added": 0,
            "message": "No data available from API",
        }

    # Store records (deduplicates automatically)
    records_added = data_store.save_usage(usage_records)

    # Get summary stats
    latest_timestamp = data_store.get_latest_usage_timestamp()

    result = {
        "success": True,
        "records_fetched": len(usage_records),
        "records_added": records_added,
        "latest_timestamp": latest_timestamp.isoformat() if latest_timestamp else None,
        "fetch_period_days": days,
    }

    logger.info(
        f"Fetch complete: {len(usage_records)} fetched, "
        f"{records_added} new records added"
    )

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch electricity consumption data from Octopus Energy"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Number of days to fetch (default: 2)",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill historical data (uses --days value)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but don't store it",
    )

    args = parser.parse_args()

    # Load config to check if ACIX is enabled
    config = load_config()
    acix_config = config.get("acix", {})

    if not acix_config.get("enabled", False):
        logger.info("ACIX is disabled in config, exiting")
        print("ACIX is disabled. Enable it in config/config.yaml")
        return

    if args.dry_run:
        logger.info("Dry run mode - fetching but not storing")
        try:
            client = OctopusConsumptionClient()
            records = client.get_historical_consumption(days=args.days)
            print(f"Would fetch {len(records)} records")
            if records:
                print(f"First record: {records[0]}")
                print(f"Last record: {records[-1]}")

                # Show some stats
                powers = [r["power_kw"] for r in records]
                print(f"Power range: {min(powers):.2f} - {max(powers):.2f} kW")
                print(f"Average power: {sum(powers)/len(powers):.2f} kW")
        except Exception as e:
            print(f"Error: {e}")
            logger.exception("Dry run failed")
        return

    # Execute fetch
    result = fetch_and_store_usage(days=args.days, backfill=args.backfill)

    if result["success"]:
        print(f"Successfully fetched {result['records_fetched']} records")
        print(f"Added {result['records_added']} new records")
        if result.get("latest_timestamp"):
            print(f"Latest data: {result['latest_timestamp']}")
    else:
        print(f"Fetch failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
