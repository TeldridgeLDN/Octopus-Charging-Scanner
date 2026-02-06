"""Smart Threshold Auto-Tuner

Automatically adjusts price and carbon thresholds based on historical data.
Uses rolling percentiles to keep thresholds relevant to current market conditions.
"""

from typing import Dict, List, Any, Tuple
from datetime import datetime, timezone, timedelta
import logging
from pathlib import Path
import json
import statistics

logger = logging.getLogger(__name__)


class ThresholdTuner:
    """Auto-tune price and carbon thresholds based on historical data.

    Analyzes rolling window of historical prices to calculate optimal
    thresholds that adapt to changing market conditions.
    """

    def __init__(self, data_dir: str = "data"):
        """Initialize threshold tuner.

        Args:
            data_dir: Directory for storing tuning data
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.tuning_file = self.data_dir / "threshold_tuning.json"
        logger.info(f"Threshold tuner initialized at {data_dir}")

    def calculate_optimal_thresholds(
        self, historical_prices: List[float], days_analyzed: int = 30
    ) -> Tuple[float, float]:
        """Calculate optimal price thresholds from historical data.

        Args:
            historical_prices: List of minimum daily prices
            days_analyzed: Number of days in the dataset

        Returns:
            Tuple of (excellent_threshold, good_threshold)
        """
        if len(historical_prices) < 7:
            logger.warning("Insufficient data for threshold tuning")
            return (10.0, 15.0)  # Return defaults

        # Calculate percentiles
        # Excellent = 25th percentile (better than 75% of days)
        # Good = 50th percentile (median)
        excellent = statistics.quantiles(historical_prices, n=4)[0]  # 25th percentile
        good = statistics.median(historical_prices)  # 50th percentile

        logger.info(
            f"Calculated thresholds from {len(historical_prices)} days: "
            f"excellent={excellent:.2f}p, good={good:.2f}p"
        )

        return (round(excellent, 1), round(good, 1))

    def get_recommended_thresholds(
        self, recommendations_file: Path, days: int = 30
    ) -> Dict[str, Any]:
        """Get recommended thresholds based on recent recommendations.

        Args:
            recommendations_file: Path to daily_recommendations.json
            days: Number of recent days to analyze

        Returns:
            Dictionary with threshold recommendations
        """
        if not recommendations_file.exists():
            logger.warning(f"Recommendations file not found: {recommendations_file}")
            return self._default_thresholds()

        try:
            with open(recommendations_file, "r") as f:
                recommendations = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading recommendations: {e}")
            return self._default_thresholds()

        if not recommendations:
            return self._default_thresholds()

        # Filter to recent days
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        recent = [
            r
            for r in recommendations
            if datetime.fromisoformat(r["timestamp"]).date() >= cutoff_date
        ]

        if len(recent) < 7:
            logger.warning(
                f"Only {len(recent)} recent recommendations - using defaults"
            )
            return self._default_thresholds()

        # Extract minimum prices from each day's optimal window
        min_prices = []
        avg_prices = []
        for rec in recent:
            if "avg_price" in rec:
                avg_prices.append(rec["avg_price"])

            # Use the average price of the recommended window as proxy for "good price"
            # This represents what the system considered optimal
            if "avg_price" in rec:
                min_prices.append(rec["avg_price"])

        if not min_prices:
            return self._default_thresholds()

        # Calculate new thresholds
        excellent, good = self.calculate_optimal_thresholds(min_prices, len(recent))

        # Calculate carbon thresholds similarly if available
        carbon_values = [r.get("avg_carbon", 150) for r in recent if "avg_carbon" in r]

        if len(carbon_values) >= 7:
            carbon_excellent = round(
                statistics.quantiles(carbon_values, n=4)[0], 0
            )  # 25th percentile
            carbon_good = round(statistics.median(carbon_values), 0)
        else:
            carbon_excellent = 100
            carbon_good = 150

        result = {
            "price_excellent": excellent,
            "price_good": good,
            "carbon_excellent": carbon_excellent,
            "carbon_good": carbon_good,
            "days_analyzed": len(recent),
            "price_range": {
                "min": min(min_prices),
                "max": max(min_prices),
                "mean": statistics.mean(min_prices),
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        # Save tuning record
        self._save_tuning_record(result)

        return result

    def should_update_thresholds(self, current_thresholds: Dict[str, float]) -> bool:
        """Check if thresholds need updating.

        Args:
            current_thresholds: Current threshold values

        Returns:
            True if thresholds are more than 2p different from recommended
        """
        recommended = self.get_recommended_thresholds(
            Path("data/daily_recommendations.json")
        )

        price_diff_excellent = abs(
            current_thresholds.get("price_excellent", 10)
            - recommended["price_excellent"]
        )
        price_diff_good = abs(
            current_thresholds.get("price_good", 15) - recommended["price_good"]
        )

        # Update if difference is > 2p for either threshold
        return price_diff_excellent > 2.0 or price_diff_good > 2.0

    def get_tuning_history(self, days: int = 90) -> List[Dict[str, Any]]:
        """Get historical threshold tuning records.

        Args:
            days: Number of days to retrieve

        Returns:
            List of tuning records
        """
        if not self.tuning_file.exists():
            return []

        try:
            with open(self.tuning_file, "r") as f:
                records = json.load(f)

            # Filter to requested period
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            recent = [r for r in records if r["last_updated"] >= cutoff]

            return sorted(recent, key=lambda x: x["last_updated"], reverse=True)

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading tuning history: {e}")
            return []

    def _default_thresholds(self) -> Dict[str, Any]:
        """Return default threshold values.

        Returns:
            Dictionary with default thresholds
        """
        return {
            "price_excellent": 10.0,
            "price_good": 15.0,
            "carbon_excellent": 100,
            "carbon_good": 150,
            "days_analyzed": 0,
            "price_range": {"min": 0, "max": 0, "mean": 0},
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "using_defaults": True,
        }

    def _save_tuning_record(self, record: Dict[str, Any]) -> None:
        """Save threshold tuning record.

        Args:
            record: Tuning record to save
        """
        records = []

        if self.tuning_file.exists():
            try:
                with open(self.tuning_file, "r") as f:
                    records = json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("Could not load existing tuning records")

        # Add new record
        records.append(record)

        # Keep last 90 days only
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        records = [r for r in records if r["last_updated"] >= cutoff]

        # Save
        with open(self.tuning_file, "w") as f:
            json.dump(records, f, indent=2)

        logger.info(f"Saved threshold tuning record: {len(records)} total records")
