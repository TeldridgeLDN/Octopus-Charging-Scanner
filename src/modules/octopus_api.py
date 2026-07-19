"""Octopus Energy Agile API Client

Fetches half-hourly electricity pricing and consumption data from Octopus Energy API.
Implements the UFC (Unified Fetch Client) pattern with retry logic.

Supports:
- Public pricing API (no auth required)
- Authenticated consumption API (requires API key, MPAN, meter serial)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
from base64 import b64encode
import os
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


class OctopusConsumptionClient(BaseAPIClient):
    """Fetch electricity consumption data from Octopus Energy.

    Retrieves half-hourly consumption data using authenticated API.
    Requires API key, MPAN, and meter serial number.

    Environment variables:
        OCTOPUS_API_KEY: Your Octopus Energy API key
        OCTOPUS_ELECTRICITY_MPAN: Your electricity meter MPAN
        OCTOPUS_ELECTRICITY_ACC: Your electricity meter serial number
    """

    BASE_URL = "https://api.octopus.energy/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        mpan: Optional[str] = None,
        meter_serial: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """Initialize consumption API client.

        Args:
            api_key: Octopus API key (or from OCTOPUS_API_KEY env var)
            mpan: Electricity MPAN (or from OCTOPUS_ELECTRICITY_MPAN env var)
            meter_serial: Meter serial (or from OCTOPUS_ELECTRICITY_ACC env var)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        super().__init__(timeout, max_retries)

        self.api_key = api_key or os.environ.get("OCTOPUS_API_KEY")
        self.mpan = mpan or os.environ.get("OCTOPUS_ELECTRICITY_MPAN")
        self.meter_serial = meter_serial or os.environ.get("OCTOPUS_ELECTRICITY_ACC")

        if not all([self.api_key, self.mpan, self.meter_serial]):
            missing = []
            if not self.api_key:
                missing.append("OCTOPUS_API_KEY")
            if not self.mpan:
                missing.append("OCTOPUS_ELECTRICITY_MPAN")
            if not self.meter_serial:
                missing.append("OCTOPUS_ELECTRICITY_ACC")
            raise ValueError(f"Missing required credentials: {', '.join(missing)}")

        logger.info(f"Consumption client initialized for MPAN {self.mpan}")

    def _get_auth_header(self) -> Dict[str, str]:
        """Generate Basic auth header for API requests.

        Returns:
            Authorization header dict
        """
        credentials = f"{self.api_key}:"
        encoded = b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def fetch_authenticated(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fetch with authentication and retry logic.

        Args:
            url: API endpoint URL
            params: Optional query parameters

        Returns:
            JSON response as dictionary

        Raises:
            requests.exceptions.RequestException: On API failure
        """
        headers = self._get_auth_header()

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Fetching {url} (attempt {attempt + 1}/{self.max_retries})"
                )
                response = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(5 * (2**attempt))
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else "Unknown"
                logger.error(f"HTTP error: {status}")
                if status == 401:
                    raise ValueError("Invalid API key - check OCTOPUS_API_KEY")
                if status == 404:
                    raise ValueError(f"MPAN or meter serial not found: {self.mpan}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(5 * (2**attempt))
            except requests.exceptions.RequestException as e:
                logger.error(f"Request exception: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(5 * (2**attempt))

        raise requests.exceptions.RequestException("All retry attempts failed")

    def get_consumption(
        self,
        period_from: Optional[datetime] = None,
        period_to: Optional[datetime] = None,
        page_size: int = 200,
    ) -> List[Dict[str, Any]]:
        """Fetch electricity consumption data.

        Args:
            period_from: Start of period (default: 48 hours ago)
            period_to: End of period (default: now)
            page_size: Results per page (max 25000)

        Returns:
            List of consumption records with structure:
            [
                {
                    "interval_start": "2026-02-15T00:00:00Z",
                    "interval_end": "2026-02-15T00:30:00Z",
                    "consumption": 0.523
                },
                ...
            ]

        Raises:
            ValueError: If credentials are invalid
            requests.exceptions.RequestException: On API failure
        """
        if period_to is None:
            period_to = datetime.now(timezone.utc)
        if period_from is None:
            period_from = period_to - timedelta(hours=48)

        url = (
            f"{self.BASE_URL}/electricity-meter-points/{self.mpan}/"
            f"meters/{self.meter_serial}/consumption/"
        )

        params = {
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
            "page_size": page_size,
            "order_by": "period",
        }

        logger.info(
            f"Fetching consumption from {period_from.isoformat()} "
            f"to {period_to.isoformat()}"
        )

        all_results = []
        next_url = url

        while next_url:
            data = self.fetch_authenticated(
                next_url, params if next_url == url else None
            )
            results = data.get("results", [])
            all_results.extend(results)

            next_url = data.get("next")
            if next_url:
                logger.debug(f"Fetching next page: {next_url}")

        logger.info(f"Retrieved {len(all_results)} consumption records")

        # Convert to consistent format with power calculation
        processed = []
        for record in all_results:
            interval_start = record.get("interval_start")
            interval_end = record.get("interval_end")
            consumption_kwh = record.get("consumption", 0)

            # Calculate power in kW (consumption over 30-min interval)
            power_kw = consumption_kwh * 2  # kWh in 30 min = kW average

            processed.append(
                {
                    "interval_start": interval_start,
                    "interval_end": interval_end,
                    "consumption_kwh": consumption_kwh,
                    "power_kw": round(power_kw, 3),
                }
            )

        return processed

    def get_consumption_for_date(self, date: datetime) -> List[Dict[str, Any]]:
        """Get consumption for a specific date.

        Args:
            date: The date to fetch consumption for

        Returns:
            List of consumption records for that date
        """
        start = datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        return self.get_consumption(period_from=start, period_to=end)

    def get_historical_consumption(self, days: int = 4) -> List[Dict[str, Any]]:
        """Get consumption for the last N days.

        Args:
            days: Number of days to fetch (default: 4)

        Returns:
            List of all consumption records for the period
        """
        period_to = datetime.now(timezone.utc)
        period_from = period_to - timedelta(days=days)

        return self.get_consumption(period_from=period_from, period_to=period_to)
