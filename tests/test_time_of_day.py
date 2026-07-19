"""Tests for time_of_day helpers and agile_predict get_cheapest_window."""

from datetime import datetime, timezone

from src.modules.time_of_day import part_of_day, part_of_day_phrase
from src.modules.agile_predict_api import AgilePredict


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestPartOfDay:
    """Hour-boundary and BST-crossover behaviour for part_of_day (winter = UTC)."""

    def test_overnight_lower_boundary(self):
        # 04:59 -> overnight, 05:00 -> morning (January: London == UTC)
        assert part_of_day(_utc(2026, 1, 10, 4, 59)) == "overnight"
        assert part_of_day(_utc(2026, 1, 10, 5, 0)) == "morning"

    def test_afternoon_evening_boundary(self):
        # 16:59 -> afternoon, 17:00 -> evening
        assert part_of_day(_utc(2026, 1, 10, 16, 59)) == "afternoon"
        assert part_of_day(_utc(2026, 1, 10, 17, 0)) == "evening"

    def test_evening_overnight_boundary(self):
        # 22:59 -> evening, 23:00 -> overnight
        assert part_of_day(_utc(2026, 1, 10, 22, 59)) == "evening"
        assert part_of_day(_utc(2026, 1, 10, 23, 0)) == "overnight"

    def test_bst_crossover(self):
        # July 16:30 UTC == 17:30 BST -> evening (not afternoon)
        assert part_of_day(_utc(2026, 7, 16, 16, 30)) == "evening"


class TestPartOfDayPhrase:
    """Same-day and future-day phrase construction."""

    def test_same_day_this_prefix(self):
        assert part_of_day_phrase(_utc(2026, 1, 10, 8, 0)) == "this morning"
        assert part_of_day_phrase(_utc(2026, 1, 10, 14, 0)) == "this afternoon"
        assert part_of_day_phrase(_utc(2026, 1, 10, 19, 0)) == "this evening"

    def test_same_day_overnight_has_no_this(self):
        assert part_of_day_phrase(_utc(2026, 1, 10, 2, 0)) == "overnight"

    def test_future_day_label(self):
        dt = _utc(2026, 1, 10, 14, 0)
        assert part_of_day_phrase(dt, "Thursday") == "Thursday afternoon"
        assert part_of_day_phrase(_utc(2026, 1, 10, 2, 0), "Thursday") == (
            "Thursday overnight"
        )
        assert part_of_day_phrase(dt, "Tomorrow") == "Tomorrow afternoon"


def _slot(iso, price):
    return {
        "date_time": iso,
        "agile_pred": price,
        "agile_low": price - 2,
        "agile_high": price + 2,
        "source": "test",
    }


def _day_slots(prices, day="2026-07-16"):
    slots = []
    for i, p in enumerate(prices):
        hh = i // 2
        mm = (i % 2) * 30
        slots.append(_slot(f"{day}T{hh:02d}:{mm:02d}:00Z", p))
    return slots


class TestGetCheapestWindow:
    """Sliding cheapest 3-hour block selection."""

    def test_finds_cheapest_block(self):
        # prices: indices 2..7 are the cheap 3-hour block (6 x 30-min slots)
        prices = [20, 20, 5, 5, 5, 5, 5, 5, 20, 20]
        window = AgilePredict().get_cheapest_window(
            target_date="2026-07-16", block_hours=3.0, slots=_day_slots(prices)
        )
        assert window is not None
        assert window["avg_price"] == 5.0
        assert window["start"] == datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
        assert window["end"] == datetime(2026, 7, 16, 4, 0, tzinfo=timezone.utc)

    def test_none_when_too_few_slots(self):
        prices = [10, 9, 8]  # only 3 slots, need 6 for 3h
        window = AgilePredict().get_cheapest_window(
            target_date="2026-07-16", block_hours=3.0, slots=_day_slots(prices)
        )
        assert window is None

    def test_none_when_no_contiguous_run(self):
        # 8 slots but a 30-min gap breaks any 6-slot contiguous run
        full = _day_slots([20, 20, 5, 5, 5, 5, 5, 5])
        gapped = full[:3] + full[5:]  # drop slots at 01:00 and 01:30
        window = AgilePredict().get_cheapest_window(
            target_date="2026-07-16", block_hours=3.0, slots=gapped
        )
        assert window is None

    def test_filters_to_target_date(self):
        other = _day_slots([1, 1, 1, 1, 1, 1], day="2026-07-15")
        target = _day_slots([5, 5, 5, 5, 5, 5], day="2026-07-16")
        window = AgilePredict().get_cheapest_window(
            target_date="2026-07-16", block_hours=3.0, slots=other + target
        )
        assert window is not None
        assert window["avg_price"] == 5.0
        assert window["start"].date().isoformat() == "2026-07-16"
