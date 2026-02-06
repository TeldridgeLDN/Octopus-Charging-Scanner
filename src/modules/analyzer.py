"""Price and Carbon Analysis Engine

Analyzes electricity pricing and carbon intensity data to identify optimal
charging windows. Implements the scoring algorithm from PRD.md.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OpportunityRating(Enum):
    """Opportunity rating classification"""

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    AVERAGE = "AVERAGE"
    POOR = "POOR"


class WindowStatus(Enum):
    """Status of charging window relative to current time"""

    UPCOMING = "upcoming"
    ACTIVE = "active"
    PASSED = "passed"


@dataclass
class PriceSlot:
    """Electricity price data for a time slot"""

    time: datetime
    price: float  # pence/kWh
    source: str  # "octopus" or "forecast"


@dataclass
class CarbonSlot:
    """Carbon intensity data for a time slot"""

    time: datetime
    intensity: int  # gCO2/kWh


@dataclass
class ChargingWindow:
    """Optimal charging window with analysis"""

    start: datetime
    end: datetime
    avg_price: float  # pence/kWh
    avg_carbon: int  # gCO2/kWh
    total_cost: float  # £
    total_carbon: int  # gCO2
    opportunity_score: float  # 0-100
    rating: OpportunityRating
    reason: str  # "cheap", "clean", "both"
    savings_vs_baseline: float  # £

    def get_status(self, current_time: Optional[datetime] = None) -> WindowStatus:
        """Get window status relative to current time.

        Args:
            current_time: Time to check against (defaults to now)

        Returns:
            WindowStatus enum value
        """
        if current_time is None:
            current_time = datetime.now(self.start.tzinfo or None)

        if current_time < self.start:
            return WindowStatus.UPCOMING
        elif current_time > self.end:
            return WindowStatus.PASSED
        else:
            return WindowStatus.ACTIVE

    def time_until_start(self, current_time: Optional[datetime] = None) -> timedelta:
        """Calculate time until window starts.

        Args:
            current_time: Time to check from (defaults to now)

        Returns:
            Time delta (negative if window already started)
        """
        if current_time is None:
            current_time = datetime.now(self.start.tzinfo or None)

        return self.start - current_time

    def time_until_end(self, current_time: Optional[datetime] = None) -> timedelta:
        """Calculate time until window ends.

        Args:
            current_time: Time to check from (defaults to now)

        Returns:
            Time delta (negative if window already ended)
        """
        if current_time is None:
            current_time = datetime.now(self.end.tzinfo or None)

        return self.end - current_time

    def has_negative_pricing(self) -> bool:
        """Check if window has negative pricing (you get PAID to charge).

        Returns:
            True if average price is negative
        """
        return self.avg_price < 0

    def get_earnings_estimate(self, kwh: float = 30.0) -> Optional[float]:
        """Calculate estimated earnings if pricing is negative.

        Args:
            kwh: Amount of energy to charge (default 30kWh)

        Returns:
            Estimated earnings in £ (positive number), or None if not negative pricing
        """
        if not self.has_negative_pricing():
            return None

        # Convert negative pence to positive pounds
        # avg_price is in pence/kWh, so multiply by kwh and divide by 100
        # Make it positive (earnings, not cost)
        return abs(self.avg_price * kwh / 100)


class Analyzer:
    """Price and carbon analysis engine.

    Analyzes electricity pricing and carbon intensity data to identify
    optimal charging opportunities based on configurable thresholds and weights.
    """

    # Default thresholds (can be overridden via config)
    DEFAULT_PRICE_EXCELLENT = 10  # pence/kWh
    DEFAULT_PRICE_GOOD = 15
    DEFAULT_PRICE_AVERAGE = 20

    DEFAULT_CARBON_EXCELLENT = 100  # gCO2/kWh
    DEFAULT_CARBON_GOOD = 150
    DEFAULT_CARBON_AVERAGE = 200

    DEFAULT_PRICE_WEIGHT = 0.6
    DEFAULT_CARBON_WEIGHT = 0.4

    def __init__(
        self,
        price_weight: float = DEFAULT_PRICE_WEIGHT,
        carbon_weight: float = DEFAULT_CARBON_WEIGHT,
        price_excellent: float = DEFAULT_PRICE_EXCELLENT,
        price_good: float = DEFAULT_PRICE_GOOD,
        price_average: float = DEFAULT_PRICE_AVERAGE,
        carbon_excellent: int = DEFAULT_CARBON_EXCELLENT,
        carbon_good: int = DEFAULT_CARBON_GOOD,
        carbon_average: int = DEFAULT_CARBON_AVERAGE,
    ):
        """Initialize analyzer with configurable thresholds and weights.

        Args:
            price_weight: Weight for price score (0-1)
            carbon_weight: Weight for carbon score (0-1)
            price_excellent: Excellent price threshold (pence/kWh)
            price_good: Good price threshold (pence/kWh)
            price_average: Average price threshold (pence/kWh)
            carbon_excellent: Excellent carbon threshold (gCO2/kWh)
            carbon_good: Good carbon threshold (gCO2/kWh)
            carbon_average: Average carbon threshold (gCO2/kWh)

        Raises:
            ValueError: If weights don't sum to 1.0
        """
        if abs(price_weight + carbon_weight - 1.0) > 0.01:
            raise ValueError(
                f"Weights must sum to 1.0, got {price_weight + carbon_weight}"
            )

        self.price_weight = price_weight
        self.carbon_weight = carbon_weight
        self.price_excellent = price_excellent
        self.price_good = price_good
        self.price_average = price_average
        self.carbon_excellent = carbon_excellent
        self.carbon_good = carbon_good
        self.carbon_average = carbon_average

        logger.info(
            f"Analyzer initialized: price_weight={price_weight}, "
            f"carbon_weight={carbon_weight}"
        )

    def calculate_price_score(self, price: float) -> float:
        """Calculate normalized score for a price value.

        Args:
            price: Price in pence/kWh

        Returns:
            Score from 0-100
        """
        if price <= self.price_excellent:
            return 100.0
        elif price <= self.price_good:
            return 75.0
        elif price <= self.price_average:
            return 50.0
        else:
            return 25.0

    def calculate_carbon_score(self, carbon: int) -> float:
        """Calculate normalized score for a carbon intensity value.

        Args:
            carbon: Carbon intensity in gCO2/kWh

        Returns:
            Score from 0-100
        """
        if carbon <= self.carbon_excellent:
            return 100.0
        elif carbon <= self.carbon_good:
            return 75.0
        elif carbon <= self.carbon_average:
            return 50.0
        else:
            return 25.0

    def calculate_opportunity_score(self, price: float, carbon: int) -> float:
        """Calculate combined opportunity score.

        Args:
            price: Price in pence/kWh
            carbon: Carbon intensity in gCO2/kWh

        Returns:
            Combined score from 0-100
        """
        price_score = self.calculate_price_score(price)
        carbon_score = self.calculate_carbon_score(carbon)

        combined = self.price_weight * price_score + self.carbon_weight * carbon_score

        logger.debug(
            f"Score calculation: price={price}p ({price_score}), "
            f"carbon={carbon}g ({carbon_score}) -> {combined}"
        )

        return combined

    def classify_opportunity(self, score: float) -> OpportunityRating:
        """Classify opportunity based on combined score.

        Args:
            score: Combined opportunity score (0-100)

        Returns:
            OpportunityRating classification
        """
        if score >= 90:
            return OpportunityRating.EXCELLENT
        elif score >= 70:
            return OpportunityRating.GOOD
        elif score >= 50:
            return OpportunityRating.AVERAGE
        else:
            return OpportunityRating.POOR

    def determine_reason(self, price: float, carbon: int) -> str:
        """Determine the reason for the recommendation.

        Args:
            price: Price in pence/kWh
            carbon: Carbon intensity in gCO2/kWh

        Returns:
            Reason string: "cheap", "clean", or "both"
        """
        is_cheap = price <= self.price_good
        is_clean = carbon <= self.carbon_good

        if is_cheap and is_clean:
            return "both"
        elif is_cheap:
            return "cheap"
        elif is_clean:
            return "clean"
        else:
            return "neither"

    def find_optimal_window(
        self,
        price_slots: List[PriceSlot],
        carbon_slots: List[CarbonSlot],
        charge_duration_hours: float,
        baseline_time: Optional[datetime] = None,
    ) -> ChargingWindow:
        """Find the optimal charging window.

        Args:
            price_slots: List of price data slots
            carbon_slots: List of carbon data slots
            charge_duration_hours: How long charging takes (e.g., 4.05 hours for 30kWh @ 7.4kW)
            baseline_time: Time for baseline cost comparison (default: 18:00 today)

        Returns:
            ChargingWindow with optimal timing and analysis

        Raises:
            ValueError: If no valid windows found or data mismatch
        """
        if not price_slots or not carbon_slots:
            raise ValueError("Price and carbon data required")

        # Align data on half-hour boundaries
        aligned_data = self._align_data(price_slots, carbon_slots)
        if not aligned_data:
            raise ValueError("No overlapping price and carbon data found")

        # Calculate number of slots needed
        slots_needed = int(charge_duration_hours * 2)  # Half-hourly slots

        # Find best consecutive window
        best_window = None
        best_score = -1.0

        for i in range(len(aligned_data) - slots_needed + 1):
            window_slots = aligned_data[i : i + slots_needed]

            avg_price = sum(s["price"] for s in window_slots) / len(window_slots)
            avg_carbon = sum(s["carbon"] for s in window_slots) / len(window_slots)
            score = self.calculate_opportunity_score(avg_price, avg_carbon)

            if score > best_score:
                best_score = score
                best_window = window_slots

        if not best_window:
            raise ValueError("No valid charging window found")

        # Calculate window metrics
        start_time = best_window[0]["time"]
        end_time = best_window[-1]["time"] + timedelta(minutes=30)
        avg_price = sum(s["price"] for s in best_window) / len(best_window)
        avg_carbon = int(sum(s["carbon"] for s in best_window) / len(best_window))

        # Calculate total cost (price is pence/kWh, need to convert to £)
        kwh_charged = charge_duration_hours * 7.4  # Assuming 7.4kW charger
        total_cost = (avg_price * kwh_charged) / 100  # Convert pence to £
        total_carbon = int(avg_carbon * kwh_charged)

        # Calculate baseline comparison
        if baseline_time:
            baseline_cost = self._calculate_baseline_cost(
                aligned_data, baseline_time, slots_needed, kwh_charged
            )
        else:
            # Default baseline: 18:00 evening charging
            baseline_cost = total_cost * 1.5  # Assume 50% more expensive

        savings = baseline_cost - total_cost

        # Determine rating and reason
        rating = self.classify_opportunity(best_score)
        reason = self.determine_reason(avg_price, avg_carbon)

        logger.info(
            f"Optimal window: {start_time} - {end_time}, "
            f"score={best_score:.1f}, rating={rating.value}"
        )

        return ChargingWindow(
            start=start_time,
            end=end_time,
            avg_price=avg_price,
            avg_carbon=avg_carbon,
            total_cost=total_cost,
            total_carbon=total_carbon,
            opportunity_score=best_score,
            rating=rating,
            reason=reason,
            savings_vs_baseline=savings,
        )

    def _align_data(
        self, price_slots: List[PriceSlot], carbon_slots: List[CarbonSlot]
    ) -> List[Dict[str, Any]]:
        """Align price and carbon data on time boundaries.

        Args:
            price_slots: List of price data
            carbon_slots: List of carbon data

        Returns:
            List of aligned slots with both price and carbon data
        """
        # Create lookup dictionary for carbon data
        carbon_lookup = {slot.time: slot.intensity for slot in carbon_slots}

        aligned = []
        for price_slot in price_slots:
            # Look for matching carbon data (exact match or within 30 minutes)
            carbon_value = carbon_lookup.get(price_slot.time)

            if carbon_value is not None:
                aligned.append(
                    {
                        "time": price_slot.time,
                        "price": price_slot.price,
                        "carbon": carbon_value,
                    }
                )

        # Sort by time to ensure chronological order
        aligned.sort(key=lambda x: x["time"])

        logger.debug(
            f"Aligned {len(aligned)} slots from {len(price_slots)} price "
            f"and {len(carbon_slots)} carbon slots"
        )

        return aligned

    def _calculate_baseline_cost(
        self,
        aligned_data: List[Dict[str, Any]],
        baseline_time: datetime,
        slots_needed: int,
        kwh_charged: float,
    ) -> float:
        """Calculate cost at baseline time for comparison.

        Args:
            aligned_data: Aligned price/carbon data
            baseline_time: Time to calculate baseline cost
            slots_needed: Number of slots for charge duration
            kwh_charged: Total kWh to charge

        Returns:
            Baseline cost in £
        """
        # Find slots starting at baseline time
        baseline_slots = []
        for i, slot in enumerate(aligned_data):
            if slot["time"] >= baseline_time:
                baseline_slots = aligned_data[i : i + slots_needed]
                break

        if not baseline_slots or len(baseline_slots) < slots_needed:
            # No baseline data, return conservative estimate
            return 5.0  # £5 for 30kWh @ ~16p/kWh

        avg_baseline_price = sum(s["price"] for s in baseline_slots) / len(
            baseline_slots
        )
        return (avg_baseline_price * kwh_charged) / 100  # Convert pence to £
