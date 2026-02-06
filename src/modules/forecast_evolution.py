"""Forecast Evolution Tracker

Tracks how price forecasts evolve over time for target charging dates.
Records snapshots as predictions change, detects significant drift,
and provides confidence scores based on forecast reliability.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


class ForecastEvolutionTracker:
    """Track forecast evolution for target charging dates.

    Records snapshots of predictions as time progresses toward target dates,
    calculates confidence scores, and detects significant forecast changes.
    """

    EVOLUTION_FILE = Path("data/forecast_evolution.json")
    SIGNIFICANT_CHANGE_THRESHOLD = 10  # Percentage points
    RETENTION_DAYS = 30

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize evolution tracker.

        Args:
            data_dir: Optional custom data directory path
        """
        if data_dir:
            self.data_dir = Path(data_dir)
            self.EVOLUTION_FILE = self.data_dir / "forecast_evolution.json"
        else:
            self.data_dir = Path("data")

        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Forecast evolution tracker initialized at {self.data_dir}")

    def record_snapshot(
        self,
        target_date: str,
        day_comparison: Any,
        historical_mae: Optional[float] = None,
    ) -> None:
        """Record a forecast snapshot for a target date.

        Args:
            target_date: Target charging date (YYYY-MM-DD)
            day_comparison: DayComparison object with forecast data
            historical_mae: Mean absolute error from forecast accuracy tracking
        """
        today = datetime.now(timezone.utc).date()
        target = datetime.strptime(target_date, "%Y-%m-%d").date()

        # Skip if target date has passed
        if target < today:
            logger.debug(f"Skipping snapshot for past date: {target_date}")
            return

        days_until_target = (target - today).days

        # Calculate confidence score
        price_source = getattr(day_comparison, "price_source", "unknown")
        confidence = self._calculate_confidence(
            days_until_target, price_source, historical_mae
        )

        # Calculate savings percentage relative to today
        savings_pct = 0.0
        if hasattr(day_comparison, "savings_vs_today") and hasattr(
            day_comparison, "cost"
        ):
            today_cost = day_comparison.cost + day_comparison.savings_vs_today
            if today_cost > 0:
                savings_pct = (day_comparison.savings_vs_today / today_cost) * 100

        # Build snapshot
        snapshot = {
            "snapshot_date": today.isoformat(),
            "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
            "days_until_target": days_until_target,
            "price_source": price_source,
            "predicted_avg_price": getattr(day_comparison, "avg_price", 0.0),
            "predicted_cost": getattr(day_comparison, "cost", 0.0),
            "predicted_savings_pct": round(savings_pct, 2),
            "rating": getattr(day_comparison, "rating", "UNKNOWN"),
            "optimal_window": getattr(day_comparison, "optimal_window", {}),
            "confidence_score": confidence,
        }

        # Load existing data
        evolution_data = self._load_evolution_data()

        # Initialize target if not exists
        if target_date not in evolution_data["target_forecasts"]:
            evolution_data["target_forecasts"][target_date] = {
                "target_date": target_date,
                "snapshots": [],
                "evolution_summary": None,
                "actual_result": None,
            }

        target_data = evolution_data["target_forecasts"][target_date]

        # Check for existing snapshot today and replace if exists
        target_data["snapshots"] = [
            s
            for s in target_data["snapshots"]
            if s["snapshot_date"] != today.isoformat()
        ]

        # Add new snapshot
        target_data["snapshots"].append(snapshot)

        # Sort snapshots by date
        target_data["snapshots"].sort(key=lambda x: x["snapshot_date"])

        # Update evolution summary
        target_data["evolution_summary"] = self._calculate_evolution_summary(
            target_data["snapshots"]
        )

        # Save updated data
        self._save_evolution_data(evolution_data)

        logger.info(
            f"Recorded snapshot for {target_date}: "
            f"{savings_pct:.1f}% savings (confidence: {confidence}%)"
        )

    def get_evolution(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Get full evolution history for a target date.

        Args:
            target_date: Target charging date (YYYY-MM-DD)

        Returns:
            Evolution data or None if not found
        """
        evolution_data = self._load_evolution_data()
        return evolution_data["target_forecasts"].get(target_date)

    def get_latest_snapshot(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Get the most recent snapshot for a target date.

        Args:
            target_date: Target charging date (YYYY-MM-DD)

        Returns:
            Latest snapshot or None if not found
        """
        evolution = self.get_evolution(target_date)
        if evolution and evolution.get("snapshots"):
            return evolution["snapshots"][-1]
        return None

    def get_all_tracked_dates(self) -> List[str]:
        """Get list of all tracked target dates.

        Returns:
            List of target dates being tracked
        """
        evolution_data = self._load_evolution_data()
        return list(evolution_data["target_forecasts"].keys())

    def detect_significant_change(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Check if latest snapshot differs significantly from previous.

        Args:
            target_date: Target charging date (YYYY-MM-DD)

        Returns:
            Change details if significant, None otherwise
        """
        evolution = self.get_evolution(target_date)
        if not evolution or len(evolution.get("snapshots", [])) < 2:
            return None

        snapshots = evolution["snapshots"]
        latest = snapshots[-1]
        previous = snapshots[-2]

        current_savings = latest["predicted_savings_pct"]
        previous_savings = previous["predicted_savings_pct"]
        drift = current_savings - previous_savings

        if abs(drift) >= self.SIGNIFICANT_CHANGE_THRESHOLD:
            return {
                "target_date": target_date,
                "previous_savings_pct": previous_savings,
                "current_savings_pct": current_savings,
                "savings_drift": drift,
                "drift_direction": "improved" if drift > 0 else "worsened",
                "previous_snapshot_date": previous["snapshot_date"],
                "current_snapshot_date": latest["snapshot_date"],
                "confidence_score": latest["confidence_score"],
                "price_source": latest["price_source"],
            }

        return None

    def get_forecasts_with_drift(self, min_drift: float = 10.0) -> List[Dict[str, Any]]:
        """Get all forecasts with significant drift.

        Args:
            min_drift: Minimum drift percentage to include

        Returns:
            List of forecasts with significant changes
        """
        evolution_data = self._load_evolution_data()
        drifted = []

        for target_date, data in evolution_data["target_forecasts"].items():
            summary = data.get("evolution_summary")
            if summary and abs(summary.get("savings_drift", 0)) >= min_drift:
                drifted.append(
                    {
                        "target_date": target_date,
                        "initial_savings_pct": summary["initial_savings_pct"],
                        "current_savings_pct": summary["current_savings_pct"],
                        "savings_drift": summary["savings_drift"],
                        "num_snapshots": len(data.get("snapshots", [])),
                    }
                )

        return sorted(drifted, key=lambda x: abs(x["savings_drift"]), reverse=True)

    def record_actual_result(
        self, target_date: str, actual_cost: float, actual_avg_price: float
    ) -> None:
        """Record actual charging result for accuracy tracking.

        Args:
            target_date: Target charging date (YYYY-MM-DD)
            actual_cost: Actual cost incurred
            actual_avg_price: Actual average price paid
        """
        evolution_data = self._load_evolution_data()

        if target_date not in evolution_data["target_forecasts"]:
            logger.warning(f"No forecast evolution data for {target_date}")
            return

        evolution_data["target_forecasts"][target_date]["actual_result"] = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "actual_cost": actual_cost,
            "actual_avg_price": actual_avg_price,
        }

        self._save_evolution_data(evolution_data)
        logger.info(f"Recorded actual result for {target_date}")

    def cleanup_old_data(self) -> int:
        """Remove evolution data older than retention period.

        Returns:
            Number of entries removed
        """
        evolution_data = self._load_evolution_data()
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=self.RETENTION_DAYS)

        original_count = len(evolution_data["target_forecasts"])

        # Remove old entries
        evolution_data["target_forecasts"] = {
            target_date: data
            for target_date, data in evolution_data["target_forecasts"].items()
            if datetime.strptime(target_date, "%Y-%m-%d").date() >= cutoff
        }

        removed = original_count - len(evolution_data["target_forecasts"])

        if removed > 0:
            evolution_data["metadata"]["last_cleanup"] = datetime.now(
                timezone.utc
            ).isoformat()
            self._save_evolution_data(evolution_data)
            logger.info(f"Cleaned up {removed} old forecast evolution entries")

        return removed

    def _calculate_confidence(
        self, days_until_target: int, price_source: str, historical_mae: Optional[float]
    ) -> int:
        """Calculate confidence score (0-100) for a forecast.

        Args:
            days_until_target: Days until the target charging date
            price_source: Source of price data ("octopus_actual" or "forecast")
            historical_mae: Historical mean absolute error (p/kWh)

        Returns:
            Confidence score from 0 to 100
        """
        # Time horizon factor (40% weight): closer = more confident
        if days_until_target <= 1:
            time_score = 100
        elif days_until_target == 2:
            time_score = 85
        elif days_until_target <= 4:
            time_score = 60
        else:
            time_score = max(30, 100 - (days_until_target * 10))

        # Data source factor (35% weight): actual prices = high confidence
        source_score = 100 if price_source == "octopus_actual" else 50

        # Historical accuracy factor (25% weight): lower MAE = higher confidence
        if historical_mae is None or historical_mae > 5:
            accuracy_score = 40
        elif historical_mae < 2:
            accuracy_score = 100
        else:
            accuracy_score = max(40, 100 - (historical_mae * 12))

        return int(0.40 * time_score + 0.35 * source_score + 0.25 * accuracy_score)

    def _calculate_evolution_summary(
        self, snapshots: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Calculate evolution summary from snapshots.

        Args:
            snapshots: List of forecast snapshots

        Returns:
            Summary dictionary or None if insufficient data
        """
        if not snapshots:
            return None

        initial = snapshots[0]
        current = snapshots[-1]

        initial_savings = initial["predicted_savings_pct"]
        current_savings = current["predicted_savings_pct"]
        drift = current_savings - initial_savings

        # Calculate price volatility (std dev of predicted costs)
        costs = [s["predicted_cost"] for s in snapshots]
        if len(costs) > 1:
            mean_cost = sum(costs) / len(costs)
            variance = sum((c - mean_cost) ** 2 for c in costs) / len(costs)
            volatility = variance**0.5
        else:
            volatility = 0.0

        return {
            "initial_savings_pct": initial_savings,
            "current_savings_pct": current_savings,
            "savings_drift": round(drift, 2),
            "savings_drift_direction": (
                "improved" if drift > 0 else "worsened" if drift < 0 else "unchanged"
            ),
            "price_volatility": round(volatility, 2),
            "num_snapshots": len(snapshots),
            "first_snapshot": initial["snapshot_date"],
            "last_updated": current["snapshot_timestamp"],
        }

    def _load_evolution_data(self) -> Dict[str, Any]:
        """Load evolution data from file.

        Returns:
            Evolution data dictionary
        """
        if not self.EVOLUTION_FILE.exists():
            return {
                "target_forecasts": {},
                "metadata": {
                    "version": "1.0",
                    "retention_days": self.RETENTION_DAYS,
                    "last_cleanup": None,
                },
            }

        try:
            with open(self.EVOLUTION_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading evolution data: {e}")
            return {
                "target_forecasts": {},
                "metadata": {
                    "version": "1.0",
                    "retention_days": self.RETENTION_DAYS,
                    "last_cleanup": None,
                },
            }

    def _save_evolution_data(self, data: Dict[str, Any]) -> None:
        """Save evolution data to file with atomic write.

        Args:
            data: Evolution data to save
        """
        temp_path = self.EVOLUTION_FILE.with_suffix(".json.tmp")

        try:
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            temp_path.replace(self.EVOLUTION_FILE)
            logger.debug(f"Saved evolution data to {self.EVOLUTION_FILE}")

        except IOError as e:
            logger.error(f"Failed to save evolution data: {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise


def format_evolution_alert(change: Dict[str, Any]) -> tuple:
    """Format forecast change notification for Pushover.

    Args:
        change: Change details from detect_significant_change()

    Returns:
        Tuple of (title, message, priority, sound)
    """
    target_date = change["target_date"]
    old_savings = change["previous_savings_pct"]
    new_savings = change["current_savings_pct"]
    drift = change["savings_drift"]
    confidence = change["confidence_score"]

    # Parse target date for display
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    display_date = target_dt.strftime("%b %d")

    if drift > 0:
        direction = "improved"
        priority = 0  # Normal - good news
        sound = "cosmic"
    else:
        direction = "worsened"
        priority = 1  # High - user may want to reconsider
        sound = "falling"

    title = f"Forecast Update: {display_date} savings {direction}"

    message = f"<b>Target Date:</b> {display_date}\n"
    message += f"<b>Original Forecast:</b> {old_savings:.0f}% savings\n"
    message += f"<b>Updated Forecast:</b> {new_savings:.0f}% savings\n"
    message += f"<b>Change:</b> {drift:+.1f}%\n\n"

    if drift < -10:
        message += "<b>Consider:</b> Charging earlier may be better\n"
    elif drift > 10:
        message += "<b>Consider:</b> Waiting is now more attractive\n"

    message += f"<b>Confidence:</b> {confidence}%"

    return title, message, priority, sound
