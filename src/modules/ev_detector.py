"""EV Charging Detection Engine

Detects EV charging sessions from electricity consumption data using
heuristic pattern matching. Part of the ACIX system.

Detection strategy:
1. Identify sustained high-power intervals (>= threshold)
2. Group consecutive intervals into sessions
3. Calculate confidence based on power consistency, duration, time of day
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class ChargingState(Enum):
    """EV charging states."""

    UNPLUGGED = "unplugged"
    PLUGGED_WAITING = "plugged_waiting"
    CHARGING = "charging"
    CHARGE_COMPLETE = "charge_complete"


@dataclass
class ChargingSession:
    """Detected EV charging session."""

    start: datetime
    end: datetime
    intervals: List[Dict[str, Any]] = field(default_factory=list)
    avg_power_kw: float = 0.0
    total_kwh: float = 0.0
    confidence: int = 0  # 0-100
    state: ChargingState = ChargingState.CHARGING

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event": "ev_charging_session",
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_hours": (self.end - self.start).total_seconds() / 3600,
            "avg_power_kw": round(self.avg_power_kw, 2),
            "total_kwh": round(self.total_kwh, 2),
            "confidence": self.confidence,
            "state": self.state.value,
            "interval_count": len(self.intervals),
        }


class EVDetector:
    """Detect EV charging sessions from consumption data.

    Uses configurable thresholds to identify sustained high-power periods
    that indicate EV charging.
    """

    def __init__(
        self,
        power_threshold_kw: float = 2.3,
        min_intervals: int = 2,
        baseline_power_kw: float = 0.5,
    ):
        """Initialize detector.

        Args:
            power_threshold_kw: Minimum power to consider as EV charging
            min_intervals: Minimum consecutive intervals to form a session
            baseline_power_kw: Expected household baseline (subtracted from readings)
        """
        self.power_threshold_kw = power_threshold_kw
        self.min_intervals = min_intervals
        self.baseline_power_kw = baseline_power_kw

        logger.info(
            f"EVDetector initialized: threshold={power_threshold_kw}kW, "
            f"min_intervals={min_intervals}, baseline={baseline_power_kw}kW"
        )

    def detect_sessions(
        self, usage_data: List[Dict[str, Any]]
    ) -> List[ChargingSession]:
        """Detect EV charging sessions from usage data.

        Args:
            usage_data: List of consumption records with interval_start,
                       interval_end, power_kw, consumption_kwh

        Returns:
            List of detected ChargingSession objects
        """
        if not usage_data:
            return []

        # Sort by interval start time
        sorted_data = sorted(usage_data, key=lambda x: x["interval_start"])

        sessions = []
        current_session_intervals = []

        for record in sorted_data:
            power = record.get("power_kw", 0)

            # Check if this interval indicates EV charging
            # We look for power above threshold (charger + baseline)
            effective_threshold = self.power_threshold_kw + self.baseline_power_kw

            if power >= effective_threshold:
                current_session_intervals.append(record)
            else:
                # Gap in charging - check if we have a valid session
                if len(current_session_intervals) >= self.min_intervals:
                    session = self._create_session(current_session_intervals)
                    sessions.append(session)
                current_session_intervals = []

        # Don't forget trailing session
        if len(current_session_intervals) >= self.min_intervals:
            session = self._create_session(current_session_intervals)
            sessions.append(session)

        logger.info(f"Detected {len(sessions)} charging sessions")
        return sessions

    def _create_session(self, intervals: List[Dict[str, Any]]) -> ChargingSession:
        """Create a ChargingSession from a list of intervals.

        Args:
            intervals: List of consecutive charging intervals

        Returns:
            ChargingSession object
        """
        # Parse timestamps
        start = datetime.fromisoformat(
            intervals[0]["interval_start"].replace("Z", "+00:00")
        )
        end = datetime.fromisoformat(
            intervals[-1]["interval_end"].replace("Z", "+00:00")
        )

        # Calculate totals
        total_kwh = sum(r.get("consumption_kwh", 0) for r in intervals)
        powers = [r.get("power_kw", 0) for r in intervals]
        avg_power = sum(powers) / len(powers) if powers else 0

        # Calculate confidence score
        confidence = self._calculate_confidence(intervals, start, end, avg_power)

        session = ChargingSession(
            start=start,
            end=end,
            intervals=intervals,
            avg_power_kw=avg_power,
            total_kwh=total_kwh,
            confidence=confidence,
            state=ChargingState.CHARGE_COMPLETE,
        )

        logger.debug(
            f"Created session: {start} to {end}, "
            f"{total_kwh:.1f}kWh, confidence={confidence}"
        )

        return session

    def _calculate_confidence(
        self,
        intervals: List[Dict[str, Any]],
        start: datetime,
        end: datetime,
        avg_power: float,
    ) -> int:
        """Calculate confidence score for a detected session.

        Factors:
        - Power consistency (low variance = higher confidence)
        - Duration (longer = higher confidence, up to a point)
        - Time of day (evening/night = higher confidence)
        - Power level match to expected charger rate

        Args:
            intervals: Session intervals
            start: Session start time
            end: Session end time
            avg_power: Average power during session

        Returns:
            Confidence score 0-100
        """
        score = 0

        # Factor 1: Duration (max 25 points)
        # 1 hour = 10 points, 2+ hours = 25 points
        duration_hours = (end - start).total_seconds() / 3600
        duration_score = min(25, int(duration_hours * 12.5))
        score += duration_score

        # Factor 2: Power consistency (max 25 points)
        # Low variance in power readings indicates consistent load (EV charger)
        powers = [r.get("power_kw", 0) for r in intervals]
        if len(powers) > 1:
            mean_power = sum(powers) / len(powers)
            variance = sum((p - mean_power) ** 2 for p in powers) / len(powers)
            std_dev = variance**0.5
            # Coefficient of variation (lower = more consistent)
            cv = std_dev / mean_power if mean_power > 0 else 1
            # CV < 0.1 = very consistent = 25 points
            # CV > 0.5 = inconsistent = 0 points
            consistency_score = max(0, min(25, int(25 * (1 - cv * 2))))
            score += consistency_score
        else:
            score += 10  # Single interval, moderate confidence

        # Factor 3: Time of day (max 25 points)
        # Evening (17:00-23:00) and overnight (23:00-07:00) = high confidence
        # Daytime = lower confidence (could be other appliances)
        start_hour = start.hour
        if 17 <= start_hour <= 23 or start_hour < 7:
            score += 25  # Typical home charging time
        elif 7 <= start_hour < 10 or 15 <= start_hour < 17:
            score += 15  # Possible charging time
        else:
            score += 5  # Unusual time for home EV charging

        # Factor 4: Power level match (max 25 points)
        # Check if average power matches expected charger rate
        expected_power = self.power_threshold_kw + self.baseline_power_kw
        power_diff = abs(avg_power - expected_power)
        # Within 0.5 kW = 25 points, within 1 kW = 15 points, etc.
        if power_diff <= 0.5:
            score += 25
        elif power_diff <= 1.0:
            score += 15
        elif power_diff <= 1.5:
            score += 10
        else:
            score += 5

        return min(100, score)

    def get_session_summary(self, sessions: List[ChargingSession]) -> Dict[str, Any]:
        """Generate summary statistics for detected sessions.

        Args:
            sessions: List of detected sessions

        Returns:
            Summary dictionary with statistics
        """
        if not sessions:
            return {
                "total_sessions": 0,
                "total_kwh": 0,
                "avg_session_kwh": 0,
                "avg_confidence": 0,
            }

        total_kwh = sum(s.total_kwh for s in sessions)
        avg_kwh = total_kwh / len(sessions)
        avg_confidence = sum(s.confidence for s in sessions) / len(sessions)

        return {
            "total_sessions": len(sessions),
            "total_kwh": round(total_kwh, 2),
            "avg_session_kwh": round(avg_kwh, 2),
            "avg_confidence": round(avg_confidence, 1),
            "sessions": [s.to_dict() for s in sessions],
        }
