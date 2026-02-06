"""Historical Cost Tracking Module

Tracks charging costs over time, calculates monthly summaries,
and provides ROI visibility through baseline comparisons.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import logging

from .data_store import DataStore

logger = logging.getLogger(__name__)


class CostTracker:
    """Tracks historical charging costs and calculates savings.

    Aggregates daily charging costs into monthly summaries and compares
    against baseline charging patterns to calculate ROI.
    """

    # Baseline rates for comparison
    STANDARD_BASELINE_RATE = 15.0  # pence/kWh - typical UK electricity rate
    PEAK_BASELINE_RATE = 20.0  # pence/kWh - evening charging fallback

    def __init__(self, data_store: Optional[DataStore] = None):
        """Initialize cost tracker.

        Args:
            data_store: Optional DataStore instance (creates new if not provided)
        """
        self.data_store = data_store or DataStore()
        self.COST_HISTORY_FILE = self.data_store.DATA_DIR / "cost_history.json"
        logger.info("Cost tracker initialized")

    def aggregate_month(
        self, year: int, month: int, kwh_per_charge: float = 30.0
    ) -> Dict[str, Any]:
        """Aggregate costs for a specific month.

        Args:
            year: Year to aggregate
            month: Month to aggregate (1-12)
            kwh_per_charge: kWh per charge for baseline calculations

        Returns:
            Dictionary with monthly cost metrics:
                - total_cost: Total amount spent charging
                - total_savings: Total savings vs baseline
                - num_charges: Number of charges completed
                - avg_cost_per_charge: Average cost per charge
                - adherence_rate: Percentage of charges on good days
                - charges_by_rating: Count by opportunity rating
        """
        logger.info(f"Aggregating costs for {year}-{month:02d}")

        # Get all recommendations and user actions for the month
        # We need more than 30 days if month > 30 days, so get extra
        all_recommendations = self.data_store.get_recommendations(days=90)
        all_actions = self.data_store.get_user_actions(days=90)

        # Filter to specific month
        recommendations = [
            r
            for r in all_recommendations
            if self._is_in_month(r.get("date"), year, month)
        ]

        actions = [
            a for a in all_actions if self._is_in_month(a.get("date"), year, month)
        ]

        logger.debug(
            f"Found {len(recommendations)} recommendations "
            f"and {len(actions)} actions for {year}-{month:02d}"
        )

        # Calculate metrics
        total_cost = 0.0
        total_savings = 0.0
        charges_on_good_days = 0
        charges_by_rating = {"EXCELLENT": 0, "GOOD": 0, "AVERAGE": 0, "POOR": 0}

        # Create date lookup for recommendations
        rec_by_date = {rec.get("date"): rec for rec in recommendations}

        # Calculate actual costs from user actions
        for action in actions:
            action_date = action.get("date")
            if action_date in rec_by_date:
                rec = rec_by_date[action_date]
                cost = rec.get("total_cost", 0)
                savings = rec.get("savings", 0)
                rating = rec.get("rating", "AVERAGE")

                total_cost += cost
                total_savings += savings

                # Track adherence
                if rating in ["EXCELLENT", "GOOD"]:
                    charges_on_good_days += 1

                # Track by rating
                charges_by_rating[rating] = charges_by_rating.get(rating, 0) + 1

        num_charges = len(actions)

        # Count good opportunities
        good_opportunities = sum(
            1 for rec in recommendations if rec.get("rating") in ["EXCELLENT", "GOOD"]
        )

        # Calculate adherence rate
        adherence_rate = (
            (charges_on_good_days / good_opportunities * 100)
            if good_opportunities > 0
            else 0
        )

        # Calculate average cost
        avg_cost_per_charge = total_cost / num_charges if num_charges > 0 else 0

        return {
            "year": year,
            "month": month,
            "total_cost": round(total_cost, 2),
            "total_savings": round(total_savings, 2),
            "num_charges": num_charges,
            "avg_cost_per_charge": round(avg_cost_per_charge, 2),
            "adherence_rate": round(adherence_rate, 1),
            "charges_on_good_days": charges_on_good_days,
            "good_opportunities": good_opportunities,
            "charges_by_rating": charges_by_rating,
        }

    def calculate_baseline_comparisons(
        self, actual_cost: float, num_charges: int, kwh_per_charge: float = 30.0
    ) -> Dict[str, float]:
        """Calculate savings vs standard and peak baselines.

        Args:
            actual_cost: Actual amount spent (£)
            num_charges: Number of charges
            kwh_per_charge: kWh per charge

        Returns:
            Dictionary with baseline comparisons:
                - standard_baseline_cost: Cost at 15p/kWh
                - peak_baseline_cost: Cost at 20p/kWh
                - standard_savings: Savings vs 15p/kWh
                - peak_savings: Savings vs 20p/kWh
        """
        total_kwh = num_charges * kwh_per_charge

        # Calculate baseline costs (convert pence to £)
        standard_baseline_cost = (total_kwh * self.STANDARD_BASELINE_RATE) / 100
        peak_baseline_cost = (total_kwh * self.PEAK_BASELINE_RATE) / 100

        # Calculate savings
        standard_savings = standard_baseline_cost - actual_cost
        peak_savings = peak_baseline_cost - actual_cost

        return {
            "standard_baseline_cost": round(standard_baseline_cost, 2),
            "peak_baseline_cost": round(peak_baseline_cost, 2),
            "standard_savings": round(standard_savings, 2),
            "peak_savings": round(peak_savings, 2),
        }

    def get_monthly_summary(
        self, year: int, month: int, kwh_per_charge: float = 30.0
    ) -> Dict[str, Any]:
        """Get complete monthly cost summary with baseline comparisons.

        Args:
            year: Year to summarize
            month: Month to summarize (1-12)
            kwh_per_charge: kWh per charge for calculations

        Returns:
            Complete monthly summary dictionary
        """
        logger.info(f"Generating monthly summary for {year}-{month:02d}")

        # Get aggregated metrics
        metrics = self.aggregate_month(year, month, kwh_per_charge)

        # Calculate baseline comparisons
        if metrics["num_charges"] > 0:
            baselines = self.calculate_baseline_comparisons(
                metrics["total_cost"], metrics["num_charges"], kwh_per_charge
            )
        else:
            baselines = {
                "standard_baseline_cost": 0.0,
                "peak_baseline_cost": 0.0,
                "standard_savings": 0.0,
                "peak_savings": 0.0,
            }

        # Combine into full summary
        summary = {
            **metrics,
            "baseline_comparisons": baselines,
            "kwh_per_charge": kwh_per_charge,
            "generated_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Monthly summary: {metrics['num_charges']} charges, "
            f"£{metrics['total_cost']:.2f} spent, "
            f"£{baselines['standard_savings']:.2f} saved"
        )

        return summary

    def save_monthly_aggregate(
        self, year: int, month: int, kwh_per_charge: float = 30.0
    ) -> None:
        """Save monthly aggregate to cost history file.

        Args:
            year: Year to aggregate
            month: Month to aggregate (1-12)
            kwh_per_charge: kWh per charge for calculations
        """
        logger.info(f"Saving monthly aggregate for {year}-{month:02d}")

        # Get summary
        summary = self.get_monthly_summary(year, month, kwh_per_charge)

        # Load existing history
        history = self._load_cost_history()

        # Remove any existing entry for this month
        history["monthly_summaries"] = [
            s
            for s in history["monthly_summaries"]
            if not (s["year"] == year and s["month"] == month)
        ]

        # Add new summary
        history["monthly_summaries"].append(summary)

        # Sort by year and month (most recent first)
        history["monthly_summaries"].sort(
            key=lambda x: (x["year"], x["month"]), reverse=True
        )

        # Save
        self._save_cost_history(history)
        logger.info(f"Saved monthly aggregate for {year}-{month:02d}")

    def get_cost_history(self, months: int = 12) -> List[Dict[str, Any]]:
        """Get historical monthly aggregates.

        Args:
            months: Number of months to retrieve (default: 12)

        Returns:
            List of monthly summaries, most recent first
        """
        history = self._load_cost_history()
        summaries = history.get("monthly_summaries", [])

        # Return most recent N months
        return summaries[:months]

    def get_yearly_projection(self, kwh_per_charge: float = 30.0) -> Dict[str, Any]:
        """Project annual savings based on current year's data.

        Args:
            kwh_per_charge: kWh per charge for calculations

        Returns:
            Dictionary with year-to-date and projected annual metrics
        """
        current_year = datetime.now().year

        # Get all summaries for current year
        history = self._load_cost_history()
        year_summaries = [
            s for s in history.get("monthly_summaries", []) if s["year"] == current_year
        ]

        if not year_summaries:
            logger.info("No data for current year, cannot project")
            return {
                "year": current_year,
                "ytd_cost": 0.0,
                "ytd_savings": 0.0,
                "ytd_charges": 0,
                "projected_annual_cost": 0.0,
                "projected_annual_savings": 0.0,
                "projected_annual_charges": 0,
                "months_of_data": 0,
            }

        # Calculate year-to-date totals
        ytd_cost = sum(s["total_cost"] for s in year_summaries)
        ytd_savings = sum(
            s["baseline_comparisons"]["standard_savings"] for s in year_summaries
        )
        ytd_charges = sum(s["num_charges"] for s in year_summaries)
        months_of_data = len(year_summaries)

        # Project to full year
        if months_of_data > 0:
            monthly_avg_cost = ytd_cost / months_of_data
            monthly_avg_savings = ytd_savings / months_of_data
            monthly_avg_charges = ytd_charges / months_of_data

            projected_annual_cost = monthly_avg_cost * 12
            projected_annual_savings = monthly_avg_savings * 12
            projected_annual_charges = monthly_avg_charges * 12
        else:
            projected_annual_cost = 0.0
            projected_annual_savings = 0.0
            projected_annual_charges = 0.0

        return {
            "year": current_year,
            "ytd_cost": round(ytd_cost, 2),
            "ytd_savings": round(ytd_savings, 2),
            "ytd_charges": int(ytd_charges),
            "projected_annual_cost": round(projected_annual_cost, 2),
            "projected_annual_savings": round(projected_annual_savings, 2),
            "projected_annual_charges": int(projected_annual_charges),
            "months_of_data": months_of_data,
        }

    def _is_in_month(self, date_str: Optional[str], year: int, month: int) -> bool:
        """Check if a date string is in the specified month.

        Args:
            date_str: Date string in ISO format (YYYY-MM-DD)
            year: Target year
            month: Target month (1-12)

        Returns:
            True if date is in the specified month
        """
        if not date_str:
            return False

        try:
            date = datetime.fromisoformat(date_str.split("T")[0])
            return date.year == year and date.month == month
        except (ValueError, AttributeError):
            logger.warning(f"Invalid date format: {date_str}")
            return False

    def _load_cost_history(self) -> Dict[str, Any]:
        """Load cost history from file.

        Returns:
            Cost history dictionary with monthly_summaries list
        """
        if not self.COST_HISTORY_FILE.exists():
            logger.debug("Cost history file does not exist, returning empty")
            return {"monthly_summaries": []}

        try:
            with open(self.COST_HISTORY_FILE, "r") as f:
                data = json.load(f)
                logger.debug(
                    f"Loaded {len(data.get('monthly_summaries', []))} monthly summaries"
                )
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load cost history: {e}")
            return {"monthly_summaries": []}

    def _save_cost_history(self, history: Dict[str, Any]) -> None:
        """Save cost history to file.

        Args:
            history: Cost history dictionary to save
        """
        try:
            with open(self.COST_HISTORY_FILE, "w") as f:
                json.dump(history, f, indent=2, default=str)
            logger.debug("Saved cost history")
        except IOError as e:
            logger.error(f"Failed to save cost history: {e}")
            raise
