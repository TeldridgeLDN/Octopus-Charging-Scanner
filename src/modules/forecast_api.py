"""Guy Lipman Energy Forecast Scraper

Scrapes 7-day electricity price forecasts from Guy Lipman's energy forecasting website.
Uses robust HTML parsing with fallback handling for structure changes.
"""

from typing import Dict, List, Any
import logging
import requests
from bs4 import BeautifulSoup
from .octopus_api import BaseAPIClient

logger = logging.getLogger(__name__)


class ForecastAPIClient(BaseAPIClient):
    """Scrape Guy Lipman energy price forecasts.

    Extracts 7-day price forecasts from HTML tables. Implements robust parsing
    with graceful degradation if the website structure changes.
    """

    BASE_URL = "https://energy.guylipman.com/forecasts"

    def __init__(self, timeout: int = 10, max_retries: int = 3):
        """Initialize Forecast API client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        super().__init__(timeout, max_retries)

    def get_forecasts(self, region: str = "H") -> List[Dict[str, Any]]:
        """Fetch 7-day price forecasts for a region.

        Args:
            region: DNO region code (default: H for Southern England)

        Returns:
            List of forecast slots with structure:
            [
                {
                    "date": "2025-12-07",
                    "time": "00:00",
                    "price": 12.5,
                    "source": "forecast"
                },
                ...
            ]

            Returns empty list if scraping fails (graceful degradation).
        """
        url = f"{self.BASE_URL}?region={region}"

        try:
            logger.info(f"Fetching forecasts from {url}")
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                },
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            forecasts = self._parse_forecast_table(soup)

            if forecasts:
                logger.info(f"Successfully parsed {len(forecasts)} forecast entries")
            else:
                logger.warning(
                    "No forecasts found in HTML - structure may have changed"
                )

            return forecasts

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch forecasts: {e}")
            logger.info("Falling back to Octopus-only mode")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing forecasts: {e}")
            logger.info("Falling back to Octopus-only mode")
            return []

    def _parse_forecast_table(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse forecast data from HTML tables or JavaScript variables.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            List of parsed forecast entries
        """
        forecasts = []

        # Try JavaScript variable parsing first (current site structure)
        forecasts = self._parse_strategy_javascript(soup)
        if forecasts:
            return forecasts

        # Fallback to table parsing strategies
        forecasts = self._parse_strategy_table_class(soup)
        if forecasts:
            return forecasts

        forecasts = self._parse_strategy_data_table(soup)
        if forecasts:
            return forecasts

        forecasts = self._parse_strategy_generic_table(soup)
        return forecasts

    def _parse_strategy_javascript(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse forecast data from JavaScript variables (current site structure).

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            List of forecast entries or empty list
        """
        import re
        from datetime import datetime, timedelta

        try:
            # Find script tags containing the price data
            scripts = soup.find_all("script")
            prices_data = None
            labels_data = None

            for script in scripts:
                if script.string and "var prices =" in script.string:
                    # Extract prices array: var prices = ['11.84', '10.66', ...]
                    prices_match = re.search(
                        r"var prices\s*=\s*\[(.*?)\];", script.string, re.DOTALL
                    )
                    labels_match = re.search(
                        r"var labels\s*=\s*\[(.*?)\];", script.string, re.DOTALL
                    )

                    if prices_match and labels_match:
                        # Parse prices (remove quotes and convert to floats)
                        prices_str = prices_match.group(1)
                        prices_data = [
                            float(p.strip().strip("'\"")) for p in prices_str.split(",")
                        ]

                        # Parse labels  (e.g., ['Thu 00h', 'Thu 01h', ...])
                        labels_str = labels_match.group(1)
                        labels_data = [
                            label.strip().strip("'\"")
                            for label in labels_str.split(",")
                        ]
                        break

            if not prices_data or not labels_data:
                logger.warning("Could not find prices/labels in JavaScript")
                return []

            if len(prices_data) != len(labels_data):
                logger.warning(
                    f"Mismatch: {len(prices_data)} prices vs {len(labels_data)} labels"
                )
                return []

            # Convert to forecast format
            forecasts = []
            # Estimate start date (today)
            base_date = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            for i, (label, price) in enumerate(zip(labels_data, prices_data)):
                # Calculate datetime (rough approximation - just use index)
                try:
                    forecast_time = base_date + timedelta(hours=i)
                    forecasts.append(
                        {
                            "time": forecast_time.isoformat(),
                            "price": price,
                            "source": "forecast",
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse label '{label}': {e}")
                    continue

            logger.info(f"Parsed {len(forecasts)} forecasts from JavaScript variables")
            return forecasts

        except Exception as e:
            logger.warning(f"JavaScript parsing failed: {e}")
            return []

    def _parse_strategy_table_class(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse using table class selector (primary strategy).

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            List of forecast entries or empty list
        """
        try:
            table = soup.find("table", {"class": "forecast-table"})
            if not table:
                return []

            rows = table.find_all("tr")[1:]  # Skip header row
            forecasts = []

            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    forecasts.append(
                        {
                            "date": cells[0].text.strip(),
                            "time": cells[1].text.strip(),
                            "price": float(cells[2].text.strip()),
                            "source": "forecast",
                        }
                    )

            return forecasts

        except (AttributeError, ValueError, IndexError) as e:
            logger.debug(f"Strategy 1 failed: {e}")
            return []

    def _parse_strategy_data_table(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse using data-table attribute (secondary strategy).

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            List of forecast entries or empty list
        """
        try:
            table = soup.find("table", {"data-table": "forecasts"})
            if not table:
                return []

            rows = table.find_all("tr")[1:]
            forecasts = []

            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    forecasts.append(
                        {
                            "date": cells[0].text.strip(),
                            "time": cells[1].text.strip(),
                            "price": float(cells[2].text.strip()),
                            "source": "forecast",
                        }
                    )

            return forecasts

        except (AttributeError, ValueError, IndexError) as e:
            logger.debug(f"Strategy 2 failed: {e}")
            return []

    def _parse_strategy_generic_table(
        self, soup: BeautifulSoup
    ) -> List[Dict[str, Any]]:
        """Parse using generic table search (tertiary strategy).

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            List of forecast entries or empty list
        """
        try:
            tables = soup.find_all("table")
            if not tables:
                return []

            # Try each table until we find data
            for table in tables:
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue

                # Check if first row looks like a header
                header = rows[0].find_all(["th", "td"])
                if not header:
                    continue

                forecasts = []
                for row in rows[1:]:
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        try:
                            forecasts.append(
                                {
                                    "date": cells[0].text.strip(),
                                    "time": cells[1].text.strip(),
                                    "price": float(cells[2].text.strip()),
                                    "source": "forecast",
                                }
                            )
                        except (ValueError, IndexError):
                            continue

                if forecasts:
                    return forecasts

            return []

        except Exception as e:
            logger.debug(f"Strategy 3 failed: {e}")
            return []

    def is_available(self, region: str = "H") -> bool:
        """Check if the forecast service is available.

        Args:
            region: DNO region code (default: H for Southern England)

        Returns:
            True if service is accessible, False otherwise
        """
        forecasts = self.get_forecasts(region)
        return len(forecasts) > 0
