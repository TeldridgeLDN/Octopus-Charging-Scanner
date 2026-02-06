"""Octopus Energy Agile API Client

Fetches half-hourly electricity pricing data from Octopus Energy's Agile tariff API.
Implements the UFC (Unified Fetch Client) pattern with retry logic.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
import requests
import time
import logging

logger = logging.getLogger(__name__)


class BaseAPIClient:
    """Base class for all API clients (UFC pattern)"""

    def __init__(self, timeout: int = 10, max_retries: int = 3):
        """Initialize base API client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries

    def fetch(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Unified fetch with exponential backoff retry logic.

        Args:
            url: API endpoint URL
            params: Optional query parameters

        Returns:
            JSON response as dictionary

        Raises:
            requests.exceptions.RequestException: On final retry failure
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Fetching {url} (attempt {attempt + 1}/{self.max_retries})"
                )
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt == self.max_retries - 1:
                    logger.error(f"API timeout after {self.max_retries} attempts")
                    raise
                time.sleep(5 * (2**attempt))
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else "Unknown"
                logger.error(f"HTTP error: {status}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(5 * (2**attempt))
            except requests.exceptions.RequestException as e:
                logger.error(f"Request exception: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(5 * (2**attempt))

        # This should never be reached due to raises above, but satisfies mypy
        raise requests.exceptions.RequestException("All retry attempts failed")


class OctopusAPIClient(BaseAPIClient):
    """Fetch Octopus Agile electricity prices.

    Retrieves half-hourly pricing data for the next 24 hours from Octopus Energy's
    public API. No authentication required.
    """

    BASE_URL = "https://api.octopus.energy/v1/products"
    PRODUCT_CODE = "AGILE-24-10-01"
    TARIFF_CODE = "E-1R-AGILE-24-10-01"

    def __init__(self, timeout: int = 10, max_retries: int = 3):
        """Initialize Octopus API client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        super().__init__(timeout, max_retries)

    def get_prices(self, region: str = "H", hours: int = 24) -> List[Dict[str, Any]]:
        """Fetch electricity prices for the next N hours.

        Args:
            region: DNO region code (default: H for Southern England)
            hours: Number of hours to fetch (default: 24)

        Returns:
            List of price slots with structure:
            [
                {
                    "valid_from": "2025-12-07T00:00:00Z",
                    "valid_to": "2025-12-07T00:30:00Z",
                    "value_inc_vat": 12.5
                },
                ...
            ]

        Raises:
            requests.exceptions.RequestException: On API failure
        """
        url = (
            f"{self.BASE_URL}/{self.PRODUCT_CODE}/"
            f"electricity-tariffs/{self.TARIFF_CODE}-{region}/"
            f"standard-unit-rates/"
        )

        # Calculate time window for API request
        period_from = datetime.now(timezone.utc)
        period_to = period_from + timedelta(hours=hours)

        params = {
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
        }

        logger.info(f"Fetching Octopus prices for region {region}, {hours} hours")
        data = self.fetch(url, params=params)

        results = data.get("results", [])
        logger.info(f"Retrieved {len(results)} price slots")

        return results

    def get_current_price(self, region: str = "H") -> Optional[Dict[str, Any]]:
        """Get the current electricity price.

        Args:
            region: DNO region code (default: H for Southern England)

        Returns:
            Current price slot or None if not found
        """
        prices = self.get_prices(region=region, hours=1)

        if not prices:
            logger.warning("No current price available")
            return None

        now = datetime.now(timezone.utc)

        for slot in prices:
            valid_from = datetime.fromisoformat(
                slot["valid_from"].replace("Z", "+00:00")
            )
            valid_to = datetime.fromisoformat(slot["valid_to"].replace("Z", "+00:00"))

            if valid_from <= now < valid_to:
                logger.info(f"Current price: {slot['value_inc_vat']}p/kWh")
                return slot

        logger.warning("No matching time slot found for current time")
        return None
