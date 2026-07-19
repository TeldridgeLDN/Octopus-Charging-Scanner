"""Tests for daily_notification.fetch_data source selection.

Confirms the 3-tier chain: Octopus published prices win when available, and
otherwise fetch_data delegates to the agile-first forecast helper.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.daily_notification as dn  # noqa: E402
from modules.analyzer import PriceSlot  # noqa: E402


def _make_config():
    return {
        "user": {
            "region": "H",
            "postcode": "E1",
            "carbon_region_id": None,
        },
    }


def _octopus_prices_covering_next_day():
    """96 half-hourly Octopus slots starting at today 00:00 UTC (covers +47h)."""
    start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    prices = []
    for i in range(96):
        t = start + timedelta(minutes=30 * i)
        prices.append(
            {
                "valid_from": t.isoformat().replace("+00:00", "Z"),
                "value_inc_vat": 15.0 + i * 0.1,
            }
        )
    return prices


def test_fetch_data_prefers_published_octopus():
    octopus = MagicMock()
    octopus.get_prices.return_value = _octopus_prices_covering_next_day()
    carbon = MagicMock()
    carbon.get_intensity.return_value = []

    with patch.object(dn, "OctopusAPIClient", return_value=octopus), patch.object(
        dn, "CarbonAPIClient", return_value=carbon
    ), patch.object(dn, "fetch_forecast_price_slots") as mock_fetch:
        price_slots, carbon_slots, price_source = dn.fetch_data(_make_config())

    assert price_source == "octopus_actual"
    assert all(p.source == "octopus" for p in price_slots)
    # Forecast helper never consulted when Octopus covers next day.
    assert not mock_fetch.called


def test_fetch_data_falls_back_to_forecast_helper():
    octopus = MagicMock()
    octopus.get_prices.return_value = []  # no coverage -> fall back
    carbon = MagicMock()
    carbon.get_intensity.return_value = []

    forecast_slots = [
        PriceSlot(
            datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc), 9.0, "agile_predict"
        ),
    ]

    with patch.object(dn, "OctopusAPIClient", return_value=octopus), patch.object(
        dn, "CarbonAPIClient", return_value=carbon
    ), patch.object(
        dn,
        "fetch_forecast_price_slots",
        return_value=(forecast_slots, "agile_predict"),
    ) as mock_fetch:
        price_slots, carbon_slots, price_source = dn.fetch_data(_make_config())

    assert price_source == "agile_predict"
    assert mock_fetch.called
    mock_fetch.assert_called_once_with("H")
    # Neutral carbon slots created for price-only analysis.
    assert len(carbon_slots) == len(price_slots)
