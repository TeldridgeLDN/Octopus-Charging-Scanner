#!/usr/bin/env python3
"""Weekly Summary Report Script

Analyzes past 7 days of recommendations vs actual actions.
Runs Sunday evenings at 18:00 via launchd.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any, List
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.data_store import DataStore
from modules.pushover import PushoverClient
import yaml
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/weekly_summary.log"),
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
    recommendations: List[Dict[str, Any]], user_actions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Analyze past 7 days of recommendations and user actions.

    Args:
        recommendations: List of daily recommendations
        user_actions: List of user charging actions

    Returns:
        Analysis summary dictionary
    """
    logger.info(
        f"Analyzing {len(recommendations)} recommendations "
        f"and {len(user_actions)} user actions"
    )

    # Count opportunities by rating
    rating_counts = {
        "EXCELLENT": 0,
        "GOOD": 0,
        "AVERAGE": 0,
        "POOR": 0,
    }

    # Separate weekend vs weekday tracking
    weekday_recs = []
    weekend_recs = []
    weekday_good_opps = 0
    weekend_good_opps = 0

    total_recommended_cost = 0.0
    total_recommended_carbon = 0
    total_savings_potential = 0.0

    for rec in recommendations:
        rating = rec.get("rating", "AVERAGE")
        rating_counts[rating] = rating_counts.get(rating, 0) + 1

        total_recommended_cost += rec.get("total_cost", 0)
        total_recommended_carbon += rec.get("total_carbon", 0)
        total_savings_potential += rec.get("savings", 0)

        # Separate by day type
        day_type = rec.get("day_type", "weekday")
        if day_type == "weekend":
            weekend_recs.append(rec)
            if rating in ["EXCELLENT", "GOOD"]:
                weekend_good_opps += 1
        else:
            weekday_recs.append(rec)
            if rating in ["EXCELLENT", "GOOD"]:
                weekday_good_opps += 1

    # Analyze user actions
    charges_completed = len(user_actions)
    charges_on_good_days = 0
    weekday_charges_good = 0
    weekend_charges_good = 0
    weekday_charges = 0
    weekend_charges = 0
    actual_cost = 0.0
    actual_carbon = 0

    # Create date lookup for recommendations
    rec_by_date = {rec.get("date"): rec for rec in recommendations}

    for action in user_actions:
        action_date = action.get("date")
        if action_date in rec_by_date:
            rec = rec_by_date[action_date]
            rating = rec.get("rating", "AVERAGE")
            day_type = rec.get("day_type", "weekday")

            # Track by day type
            if day_type == "weekend":
                weekend_charges += 1
                if rating in ["EXCELLENT", "GOOD"]:
                    weekend_charges_good += 1
            else:
                weekday_charges += 1
                if rating in ["EXCELLENT", "GOOD"]:
                    weekday_charges_good += 1

            # Count if charged on a good day
            if rating in ["EXCELLENT", "GOOD"]:
                charges_on_good_days += 1

            # Estimate actual cost (assume they followed recommendation)
            actual_cost += rec.get("total_cost", 0)
            actual_carbon += rec.get("total_carbon", 0)

    # Calculate adherence rates
    good_opportunities = rating_counts["EXCELLENT"] + rating_counts["GOOD"]
    adherence_rate = (
        (charges_on_good_days / good_opportunities * 100)
        if good_opportunities > 0
        else 0
    )

    # Calculate separate adherence for weekdays vs weekends
    weekday_adherence = (
        (weekday_charges_good / weekday_good_opps * 100) if weekday_good_opps > 0 else 0
    )
    weekend_adherence = (
        (weekend_charges_good / weekend_good_opps * 100) if weekend_good_opps > 0 else 0
    )

    # Calculate actual vs potential savings
    avg_baseline_cost = 4.50  # £4.50 for 30kWh @ ~15p/kWh
    potential_savings = charges_completed * avg_baseline_cost - actual_cost
    realized_savings_pct = (
        (potential_savings / total_savings_potential * 100)
        if total_savings_potential > 0
        else 0
    )

    return {
        "rating_counts": rating_counts,
        "good_opportunities": good_opportunities,
        "charges_completed": charges_completed,
        "charges_on_good_days": charges_on_good_days,
        "adherence_rate": adherence_rate,
        "weekday_adherence": weekday_adherence,
        "weekend_adherence": weekend_adherence,
        "weekday_good_opps": weekday_good_opps,
        "weekend_good_opps": weekend_good_opps,
        "weekday_charges": weekday_charges,
        "weekend_charges": weekend_charges,
        "weekday_charges_good": weekday_charges_good,
        "weekend_charges_good": weekend_charges_good,
        "avg_recommended_cost": (
            total_recommended_cost / len(recommendations) if recommendations else 0
        ),
        "avg_recommended_carbon": (
            total_recommended_carbon / len(recommendations) if recommendations else 0
        ),
        "actual_cost": actual_cost,
        "actual_carbon": actual_carbon,
        "potential_savings": potential_savings,
        "total_savings_potential": total_savings_potential,
        "realized_savings_pct": realized_savings_pct,
    }


