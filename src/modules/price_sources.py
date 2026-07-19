"""Shared price-forecast conversion and fetch helpers.

Converts agile_predict and Guy Lipman forecast payloads into ``PriceSlot``
objects and provides a forecast fetch that tries agile_predict first, then
falls back to the Guy Lipman scraper. Used by both the daily notification
script and the multi-day planner so the conversion logic lives in one place.
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging

from .agile_predict_api import AgilePredict
from .forecast_api import ForecastAPIClient
from .analyzer import PriceSlot

logger = logging.getLogger(__name__)


def agile_to_price_slots(slots: List[Dict[str, Any]]) -> List[PriceSlot]:
    """Convert agile_predict forecast slots to PriceSlot objects.

    Args:
        slots: Raw agile_predict slots from AgilePredict.get_forecasts().

    Returns:
        List of PriceSlot with source "agile_predict".
    """
    price_slots = []
    for s in slots:
        slot_time = datetime.fromisoformat(s["date_time"].replace("Z", "+00:00"))
        price_slots.append(PriceSlot(slot_time, s["agile_pred"], "agile_predict"))
    return price_slots


def guy_lipman_to_price_slots(forecasts: List[Dict[str, Any]]) -> List[PriceSlot]:
    """Convert Guy Lipman forecast entries to PriceSlot objects.

    Handles both the old table-parsed format ({"date": "...", "time": "HH:MM"})
    and the new JavaScript-parsed format ({"time": ISO string}).

    Args:
        forecasts: Raw forecast entries from ForecastAPIClient.get_forecasts().

    Returns:
        List of PriceSlot with source "forecast".
    """
    price_slots = []
    for f in forecasts:
        if "date" in f:
            # Old table-parsed format: {"date": "2025-12-07", "time": "00:00"}
            date_str = f["date"]
            time_str = f["time"]
            dt_str = f"{date_str}T{time_str}:00+00:00"
            slot_time = datetime.fromisoformat(dt_str)
        else:
            # New JavaScript-parsed format: {"time": "2025-12-07T00:00:00"}
            time_str = f["time"]
            if "+" in time_str or time_str.endswith("Z"):
                slot_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            else:
                slot_time = datetime.fromisoformat(time_str).replace(
                    tzinfo=timezone.utc
                )
        price_slots.append(PriceSlot(slot_time, f["price"], "forecast"))
    return price_slots


def fetch_forecast_price_slots(
    region: str,
    agile_client: Optional[AgilePredict] = None,
    forecast_client: Optional[ForecastAPIClient] = None,
    days: int = 2,
) -> Tuple[List[PriceSlot], str]:
    """Fetch forecast prices, preferring agile_predict over Guy Lipman.

    Args:
        region: DNO region code.
        agile_client: Optional AgilePredict client (default-constructed if None).
        forecast_client: Optional Guy Lipman client (default-constructed if None).
        days: Number of days to request from agile_predict.

    Returns:
        Tuple of (price_slots, price_source) where price_source is
        "agile_predict" or "forecast".

    Raises:
        RuntimeError: If no forecast source returns usable data.
    """
    if agile_client is None:
        agile_client = AgilePredict()
    if forecast_client is None:
        forecast_client = ForecastAPIClient()

    # Tier 1: agile_predict ML forecast
    agile_slots = agile_client.get_forecasts(region, days=days)
    if agile_slots:
        price_slots = agile_to_price_slots(agile_slots)
        if price_slots:
            logger.info(f"✅ Using agile_predict FORECAST ({len(price_slots)} slots)")
            return price_slots, "agile_predict"

    # Tier 2: Guy Lipman scraper
    logger.info(f"Falling back to Guy Lipman forecast for region {region}")
    forecasts = forecast_client.get_forecasts(region)
    if forecasts:
        price_slots = guy_lipman_to_price_slots(forecasts)
        if price_slots:
            logger.info(f"✅ Using Guy Lipman FORECAST ({len(price_slots)} slots)")
            return price_slots, "forecast"

    raise RuntimeError("Failed to fetch forecast prices from all sources")
