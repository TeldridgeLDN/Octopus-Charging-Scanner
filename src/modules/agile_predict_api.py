"""agile_predict API Client

Fetches Octopus Agile price forecasts from https://prices.fly.dev — a public
XGBoost ML service trained on National Grid ESO demand/wind/solar and weather
data. Provides 14-day ahead forecasts at 30-min resolution with p10/p90
confidence intervals.

GitHub: https://github.com/fboundy/agile_predict
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, date, timedelta
import logging

from .octopus_api import BaseAPIClient

logger = logging.getLogger(__name__)

# Confidence labels derived from p10/p90 band width (pence/kWh)
CONFIDENCE_HIGH = "high confidence"
CONFIDENCE_MODERATE = "moderate confidence"
CONFIDENCE_UNCERTAIN = "uncertain forecast"

# Band width thresholds for confidence classification
_BAND_HIGH = 5.0
_BAND_MODERATE = 10.0


class AgilePredict(BaseAPIClient):
    """Fetch ML-based Agile price forecasts from prices.fly.dev.

    Returns 30-min half-hourly slots for up to 14 days with confidence bands.
    No authentication required. Default region H = Southern England / London.
    """

    BASE_URL = "https://prices.fly.dev/api"

    def __init__(self, timeout: int = 15, max_retries: int = 3):
        """Initialize agile_predict client.

        Args:
            timeout: Request timeout in seconds (slightly higher than others
                     as the ML service can be slower on cold start)
            max_retries: Maximum number of retry attempts
        """
        super().__init__(timeout, max_retries)

    def get_forecasts(self, region: str = "H", days: int = 14) -> List[Dict[str, Any]]:
        """Fetch price forecasts for a region.

        Args:
            region: Octopus Agile DNO region code (default: H = London)
            days: Number of days ahead to fetch (max 14)

        Returns:
            List of forecast slots:
            [
                {
                    "date_time": "2026-03-23T00:00:00Z",  # UTC ISO 8601
                    "agile_pred": 12.5,   # predicted price (pence/kWh)
                    "agile_low": 8.2,     # p10 confidence bound (pence/kWh)
                    "agile_high": 18.7,   # p90 confidence bound (pence/kWh)
                    "source": "agile_predict"
                },
                ...
            ]

        Returns empty list on failure (graceful degradation — caller falls
        back to Guy Lipman scraper).
        """
        url = f"{self.BASE_URL}/{region}/"
        params: Dict[str, Any] = {
            "days": min(days, 14),
            "high_low": "true",
        }

        try:
            logger.info(
                f"Fetching agile_predict forecasts for region {region}, {days} days"
            )
            data = self.fetch(url, params=params)

            slots = self._parse_response(data)
            logger.info(f"Retrieved {len(slots)} agile_predict forecast slots")
            return slots

        except Exception as e:
            logger.warning(f"agile_predict fetch failed: {e}")
            return []

    def _parse_response(self, data: Any) -> List[Dict[str, Any]]:
        """Parse API response into normalised slot list.

        Args:
            data: Raw JSON response (list of forecast objects)

        Returns:
            Flat list of price slots with confidence bands
        """
        if not isinstance(data, list) or not data:
            logger.warning("agile_predict returned unexpected response shape")
            return []

        # Response is an array; take the most recent forecast (first element)
        forecast = data[0]
        prices = forecast.get("prices", [])

        if not prices:
            logger.warning("agile_predict forecast contains no prices")
            return []

        slots = []
        for entry in prices:
            date_time = entry.get("date_time")
            agile_pred = entry.get("agile_pred")

            if date_time is None or agile_pred is None:
                continue

            slots.append(
                {
                    "date_time": date_time,
                    "agile_pred": float(agile_pred),
                    "agile_low": (
                        float(entry["agile_low"])
                        if entry.get("agile_low") is not None
                        else None
                    ),
                    "agile_high": (
                        float(entry["agile_high"])
                        if entry.get("agile_high") is not None
                        else None
                    ),
                    "source": "agile_predict",
                }
            )

        return slots

    def _band_to_confidence(self, low: Any, high: Any) -> str:
        """Map p10/p90 band width to a confidence label.

        Args:
            low: p10 bound (agile_low), or None
            high: p90 bound (agile_high), or None

        Returns:
            One of CONFIDENCE_HIGH, CONFIDENCE_MODERATE, CONFIDENCE_UNCERTAIN
        """
        if low is None or high is None:
            return CONFIDENCE_UNCERTAIN
        band = high - low
        if band < _BAND_HIGH:
            return CONFIDENCE_HIGH
        if band < _BAND_MODERATE:
            return CONFIDENCE_MODERATE
        return CONFIDENCE_UNCERTAIN

    def confidence_label(self, slot: Dict[str, Any]) -> str:
        """Derive a human-readable confidence label from a forecast slot's p10/p90 band.

        Args:
            slot: A forecast slot dict from get_forecasts()

        Returns:
            One of CONFIDENCE_HIGH, CONFIDENCE_MODERATE, CONFIDENCE_UNCERTAIN
        """
        return self._band_to_confidence(slot.get("agile_low"), slot.get("agile_high"))

    def is_available(self, region: str = "H") -> bool:
        """Check if the agile_predict service is reachable.

        Args:
            region: DNO region code

        Returns:
            True if at least one slot is returned
        """
        return len(self.get_forecasts(region, days=1)) > 0

    def get_day_summary(
        self,
        region: str = "H",
        days: int = 7,
        slots: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Return one summary entry per day: min/avg/max predicted price.

        Useful for weekly summary "best days ahead" section without needing
        the full MultiDayPlanner machinery.

        Args:
            region: DNO region code
            days: Number of days to summarise
            slots: Optional pre-fetched forecast slots (from get_forecasts).
                If None, fetches fresh — pass shared slots to avoid a second
                API call when combining with get_cheapest_window.

        Returns:
            List of daily summaries ordered by date:
            [
                {
                    "date": "2026-03-23",
                    "avg_pred": 11.2,
                    "min_pred": 6.4,
                    "max_pred": 18.9,
                    "avg_low": 5.1,
                    "avg_high": 17.3,
                    "confidence": "high confidence"
                },
                ...
            ]
        """
        if slots is None:
            slots = self.get_forecasts(region, days=days)
        if not slots:
            return []

        by_date: Dict[str, List[Dict[str, Any]]] = {}
        for slot in slots:
            dt = datetime.fromisoformat(slot["date_time"].replace("Z", "+00:00"))
            date_str = dt.date().isoformat()
            by_date.setdefault(date_str, []).append(slot)

        summaries = []
        for date_str in sorted(by_date):
            day_slots = by_date[date_str]
            preds = [s["agile_pred"] for s in day_slots]
            lows = [s["agile_low"] for s in day_slots if s["agile_low"] is not None]
            highs = [s["agile_high"] for s in day_slots if s["agile_high"] is not None]

            avg_low = sum(lows) / len(lows) if lows else None
            avg_high = sum(highs) / len(highs) if highs else None
            confidence = self._band_to_confidence(avg_low, avg_high)

            summaries.append(
                {
                    "date": date_str,
                    "avg_pred": round(sum(preds) / len(preds), 1),
                    "min_pred": round(min(preds), 1),
                    "max_pred": round(max(preds), 1),
                    "avg_low": round(avg_low, 1) if avg_low is not None else None,
                    "avg_high": round(avg_high, 1) if avg_high is not None else None,
                    "confidence": confidence,
                }
            )

        return summaries

    def get_cheapest_window(
        self,
        region: str = "H",
        target_date=None,
        block_hours: float = 3.0,
        slots: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find the cheapest contiguous price block on a given forecast day.

        Slides a fixed-length window of contiguous 30-min slots across the day
        and returns the block with the lowest average predicted price. The
        default 3-hour block ("3h core") reflects a typical overnight EV top-up
        so the hint names a realistic charging window rather than a single slot.

        Args:
            region: DNO region code (used only if slots must be fetched).
            target_date: Day to search, as an ISO date string ("2026-03-23")
                or a date object. If None, no day filter is applied.
            block_hours: Length of the contiguous block in hours (default 3.0).
            slots: Optional pre-fetched forecast slots (from get_forecasts).
                If None, fetches a 7-day forecast — pass shared slots to avoid
                a second API call.

        Returns:
            {"start": datetime (UTC-aware), "end": datetime (UTC-aware),
            "avg_price": float} for the cheapest block, or None if no
            contiguous block of the required length exists on that day.
        """
        if slots is None:
            slots = self.get_forecasts(region, days=7)
        if not slots:
            return None

        target_iso: Optional[str] = None
        if target_date is not None:
            target_iso = (
                target_date.isoformat()
                if isinstance(target_date, date)
                else str(target_date)
            )

        # Parse slots to (datetime, price) and filter to the target day
        parsed = []
        for slot in slots:
            dt = datetime.fromisoformat(slot["date_time"].replace("Z", "+00:00"))
            if target_iso is not None and dt.date().isoformat() != target_iso:
                continue
            parsed.append((dt, slot["agile_pred"]))

        n = int(block_hours * 2)  # number of 30-min slots in the block
        if len(parsed) < n:
            return None

        parsed.sort(key=lambda p: p[0])

        best_avg: Optional[float] = None
        best_block = None
        half_hour = timedelta(minutes=30)

        # Slide over contiguous runs of 30-min slots only
        for i in range(len(parsed) - n + 1):
            block = parsed[i : i + n]
            contiguous = all(
                block[j + 1][0] - block[j][0] == half_hour for j in range(n - 1)
            )
            if not contiguous:
                continue
            avg = sum(price for _, price in block) / n
            if best_avg is None or avg < best_avg:
                best_avg = avg
                best_block = block

        if best_block is None:
            return None

        return {
            "start": best_block[0][0],
            "end": best_block[-1][0] + half_hour,
            "avg_price": best_avg,
        }