def format_summary(analysis: Dict[str, Any], config: Dict[str, Any]) -> str:
    """Format weekly summary notification.

    Args:
        analysis: Weekly analysis results
        config: Configuration dictionary

    Returns:
        HTML-formatted summary message
    """
    rating_counts = analysis["rating_counts"]
    good_opps = analysis["good_opportunities"]
    charges = analysis["charges_completed"]
    charges_good = analysis["charges_on_good_days"]
    adherence = analysis["adherence_rate"]
    avg_cost = analysis["avg_recommended_cost"]
    actual_cost = analysis["actual_cost"]
    potential_savings = analysis["potential_savings"]
    realized_pct = analysis["realized_savings_pct"]

    message = "<b>📊 Weekly Charging Summary</b>\n\n"

    # Opportunities overview
    message += "<b>🎯 Opportunities this week:</b>\n"
    if rating_counts["EXCELLENT"] > 0:
        message += f"  ⚡ {rating_counts['EXCELLENT']} excellent days\n"
    if rating_counts["GOOD"] > 0:
        message += f"  ✅ {rating_counts['GOOD']} good days\n"
    if rating_counts["AVERAGE"] > 0:
        message += f"  🔌 {rating_counts['AVERAGE']} average days\n"
    message += "\n"

    # Performance metrics
    message += "<b>📈 Your performance:</b>\n"
    message += f"  Charges completed: {charges}\n"

    if good_opps > 0:
        message += f"  Charged on good days: {charges_good}/{good_opps}\n"
        message += f"  Adherence rate: {adherence:.0f}%\n"
    message += "\n"

    # Cost analysis
    message += "<b>💰 Cost analysis:</b>\n"

    if charges > 0:
        message += f"  Total spent: £{actual_cost:.2f}\n"
        message += f"  Avg per charge: £{actual_cost/charges:.2f}\n"

        if potential_savings > 0:
            message += f"  You saved: £{potential_savings:.2f}\n"
            message += f"  Savings rate: {realized_pct:.0f}%\n"
    else:
        message += f"  Recommended avg: £{avg_cost:.2f}/charge\n"

    # Add tip or encouragement
    message += "\n<b>💡 Tip:</b> "
    if adherence >= 80:
        message += "Excellent adherence! Keep it up! 🎉"
    elif adherence >= 60:
        message += "Good work! Try to catch more excellent days."
    elif adherence >= 40:
        message += "You're doing okay. Watch for excellent ratings!"
    else:
        message += "Try to charge on excellent/good days for max savings."

    return message


