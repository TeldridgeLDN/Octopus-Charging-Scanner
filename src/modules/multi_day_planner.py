"""Multi-Day Planning Module

Compares charging costs across multiple days (default 7) to help users
make informed deferral decisions. Uses actual Octopus prices when available,
falls back to Guy Lipman forecasts for days beyond 48 hours.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import logging

from .octopus_api import OctopusAPIClient
from .forecast_api import ForecastAPIClient
from .carbon_api import CarbonAPIClient
from .analyzer import (
    Analyzer,
    PriceSlot,
    CarbonSlot,
    OpportunityRating,
)
from .data_store import DataStore

logger = logging.getLogger(__name__)


@dataclass
class DayComparison:
    """Comparison data for a single day's charging opportunity"""

    date: str  # ISO format YYYY-MM-DD
    day_name: str  # "Today", "Tomorrow", "Day After"
    avg_price: float  # pence/kWh
    optimal_window: Dict[str, str]  # {start, end} in ISO format
    cost: float  # £ for specified kWh
    rating: str  # OpportunityRating value
    price_source: str  # "octopus_actual" or "forecast"
    savings_vs_today: float  # £ (0 for today, positive/negative for others)
    avg_carbon: int  # gCO2/kWh


@dataclass
class MultiDayPlan:
    """Complete multi-day charging plan (up to 7 days)"""

    timestamp: str  # ISO format
    kwh_amount: float  # kWh being charged
    num_days: int  # Number of days in the plan
    days: List[DayComparison]
    best_day: Dict[str, Any]  # {date, day_name, reason, savings, percentage}


