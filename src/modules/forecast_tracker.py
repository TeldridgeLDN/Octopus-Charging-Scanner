"""Forecast Accuracy Tracker

Tracks Guy Lipman forecast accuracy vs Octopus actual prices.
Stores daily comparison metrics for analysis and auto-tuning.
"""

from typing import Dict, List, Any
from datetime import datetime, date, timezone
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ForecastTracker:
    """Track and analyze forecast accuracy over time.

    Compares Guy Lipman price forecasts with actual Octopus Agile prices
    to measure forecast reliability and identify systematic biases.
    """

    def __init__(self, data_dir: str = "data"):
        """Initialize forecast tracker.

        Args:
            data_dir: Directory for storing accuracy data
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.accuracy_file = self.data_dir / "forecast_accuracy.json"
        logger.info(f"Forecast tracker initialized at {data_dir}")

    def record_comparison(
        self,
        comparison_date: date,
        forecast_prices: List[float],
        actual_prices: List[float],
        forecast_source: str = "guy_lipman",
    ) -> Dict[str, Any]:
        """Record forecast vs actual price comparison.

        Args:
            comparison_date: Date being compared
            forecast_prices: Hourly forecast prices (24 values)
            actual_prices: Hourly actual prices (24 values)
            forecast_source: Source of forecast data

        Returns:
            Dictionary with accuracy metrics

        Raises:
            ValueError: If price lists are different lengths
        """
        if len(forecast_prices) != len(actual_prices):
            raise ValueError(
                f"Price lists must be same length: "
                f"forecast={len(forecast_prices)}, actual={len(actual_prices)}"
            )

        # Calculate accuracy metrics
        errors = [
            actual - forecast
            for actual, forecast in zip(actual_prices, forecast_prices)
        ]
        abs_errors = [abs(e) for e in errors]

        metrics = {
            "date": comparison_date.isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "forecast_source": forecast_source,
            "num_hours": len(forecast_prices),
            "mean_absolute_error": sum(abs_errors) / len(abs_errors),
            "mean_error": sum(errors) / len(errors),  # Systematic bias
            "max_error": max(abs_errors),
            "min_error": min(abs_errors),
            "forecast_avg": sum(forecast_prices) / len(forecast_prices),
            "actual_avg": sum(actual_prices) / len(actual_prices),
            "rmse": (sum(e**2 for e in errors) / len(errors)) ** 0.5,
            "forecast_min": min(forecast_prices),
            "actual_min": min(actual_prices),
            "forecast_max": max(forecast_prices),
            "actual_max": max(actual_prices),
            "errors": errors[:10],  # Store first 10 for debugging
        }

        # Detect negative pricing prediction accuracy
        forecast_negative = any(p < 0 for p in forecast_prices)
        actual_negative = any(p < 0 for p in actual_prices)

        metrics["negative_pricing"] = {
            "forecast_predicted": forecast_negative,
            "actually_occurred": actual_negative,
            "correct_prediction": forecast_negative == actual_negative,
        }

        # Store the comparison
        self._save_comparison(metrics)

        logger.info(
            f"Recorded forecast comparison for {comparison_date}: "
            f"MAE={metrics['mean_absolute_error']:.2f}p/kWh"
        )

        return metrics

    def get_recent_accuracy(self, days: int = 30) -> Dict[str, Any]:
        """Get accuracy statistics for recent period.

        Args:
            days: Number of recent days to analyze

        Returns:
            Dictionary with aggregated accuracy metrics
        """
        comparisons = self._load_comparisons()

        if not comparisons:
            return {
                "num_comparisons": 0,
                "mean_absolute_error": None,
                "trend": "insufficient_data",
            }

        # Filter to recent days
        recent = sorted(comparisons, key=lambda x: x["date"], reverse=True)[:days]

        if not recent:
            return {
                "num_comparisons": 0,
                "mean_absolute_error": None,
                "trend": "no_recent_data",
            }

        # Aggregate metrics
        mae_values = [c["mean_absolute_error"] for c in recent]
        bias_values = [c["mean_error"] for c in recent]

        # Calculate trend (improving/degrading)
        if len(recent) >= 7:
            recent_7 = mae_values[:7]
            older_7 = mae_values[7:14] if len(mae_values) >= 14 else mae_values[7:]

            if older_7:
                recent_avg = sum(recent_7) / len(recent_7)
                older_avg = sum(older_7) / len(older_7)

                if recent_avg < older_avg - 0.5:
                    trend = "improving"
                elif recent_avg > older_avg + 0.5:
                    trend = "degrading"
                else:
                    trend = "stable"
            else:
                trend = "insufficient_data"
        else:
            trend = "insufficient_data"

        # Count negative pricing predictions
        neg_predictions = sum(
            1
            for c in recent
            if c.get("negative_pricing", {}).get("forecast_predicted", False)
        )
        neg_correct = sum(
            1
            for c in recent
            if c.get("negative_pricing", {}).get("correct_prediction", False)
        )

        return {
            "num_comparisons": len(recent),
            "period_days": days,
            "mean_absolute_error": sum(mae_values) / len(mae_values),
            "median_absolute_error": sorted(mae_values)[len(mae_values) // 2],
            "systematic_bias": sum(bias_values) / len(bias_values),
            "best_day_mae": min(mae_values),
            "worst_day_mae": max(mae_values),
            "trend": trend,
            "negative_pricing_predictions": neg_predictions,
            "negative_pricing_correct": neg_correct,
            "negative_pricing_accuracy": (
                neg_correct / neg_predictions if neg_predictions > 0 else None
            ),
            "last_updated": recent[0]["timestamp"],
        }

    def get_reliability_grade(self, days: int = 30) -> str:
        """Get forecast reliability grade based on recent accuracy.

        Args:
            days: Number of recent days to analyze

        Returns:
            Grade: EXCELLENT, GOOD, FAIR, POOR, UNKNOWN
        """
        stats = self.get_recent_accuracy(days)

        if stats["num_comparisons"] < 3:
            return "UNKNOWN"

        mae = stats["mean_absolute_error"]

        if mae is None:
            return "UNKNOWN"
        elif mae < 2.0:
            return "EXCELLENT"
        elif mae < 3.0:
            return "GOOD"
        elif mae < 5.0:
            return "FAIR"
        else:
            return "POOR"

    def should_trust_forecast(self, days: int = 7) -> bool:
        """Determine if recent forecast accuracy is trustworthy.

        Args:
            days: Number of recent days to check

        Returns:
            True if forecast is reliable (MAE < 4p/kWh)
        """
        stats = self.get_recent_accuracy(days)

        if stats["num_comparisons"] < 3:
            return True  # Give benefit of doubt with limited data

        mae = stats["mean_absolute_error"]
        return mae is not None and mae < 4.0

    def _save_comparison(self, metrics: Dict[str, Any]) -> None:
        """Save comparison metrics to file.

        Args:
            metrics: Comparison metrics to save
        """
        comparisons = self._load_comparisons()

        # Remove any existing comparison for same date
        comparisons = [c for c in comparisons if c["date"] != metrics["date"]]

        # Add new comparison
        comparisons.append(metrics)

        # Sort by date (newest first)
        comparisons.sort(key=lambda x: x["date"], reverse=True)

        # Keep last 90 days only
        comparisons = comparisons[:90]

        # Save to file
        with open(self.accuracy_file, "w") as f:
            json.dump(comparisons, f, indent=2)

    def _load_comparisons(self) -> List[Dict[str, Any]]:
        """Load all comparison metrics from file.

        Returns:
            List of comparison metrics dictionaries
        """
        if not self.accuracy_file.exists():
            return []

        try:
            with open(self.accuracy_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading forecast comparisons: {e}")
            return []
