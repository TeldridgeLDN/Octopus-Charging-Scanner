#!/usr/bin/env python3
"""Monthly Cost Summary Script

Generates monthly charging cost report with ROI analysis.
Runs on the 1st of each month at 08:00 via launchd.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any
import logging
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.data_store import DataStore
from modules.cost_tracker import CostTracker
from modules.pushover import PushoverClient
import yaml
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/monthly_summary.log"),
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


def format_monthly_summary(
    summary: Dict[str, Any], projection: Dict[str, Any], config: Dict[str, Any]
) -> str:
    """Format monthly summary notification.

    Args:
        summary: Monthly cost summary from CostTracker
        projection: Yearly projection from CostTracker
        config: Configuration dictionary

    Returns:
        HTML-formatted summary message
    """
    year = summary["year"]
    month = summary["month"]
    month_name = datetime(year, month, 1).strftime("%B")

    message = f"<b>📊 Monthly Charging Report - {month_name} {year}</b>\n\n"

    # Cost summary
    message += "<b>💰 Cost Summary:</b>\n"
    if summary["num_charges"] > 0:
        message += f"  Total spent: £{summary['total_cost']:.2f}\n"
        message += f"  Number of charges: {summary['num_charges']}\n"
        message += f"  Avg per charge: £{summary['avg_cost_per_charge']:.2f}\n"
    else:
        message += "  No charges this month\n"

    # Savings analysis
    if summary["num_charges"] > 0:
        message += "\n<b>💸 Savings vs Baseline:</b>\n"
        baselines = summary["baseline_comparisons"]

        std_savings = baselines["standard_savings"]
        peak_savings = baselines["peak_savings"]

        message += f"  vs Standard rate (15p/kWh): £{std_savings:.2f}\n"
        message += f"  vs Peak charging (20p/kWh): £{peak_savings:.2f}\n"

        # Show which baseline is most relevant
        if std_savings > 0:
            pct_saved = (std_savings / baselines["standard_baseline_cost"]) * 100
            message += f"  💡 Saved {pct_saved:.0f}% vs standard rate\n"

    # Performance metrics
    if summary["num_charges"] > 0:
        message += "\n<b>📈 Performance:</b>\n"
        message += f"  Adherence: {summary['adherence_rate']:.0f}%\n"
        message += (
            f"  Good opportunities: {summary['charges_on_good_days']}"
            f"/{summary['good_opportunities']}\n"
        )

        # Show rating breakdown
        ratings = summary["charges_by_rating"]
        if any(ratings.values()):
            message += "  Charge breakdown:\n"
            if ratings.get("EXCELLENT", 0) > 0:
                message += f"    ⚡ {ratings['EXCELLENT']} excellent\n"
            if ratings.get("GOOD", 0) > 0:
                message += f"    ✅ {ratings['GOOD']} good\n"
            if ratings.get("AVERAGE", 0) > 0:
                message += f"    🔌 {ratings['AVERAGE']} average\n"
            if ratings.get("POOR", 0) > 0:
                message += f"    ⚠️ {ratings['POOR']} poor\n"

    # Year-to-date projection
    if projection["months_of_data"] > 0:
        message += "\n<b>🎯 Year to Date ({} months):</b>\n".format(
            projection["months_of_data"]
        )
        message += f"  Total saved: £{projection['ytd_savings']:.2f}\n"
        message += f"  Total charges: {projection['ytd_charges']}\n"

        # Show projection if we have data
        if projection["months_of_data"] >= 2:
            message += f"  Projected annual savings: £{projection['projected_annual_savings']:.2f}\n"

    # Add tip or encouragement
    if summary["num_charges"] > 0:
        message += "\n<b>💡 Insight:</b> "
        adherence = summary["adherence_rate"]

        if adherence >= 80:
            message += "Outstanding! You're maximizing your savings by charging on the best days."
        elif adherence >= 60:
            message += "Great work! Keep watching for excellent opportunities to save even more."
        elif adherence >= 40:
            message += "You're doing okay. Try to prioritize excellent/good days for bigger savings."
        else:
            message += "Focus on charging during excellent/good rated days for maximum savings."

    return message


def main():
    """Main execution function"""
    logger.info("Starting monthly summary script")

    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded")

        # Get previous month's dates
        today = datetime.now()
        first_of_month = today.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        target_year = last_month.year
        target_month = last_month.month

        logger.info(f"Generating summary for {target_year}-{target_month:02d}")

        # Initialize clients
        data_store = DataStore()
        cost_tracker = CostTracker(data_store)

        # Get kWh per charge from config
        kwh_per_charge = config["user"]["typical_charge_kwh"]

        # Generate and save monthly summary
        logger.info("Aggregating monthly costs")
        summary = cost_tracker.get_monthly_summary(
            target_year, target_month, kwh_per_charge
        )

        # Save to cost history
        logger.info("Saving monthly aggregate")
        cost_tracker.save_monthly_aggregate(target_year, target_month, kwh_per_charge)

        # Get yearly projection
        logger.info("Calculating yearly projection")
        projection = cost_tracker.get_yearly_projection(kwh_per_charge)

        # Format notification
        message = format_monthly_summary(summary, projection, config)

        # Send notification
        logger.info("Sending monthly summary notification")
        pushover_client = PushoverClient(
            config["apis"]["pushover"]["user_key"],
            config["apis"]["pushover"]["api_token"],
        )

        success = pushover_client.send_notification(
            title="EV Optimizer: Monthly Charging Report",
            message=message,
            priority=0,
            sound="pushover",
            html=True,
        )

        if success:
            logger.info("Monthly summary sent successfully")
            return 0
        else:
            logger.error("Failed to send summary")
            return 1

    except Exception as e:
        logger.exception(f"Error in monthly summary script: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
