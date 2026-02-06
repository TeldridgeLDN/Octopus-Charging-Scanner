"""Carbon Intensity API Client

Fetches carbon intensity forecasts from the UK National Grid Carbon Intensity API.
Provides 48-hour regional carbon intensity data based on postcode.
"""

from typing import Dict, List, Any
import logging
from .octopus_api import BaseAPIClient

logger = logging.getLogger(__name__)


class CarbonAPIClient(BaseAPIClient):
    """Fetch UK carbon intensity forecasts.

    Retrieves 48-hour carbon intensity forecasts for a specific postcode region
    from the National Grid Carbon Intensity API. No authentication required.
    """

    BASE_URL = "https://api.carbonintensity.org.uk"

    def __init__(self, timeout: int = 10, max_retries: int = 3):
        """Initialize Carbon Intensity API client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        super().__init__(timeout, max_retries)

    def get_intensity(
        self, postcode: str = "E1", region_id: int = None
    ) -> List[Dict[str, Any]]:
        """Fetch 48-hour carbon intensity forecast for a region.

        Args:
            postcode: UK postcode or postcode area (deprecated, use region_id)
            region_id: UK DNO region ID (13 = London, see API docs for others)

        Returns:
            List of intensity slots with structure:
            [
                {
                    "time": "2025-12-07T00:00:00Z",
                    "intensity": 250
                },
                ...
            ]

        Raises:
            requests.exceptions.RequestException: On API failure
        """
        # Regional endpoints now require authentication, use national forecast
        # Note: region_id parameter kept for backwards compatibility but not used
        if region_id:
            logger.info(
                f"Region ID {region_id} noted (using national forecast - regional API deprecated)"
            )
        else:
            logger.info("Using national carbon intensity forecast")

        url = f"{self.BASE_URL}/intensity/date"

        try:
            data = self.fetch(url)
        except Exception as e:
            logger.error(f"Failed to fetch carbon intensity: {e}")
            return []

        # National endpoint: data[]
        regional_data = data.get("data", [])

        if not regional_data:
            logger.warning("No carbon intensity data available")
            return []

        results = []
        for entry in regional_data:
            from_time = entry.get("from")
            intensity_data = entry.get("intensity", {})
            forecast = intensity_data.get("forecast")

            if from_time and forecast is not None:
                results.append({"time": from_time, "intensity": forecast})

        logger.info(f"Retrieved {len(results)} carbon intensity slots")
        return results

    def get_current_intensity(self, postcode: str = "E1") -> Dict[str, Any]:
        """Get current carbon intensity for a postcode.

        Args:
            postcode: UK postcode or postcode area (default: E1)

        Returns:
            Current intensity data with structure:
            {
                "time": "2025-12-07T00:00:00Z",
                "intensity": 250,
                "index": "moderate"
            }

        Raises:
            requests.exceptions.RequestException: On API failure
        """
        url = f"{self.BASE_URL}/regional/postcode/{postcode}"

        logger.info(f"Fetching current carbon intensity for postcode {postcode}")
        data = self.fetch(url)

        regional_data = data.get("data", [])
        if not regional_data:
            logger.error(f"No current intensity data for postcode {postcode}")
            raise ValueError(f"No data available for postcode {postcode}")

        entry = regional_data[0]
        intensity_data = entry.get("data", [{}])[0].get("intensity", {})

        result = {
            "time": entry.get("from"),
            "intensity": intensity_data.get("forecast"),
            "index": intensity_data.get("index"),
        }

        logger.info(
            f"Current intensity: {result['intensity']} gCO2/kWh ({result['index']})"
        )
        return result

    def get_cleanest_window(
        self, postcode: str = "E1", hours: int = 4
    ) -> Dict[str, Any]:
        """Find the cleanest N-hour charging window in the next 48 hours.

        Args:
            postcode: UK postcode or postcode area (default: E1)
            hours: Duration of charging window in hours (default: 4)

        Returns:
            Dictionary with cleanest window details:
            {
                "start_time": "2025-12-07T03:00:00Z",
                "end_time": "2025-12-07T07:00:00Z",
                "average_intensity": 180,
                "total_slots": 8
            }

        Raises:
            requests.exceptions.RequestException: On API failure
            ValueError: If not enough data available
        """
        intensities = self.get_intensity(postcode)

        if len(intensities) < hours * 2:  # Half-hourly slots
            raise ValueError(
                f"Insufficient data: need {hours * 2} slots, got {len(intensities)}"
            )

        slots_needed = hours * 2
        best_window: Dict[str, Any] = {}
        best_avg = float("inf")

        # Sliding window to find cleanest period
        for i in range(len(intensities) - slots_needed + 1):
            window = intensities[i : i + slots_needed]
            avg_intensity = sum(slot["intensity"] for slot in window) / len(window)

            if avg_intensity < best_avg:
                best_avg = avg_intensity
                best_window = {
                    "start_time": window[0]["time"],
                    "end_time": window[-1]["time"],
                    "average_intensity": round(avg_intensity),
                    "total_slots": len(window),
                }

        if not best_window:
            raise ValueError("No valid window found")

        logger.info(
            f"Cleanest {hours}h window: {best_window['start_time']} "
            f"({best_window['average_intensity']} gCO2/kWh average)"
        )

        return best_window