class MultiDayPlanner:
    """Generate multi-day charging cost comparisons.

    Fetches price data for up to 7 days, calculates optimal charging
    windows for each, and identifies the cheapest option. Uses Octopus
    actual prices for days 0-1, Guy Lipman forecasts for days 2-6.
    """

    # Day names for display
    DAY_NAMES = [
        "Today",
        "Tomorrow",
        "Day 3",
        "Day 4",
        "Day 5",
        "Day 6",
        "Day 7",
    ]

    def __init__(
        self,
        config: Dict[str, Any],
        analyzer: Analyzer,
        data_store: DataStore,
        num_days: int = 7,
    ):
        """Initialize planner.

        Args:
            config: Configuration dictionary
            analyzer: Analyzer instance for window finding
            data_store: DataStore instance for persistence
            num_days: Number of days to plan (default 7, max 7)
        """
        self.config = config
        self.analyzer = analyzer
        self.data_store = data_store
        self.num_days = min(num_days, 7)  # Cap at 7 days (forecast limit)
        self.octopus_client = OctopusAPIClient()
        self.forecast_client = ForecastAPIClient()
        self.carbon_client = CarbonAPIClient()

    def generate_plan(self, kwh: Optional[float] = None) -> MultiDayPlan:
        """Generate complete multi-day charging plan.

        Args:
            kwh: Amount to charge in kWh (uses config default if not provided)

        Returns:
            MultiDayPlan with comparisons and recommendation
        """
        if kwh is None:
            kwh = self.config["user"]["typical_charge_kwh"]

        logger.info(f"Generating {self.num_days}-day plan for {kwh}kWh charge")

        # Get price data for all days
        multi_day_data = self._get_multi_day_prices()

        # Compare each day
        comparisons = self._compare_days(multi_day_data, kwh)

        # Record forecast evolution snapshots
        self._record_evolution_snapshots(comparisons)

        # Identify best day
        best_day = self._identify_best_day(comparisons)

        plan = MultiDayPlan(
            timestamp=datetime.now(timezone.utc).isoformat(),
            kwh_amount=kwh,
            num_days=self.num_days,
            days=comparisons,
            best_day=best_day,
        )

        # Save plan to data store
        self._save_plan(plan)

        logger.info(f"Plan generated: Best day is {best_day['day_name']}")
        return plan

    def _get_multi_day_prices(
        self,
    ) -> List[Tuple[datetime, List[PriceSlot], List[CarbonSlot], str]]:
        """Fetch price and carbon data for multiple days.

        Returns:
            List of tuples: (date, price_slots, carbon_slots, price_source)
        """
        region = self.config["user"]["region"]
        postcode = self.config["user"]["postcode"]
        charge_hours = (
            self.config["user"]["typical_charge_kwh"]
            / self.config["user"]["charging_rate_kw"]
        )

        logger.info(f"Fetching {self.num_days}-day price data")

        # Try to fetch Octopus data (covers up to 48 hours)
        try:
            octopus_prices = self.octopus_client.get_prices(region, hours=48)
            logger.info(f"Fetched {len(octopus_prices)} Octopus price slots")
        except Exception as e:
            logger.error(f"Failed to fetch Octopus prices: {e}")
            octopus_prices = []

        # Get carbon data
        try:
            carbon_data = self.carbon_client.get_intensity(postcode)
            logger.info(f"Fetched {len(carbon_data)} carbon slots")
        except Exception as e:
            logger.warning(f"Failed to fetch carbon data: {e}")
            carbon_data = []

        # Process each day
        multi_day_data = []
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        for day_offset in range(self.num_days):
            target_date = today + timedelta(days=day_offset)
            day_end = target_date + timedelta(days=1)

            # Filter prices for this day
            day_prices = []
            price_source = "unknown"

            if octopus_prices:
                # Convert Octopus data to PriceSlot objects for this day
                for p in octopus_prices:
                    slot_time = datetime.fromisoformat(
                        p["valid_from"].replace("Z", "+00:00")
                    )
                    if target_date <= slot_time < day_end:
                        day_prices.append(
                            PriceSlot(slot_time, p["value_inc_vat"], "octopus")
                        )

                # Check if we have enough coverage for overnight charging
                # Need at least charge_hours + 4 slots (2 hours buffer)
                if len(day_prices) >= int(charge_hours * 2) + 4:
                    price_source = "octopus_actual"
                    logger.info(
                        f"Day {day_offset}: Using Octopus actual prices "
                        f"({len(day_prices)} slots)"
                    )
                else:
                    # Not enough Octopus coverage, use forecast
                    day_prices = []

            # Fall back to forecast if needed
            if not day_prices:
                logger.info(f"Day {day_offset}: Falling back to forecast")
                try:
                    forecasts = self.forecast_client.get_forecasts(region)

                    for f in forecasts:
                        # Handle both old format (date+time) and new format (ISO time)
                        if "date" in f:
                            # Old table-parsed format: {"date": "2025-12-07", "time": "00:00"}
                            date_str = f["date"]
                            time_str = f["time"]
                            dt_str = f"{date_str}T{time_str}:00+00:00"
                            slot_time = datetime.fromisoformat(dt_str)
                        else:
                            # New JavaScript-parsed format: {"time": "2025-12-07T00:00:00"}
                            time_str = f["time"]
                            # Handle both naive and timezone-aware formats
                            if "+" in time_str or time_str.endswith("Z"):
                                slot_time = datetime.fromisoformat(
                                    time_str.replace("Z", "+00:00")
                                )
                            else:
                                slot_time = datetime.fromisoformat(time_str).replace(
                                    tzinfo=timezone.utc
                                )

                        if target_date <= slot_time < day_end:
                            day_prices.append(
                                PriceSlot(slot_time, f["price"], "forecast")
                            )

                    price_source = "forecast"
                    logger.info(
                        f"Day {day_offset}: Using forecast ({len(day_prices)} slots)"
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch forecast for day {day_offset}: {e}")
                    # Use empty list, will be handled later

            # Filter carbon data for this day
            day_carbon = []
            for c in carbon_data:
                slot_time = datetime.fromisoformat(c["time"].replace("Z", "+00:00"))
                if target_date <= slot_time < day_end:
                    day_carbon.append(CarbonSlot(slot_time, c["intensity"]))

            # If no carbon data, use neutral values
            if not day_carbon:
                for price_slot in day_prices:
                    day_carbon.append(CarbonSlot(price_slot.time, 175))

            multi_day_data.append((target_date, day_prices, day_carbon, price_source))

        return multi_day_data

    def _compare_days(
        self,
        multi_day_data: List[Tuple[datetime, List[PriceSlot], List[CarbonSlot], str]],
        kwh: float,
    ) -> List[DayComparison]:
        """Compare charging costs across multiple days.

        Args:
            multi_day_data: Price/carbon data for each day
            kwh: Amount to charge

        Returns:
            List of DayComparison objects
        """
        charge_hours = kwh / self.config["user"]["charging_rate_kw"]
        comparisons = []

        for idx, (target_date, price_slots, carbon_slots, price_source) in enumerate(
            multi_day_data
        ):
            if not price_slots:
                logger.warning(f"No price data for day {idx}, skipping")
                continue

            # Find optimal window for this day
            baseline_time = target_date.replace(hour=18, minute=0, second=0)
            window = self.analyzer.find_optimal_window(
                price_slots, carbon_slots, charge_hours, baseline_time
            )

            comparison = DayComparison(
                date=target_date.date().isoformat(),
                day_name=self.DAY_NAMES[idx],
                avg_price=window.avg_price,
                optimal_window={
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                },
                cost=window.total_cost,
                rating=window.rating.value,
                price_source=price_source,
                savings_vs_today=0.0,  # Will calculate after we have all days
                avg_carbon=window.avg_carbon,
            )

            comparisons.append(comparison)

        # Calculate savings relative to today
        if comparisons:
            today_cost = comparisons[0].cost
            for comp in comparisons:
                comp.savings_vs_today = today_cost - comp.cost

        return comparisons

    def _identify_best_day(self, comparisons: List[DayComparison]) -> Dict[str, Any]:
        """Identify the best day to charge based on cost.

        Args:
            comparisons: List of day comparisons

        Returns:
            Dictionary with best day info
        """
        if not comparisons:
            raise ValueError("No days to compare")

        # Sort by cost (cheapest first)
        sorted_days = sorted(comparisons, key=lambda x: x.cost)
        best = sorted_days[0]
        today = comparisons[0]

        # Calculate savings and percentage
        savings = today.cost - best.cost
        if today.cost > 0:
            percentage = (savings / today.cost) * 100
        else:
            percentage = 0.0

        # Build reason string
        if best.date == today.date:
            reason = "Today has the best prices"
        else:
            if best.rating == OpportunityRating.EXCELLENT.value:
                reason = f"Excellent prices on {best.day_name}"
            elif savings >= 2.0:
                reason = f"Significant savings on {best.day_name}"
            else:
                reason = f"Slightly cheaper on {best.day_name}"

            # Add percentage to reason
            reason += f" ({percentage:.0f}% cheaper than today)"

        return {
            "date": best.date,
            "day_name": best.day_name,
            "reason": reason,
            "savings": savings,
            "percentage": percentage,
        }

    def _save_plan(self, plan: MultiDayPlan) -> None:
        """Save plan to data store.

        Args:
            plan: MultiDayPlan to save
        """
        try:
            # Convert to dict for JSON serialization
            plan_dict = asdict(plan)

            # Load existing plans
            plans_file = self.data_store.DATA_DIR / "multi_day_plans.json"
            if plans_file.exists():
                plans = self.data_store._load_json(plans_file, default=[])
            else:
                plans = []

            plans.append(plan_dict)

            # Keep last 30 days
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            plans = [
                p for p in plans if datetime.fromisoformat(p["timestamp"]) >= cutoff
            ]

            # Save
            self.data_store._save_json(plans_file, plans)
            logger.info("Multi-day plan saved")

        except Exception as e:
            logger.error(f"Failed to save plan: {e}")

    def _record_evolution_snapshots(self, comparisons: List[DayComparison]) -> None:
        """Record forecast evolution snapshots for each day.

        Args:
            comparisons: List of day comparisons from the plan
        """
        try:
            from .forecast_evolution import ForecastEvolutionTracker
            from .forecast_tracker import ForecastTracker

            evolution_tracker = ForecastEvolutionTracker()
            forecast_tracker = ForecastTracker()

            # Get historical accuracy for confidence calculation
            accuracy = forecast_tracker.get_recent_accuracy(7)
            historical_mae = accuracy.get("mean_absolute_error") if accuracy else None

            # Record snapshot for each future day
            for comparison in comparisons:
                evolution_tracker.record_snapshot(
                    target_date=comparison.date,
                    day_comparison=comparison,
                    historical_mae=historical_mae,
                )

            logger.info(f"Recorded evolution snapshots for {len(comparisons)} days")

        except Exception as e:
            # Log but don't fail the plan generation
            logger.warning(f"Failed to record evolution snapshots: {e}")