def add_forecast_accuracy(message: str, recommendations: List[Dict[str, Any]]) -> str:
    """Add forecast accuracy section to summary.

    Args:
        message: Current message
        recommendations: List of recommendations

    Returns:
        Updated message with forecast accuracy
    """
    try:
        from pathlib import Path
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from modules.forecast_tracker import ForecastTracker

        tracker = ForecastTracker()
        accuracy = tracker.get_recent_accuracy(days=7)
        grade = tracker.get_reliability_grade(days=7)

        if accuracy["num_comparisons"] >= 3:
            message += "\n<b>📈 Forecast Accuracy (7 days):</b>\n"
            message += f"  Grade: {grade}\n"
            message += f"  Avg Error: {accuracy['mean_absolute_error']:.2f}p/kWh\n"

            if accuracy["negative_pricing_predictions"] > 0:
                neg_acc = accuracy["negative_pricing_accuracy"]
                if neg_acc is not None:
                    message += f"  Negative pricing: {neg_acc*100:.0f}% accurate\n"

            message += f"  Trend: {accuracy['trend'].replace('_', ' ')}\n"
    except Exception as e:
        logger.debug(f"Could not add forecast accuracy: {e}")

    return message


def add_weekend_analysis(
    message: str, recommendations: List[Dict[str, Any]], analysis: Dict[str, Any]
) -> str:
    """Add weekend vs weekday analysis to summary.

    Args:
        message: Current message
        recommendations: List of recommendations
        analysis: Analysis results with adherence data

    Returns:
        Updated message with weekend analysis
    """
    # Separate weekend vs weekday
    weekday_recs = [r for r in recommendations if r.get("day_type") == "weekday"]
    weekend_recs = [r for r in recommendations if r.get("day_type") == "weekend"]

    if len(weekday_recs) >= 2 and len(weekend_recs) >= 1:
        message += "\n<b>📅 Weekend vs Weekday Patterns:</b>\n"

        # Calculate averages
        weekday_avg = (
            sum(r.get("avg_price", 0) for r in weekday_recs) / len(weekday_recs)
            if weekday_recs
            else 0
        )
        weekend_avg = (
            sum(r.get("avg_price", 0) for r in weekend_recs) / len(weekend_recs)
            if weekend_recs
            else 0
        )

        message += f"  Weekday avg: {weekday_avg:.1f}p/kWh ({len(weekday_recs)} days)\n"
        message += f"  Weekend avg: {weekend_avg:.1f}p/kWh ({len(weekend_recs)} days)\n"

        # Add adherence comparison
        weekday_adherence = analysis.get("weekday_adherence", 0)
        weekend_adherence = analysis.get("weekend_adherence", 0)
        weekday_good_opps = analysis.get("weekday_good_opps", 0)
        weekend_good_opps = analysis.get("weekend_good_opps", 0)

        if weekday_good_opps > 0 or weekend_good_opps > 0:
            message += "\n<b>📊 Adherence by day type:</b>\n"

            if weekday_good_opps > 0:
                message += f"  Weekdays: {weekday_adherence:.0f}% ({analysis.get('weekday_charges_good', 0)}/{weekday_good_opps})\n"

            if weekend_good_opps > 0:
                message += f"  Weekends: {weekend_adherence:.0f}% ({analysis.get('weekend_charges_good', 0)}/{weekend_good_opps})\n"

        # Price comparison insight
        message += "\n<b>💡 Insight:</b> "
        if weekend_avg < weekday_avg - 2:
            message += "Weekends are cheaper - prioritize weekend charging!\n"

            if weekend_adherence < weekday_adherence - 10:
                message += "  ⚠️ You're following weekday recommendations more than weekend ones.\n"
                message += "  Consider planning Sunday charges in advance!"

        elif weekday_avg < weekend_avg - 2:
            message += "Weekdays are cheaper this week - weekday charging is better!\n"

            if weekday_adherence < weekend_adherence - 10:
                message += "  ⚠️ Try to catch those cheaper weekday opportunities!"

        else:
            message += "Similar pricing throughout week\n"

            # Check for behavior patterns
            if abs(weekday_adherence - weekend_adherence) > 15:
                if weekend_adherence > weekday_adherence:
                    message += (
                        "  📈 You charge more reliably on weekends - good routine!\n"
                    )
                else:
                    message += (
                        "  📈 You charge more reliably on weekdays - good routine!\n"
                    )

    return message


