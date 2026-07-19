"""Regression test for duplicate notification on negative-pricing days.

Bug: on a negative-pricing day the script sent BOTH a dedicated
"MONEY-MAKING ALERT" and the normal notification (which itself contained a
second negative-pricing block), so the user received two Pushover messages
for one event.

Contract: exactly ONE Pushover message is sent on a negative-pricing day.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# The script does `from modules...` relying on `src` being on sys.path.
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.daily_notification as dn  # noqa: E402
from modules.analyzer import PriceSlot, CarbonSlot  # noqa: E402


def _make_config():
    return {
        "preferences": {"price_weight": 0.6, "carbon_weight": 0.4},
        "thresholds": {
            "price_excellent": 10,
            "price_good": 15,
            "carbon_excellent": 100,
            "carbon_good": 150,
        },
        "user": {
            "typical_charge_kwh": 10.0,
            "charging_rate_kw": 2.3,
            "region": "H",
        },
        "apis": {
            "pushover": {"user_key": "u", "api_token": "t"},
        },
    }


def _make_slots_with_negative():
    """48 half-hourly slots; a handful are negatively priced."""
    start = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
    price_slots = []
    carbon_slots = []
    for i in range(48):
        t = start + timedelta(minutes=30 * i)
        # Slots 4-9 are negatively priced (money-making window)
        price = -5.0 if 4 <= i < 10 else 15.0
        price_slots.append(PriceSlot(t, price, "octopus"))
        carbon_slots.append(CarbonSlot(t, 120))
    return price_slots, carbon_slots


def test_exactly_one_notification_on_negative_price_day():
    price_slots, carbon_slots = _make_slots_with_negative()

    pushover_instance = MagicMock()
    pushover_instance.send_notification.return_value = True

    with patch.object(dn, "load_config", return_value=_make_config()), patch.object(
        dn, "fetch_data", return_value=(price_slots, carbon_slots, "octopus_actual")
    ), patch.object(dn, "DataStore", return_value=MagicMock()), patch.object(
        dn, "sync_to_google_calendar", return_value=None
    ), patch.object(
        dn, "AgilePredict", return_value=MagicMock()
    ), patch.object(
        dn, "PushoverClient", return_value=pushover_instance
    ):
        result = dn.main()

    assert result == 0
    # Exactly one Pushover message for the single negative-pricing event.
    assert pushover_instance.send_notification.call_count == 1