def add_acix_insights(
    message: str, data_store: DataStore, config: Dict[str, Any]
) -> str:
    """Add ACIX behavioral insights to weekly summary.

    Uses actual detected charging sessions to provide behavior analysis.

    Args:
        message: Current message
        data_store: DataStore instance
        config: Configuration dictionary

    Returns:
        Updated message with ACIX insights
    """
    acix_config = config.get("acix", {})
    if not acix_config.get("enabled", False):
        return message

    try:
        from modules.recommendation_analyzer import RecommendationAnalyzer

        analyzer = RecommendationAnalyzer(data_store)
        metrics = analyzer.analyze_period(days=7)

        if metrics.total_sessions == 0:
            return message

        message += "\n<b>🧠 ACIX Charging Intelligence:</b>\n"
        message += f"  Sessions detected: {metrics.total_sessions}\n"

        # Timing analysis
        if metrics.sessions_analyzed > 0:
            message += f"  Timing score: {metrics.avg_timing_score:.0f}/100\n"

            # Compliance breakdown
            if metrics.optimal_count > 0:
                message += f"  ✅ Optimal timing: {metrics.optimal_count}\n"
            if metrics.partial_count > 0:
                message += f"  🔶 Partial overlap: {metrics.partial_count}\n"
            if metrics.suboptimal_count > 0:
                message += f"  ❌ Missed window: {metrics.suboptimal_count}\n"

            # Compliance rate
            message += f"  Compliance rate: {metrics.compliance_rate:.0f}%\n"

        # Savings analysis
        message += "\n<b>💵 Savings Analysis:</b>\n"
        message += f"  Captured: £{metrics.total_savings_captured:.2f}\n"

        if metrics.total_savings_missed > 0.10:
            message += f"  Missed: £{metrics.total_savings_missed:.2f}\n"

        if metrics.improvement_potential > 1.0:
            message += f"  Monthly potential: £{metrics.improvement_potential:.2f}\n"

        # Patterns detected
        patterns = metrics.patterns
        if patterns:
            message += "\n<b>📊 Detected Patterns:</b>\n"

            avg_hour = patterns.get("avg_start_hour")
            if avg_hour is not None:
                hour_str = f"{int(avg_hour)}:{int((avg_hour % 1) * 60):02d}"
                message += f"  Avg plug-in time: {hour_str}\n"

            if patterns.get("late_start_ratio", 0) > 0.3:
                late_pct = int(patterns["late_start_ratio"] * 100)
                message += f"  ⚠️ Late starts: {late_pct}% of sessions\n"

            if patterns.get("consistent_timing", False):
                message += "  ✅ Consistent charging schedule\n"
            elif patterns.get("start_time_variance", 0) > 6:
                message += "  📈 Variable charging times\n"

            if patterns.get("avg_kwh"):
                message += f"  Avg charge: {patterns['avg_kwh']:.1f} kWh\n"

        # Top recommendation
        if metrics.recommendations:
            message += "\n<b>💡 ACIX Recommendation:</b>\n"
            # Get most actionable recommendation (not "Great job")
            for rec in metrics.recommendations:
                if "Great job" not in rec and "Keep monitoring" not in rec:
                    message += f"  {rec}\n"
                    break
            else:
                # All recommendations are positive
                message += f"  {metrics.recommendations[0]}\n"

    except Exception as e:
        logger.warning(f"Could not add ACIX insights: {e}")

    return message


def add_monthly_cost_section(message: str, config: Dict[str, Any]) -> str:
    """Add month-to-date cost tracking to weekly summary.

    Args:
        message: Current message
        config: Configuration dictionary

    Returns:
        Updated message with month-to-date costs
    """
    try:
        from pathlib import Path
        import sys
        from datetime import datetime

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from modules.cost_tracker import CostTracker

        tracker = CostTracker()
        current_year = datetime.now().year
        current_month = datetime.now().month
        kwh_per_charge = config["user"]["typical_charge_kwh"]

        # Get current month's summary
        summary = tracker.get_monthly_summary(
            current_year, current_month, kwh_per_charge
        )

        if summary["num_charges"] > 0:
            message += "\n<b>📅 Month-to-Date ({})</b>\n".format(
                datetime.now().strftime("%B")
            )
            message += f"  Total spent: £{summary['total_cost']:.2f}\n"
            message += f"  Charges: {summary['num_charges']}\n"
            message += f"  Saved vs standard: £{summary['baseline_comparisons']['standard_savings']:.2f}\n"

            # Show adherence
            if summary["good_opportunities"] > 0:
                message += f"  Monthly adherence: {summary['adherence_rate']:.0f}%\n"

    except Exception as e:
        logger.debug(f"Could not add monthly cost section: {e}")

    return message


def add_week_ahead_section(message: str, config: Dict[str, Any]) -> str:
    """Add best forecast days for the coming week to the summary.

    Fetches agile_predict day summaries for the next 7 days and ranks them
    by average predicted price, highlighting the best charging days ahead.

    Args:
        message: Current message
        config: Configuration dictionary

    Returns:
        Updated message with week-ahead forecast section
    """
    try:
        from modules.agile_predict_api import AgilePredict

        region = config["user"]["region"]
        client = AgilePredict()
        summaries = client.get_day_summary(region, days=7)

        if not summaries:
            return message

        # Skip today (index 0) — we only want future days
        future = summaries[1:]
        if not future:
            return message

        # Rank by avg predicted price (cheapest first)
        ranked = sorted(future, key=lambda s: s["avg_pred"])

        message += "\n<b>📅 Best days to charge next week:</b>\n"

        from datetime import date as date_type

        today = date_type.today()

        for entry in ranked[:4]:  # Show top 4 days
            try:
                entry_date = date_type.fromisoformat(entry["date"])
                delta = (entry_date - today).days
                if delta == 1:
                    label = "Tomorrow"
                else:
                    label = entry_date.strftime("%A")
            except ValueError:
                label = entry["date"]

            price = entry["avg_pred"]
            confidence = entry["confidence"]

            # Star the cheapest day
            star = " ⭐" if entry == ranked[0] else ""
            message += f"  {label}: {price:.1f}p/kWh ({confidence}){star}\n"

        logger.info(
            f"Week ahead section added: best day is "
            f"{ranked[0]['date']} at {ranked[0]['avg_pred']:.1f}p/kWh"
        )

    except Exception as e:
        logger.debug(f"Could not add week-ahead section: {e}")

    return message


def main():
    """Main execution function"""
    logger.info("Starting weekly summary script")

    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded")

        # Initialize clients
        data_store = DataStore()

        # Get past 7 days of recommendations
        logger.info("Fetching past 7 days of recommendations")
        recommendations = data_store.get_recommendations(days=7)

        if not recommendations:
            logger.warning("No recommendations found for past 7 days")
            return 0

        logger.info(f"Found {len(recommendations)} recommendations")

        # Get past 7 days of user actions
        logger.info("Fetching past 7 days of user actions")
        user_actions = data_store.get_user_actions(days=7)
        logger.info(f"Found {len(user_actions)} user actions")

        # Analyze the week
        logger.info("Analyzing weekly performance")
        analysis = analyze_week(recommendations, user_actions)

        # Format summary
        message = format_summary(analysis, config)

        # Add weekend/weekday analysis (Phase 2 Feature #8)
        message = add_weekend_analysis(message, recommendations, analysis)

        # Add ACIX behavioral insights (Phase 3 Task 11)
        message = add_acix_insights(message, data_store, config)

        # Add forecast accuracy (Phase 1 Feature #1)
        message = add_forecast_accuracy(message, recommendations)

        # Add month-to-date cost tracking (Phase 2 Feature #7)
        message = add_monthly_cost_section(message, config)

        # Add agile_predict week-ahead forecast
        message = add_week_ahead_section(message, config)

        # Send notification
        logger.info("Sending weekly summary notification")
        pushover_client = PushoverClient(
            config["apis"]["pushover"]["user_key"],
            config["apis"]["pushover"]["api_token"],
        )

        success = pushover_client.send_notification(
            title="EV Optimizer: Weekly Charging Summary",
            message=message,
            priority=0,
            sound="pushover",
            html=True,
        )

        if success:
            logger.info("Weekly summary sent successfully")
            return 0
        else:
            logger.error("Failed to send summary")
            return 1

    except Exception as e:
        logger.exception(f"Error in weekly summary script: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
