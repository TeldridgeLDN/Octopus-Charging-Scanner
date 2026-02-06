"""Tests for WindowStatus detection in analyzer module."""

import pytest
from datetime import datetime, timedelta, timezone

from src.modules.analyzer import (
    ChargingWindow,
    WindowStatus,
    OpportunityRating,
)


@pytest.fixture
def sample_window():
    """Create a sample charging window for testing."""
    start_time = datetime(2025, 12, 9, 2, 0, tzinfo=timezone.utc)
    end_time = datetime(2025, 12, 9, 6, 0, tzinfo=timezone.utc)

    return ChargingWindow(
        start=start_time,
        end=end_time,
        avg_price=10.5,
        avg_carbon=120,
        total_cost=3.15,
        total_carbon=3600,
        opportunity_score=85.0,
        rating=OpportunityRating.EXCELLENT,
        reason="both",
        savings_vs_baseline=1.50,
    )


class TestWindowStatus:
    """Test window status detection methods."""

    def test_upcoming_window_before_start(self, sample_window):
        """Test window is UPCOMING when current time is before start."""
        # 1 hour before window starts
        current_time = sample_window.start - timedelta(hours=1)

        status = sample_window.get_status(current_time)

        assert status == WindowStatus.UPCOMING

    def test_active_window_at_start(self, sample_window):
        """Test window is ACTIVE exactly at start time."""
        current_time = sample_window.start

        status = sample_window.get_status(current_time)

        # At start time, window is active (not < start)
        assert status == WindowStatus.ACTIVE

    def test_active_window_during(self, sample_window):
        """Test window is ACTIVE during the window period."""
        # 2 hours into the 4-hour window
        current_time = sample_window.start + timedelta(hours=2)

        status = sample_window.get_status(current_time)

        assert status == WindowStatus.ACTIVE

    def test_active_window_before_end(self, sample_window):
        """Test window is ACTIVE just before end time."""
        # 1 minute before end
        current_time = sample_window.end - timedelta(minutes=1)

        status = sample_window.get_status(current_time)

        assert status == WindowStatus.ACTIVE

    def test_passed_window_at_end(self, sample_window):
        """Test window is still ACTIVE exactly at end time."""
        current_time = sample_window.end

        status = sample_window.get_status(current_time)

        # At end time exactly, window is still active (current_time <= end)
        assert status == WindowStatus.ACTIVE

    def test_passed_window_after_end(self, sample_window):
        """Test window is PASSED after end time."""
        # 2 hours after window ends
        current_time = sample_window.end + timedelta(hours=2)

        status = sample_window.get_status(current_time)

        assert status == WindowStatus.PASSED

    def test_defaults_to_current_time(self, sample_window):
        """Test status uses current time when none provided."""
        # This will use datetime.now(), so we can't predict the exact status
        # Just verify it returns a valid WindowStatus
        status = sample_window.get_status()

        assert isinstance(status, WindowStatus)
        assert status in [
            WindowStatus.UPCOMING,
            WindowStatus.ACTIVE,
            WindowStatus.PASSED,
        ]


class TestTimeUntilStart:
    """Test time_until_start calculations."""

    def test_positive_time_before_start(self, sample_window):
        """Test positive delta when window hasn't started."""
        # 3 hours before start
        current_time = sample_window.start - timedelta(hours=3)

        time_delta = sample_window.time_until_start(current_time)

        assert time_delta == timedelta(hours=3)
        assert time_delta.total_seconds() > 0

    def test_zero_time_at_start(self, sample_window):
        """Test zero delta exactly at start time."""
        current_time = sample_window.start

        time_delta = sample_window.time_until_start(current_time)

        assert time_delta == timedelta(0)
        assert time_delta.total_seconds() == 0

    def test_negative_time_after_start(self, sample_window):
        """Test negative delta after window started."""
        # 1 hour after start
        current_time = sample_window.start + timedelta(hours=1)

        time_delta = sample_window.time_until_start(current_time)

        assert time_delta == timedelta(hours=-1)
        assert time_delta.total_seconds() < 0

    def test_negative_time_after_window_ends(self, sample_window):
        """Test negative delta after window has completely passed."""
        # 2 hours after end
        current_time = sample_window.end + timedelta(hours=2)

        time_delta = sample_window.time_until_start(current_time)

        # Start was 6 hours ago (4 hour window + 2 hours after)
        assert time_delta == timedelta(hours=-6)
        assert time_delta.total_seconds() < 0

    def test_defaults_to_current_time(self, sample_window):
        """Test uses current time when none provided."""
        time_delta = sample_window.time_until_start()

        # Can't predict exact value, but should be a timedelta
        assert isinstance(time_delta, timedelta)


class TestTimeUntilEnd:
    """Test time_until_end calculations."""

    def test_positive_time_before_window(self, sample_window):
        """Test positive delta when window hasn't started yet."""
        # 2 hours before start (6 hours before end)
        current_time = sample_window.start - timedelta(hours=2)

        time_delta = sample_window.time_until_end(current_time)

        # End is 6 hours away (2 + 4-hour window)
        assert time_delta == timedelta(hours=6)
        assert time_delta.total_seconds() > 0

    def test_positive_time_during_window(self, sample_window):
        """Test positive delta during window."""
        # 1 hour after start (3 hours before end)
        current_time = sample_window.start + timedelta(hours=1)

        time_delta = sample_window.time_until_end(current_time)

        assert time_delta == timedelta(hours=3)
        assert time_delta.total_seconds() > 0

    def test_zero_time_at_end(self, sample_window):
        """Test zero delta exactly at end time."""
        current_time = sample_window.end

        time_delta = sample_window.time_until_end(current_time)

        assert time_delta == timedelta(0)
        assert time_delta.total_seconds() == 0

    def test_negative_time_after_end(self, sample_window):
        """Test negative delta after window ends."""
        # 2 hours after end
        current_time = sample_window.end + timedelta(hours=2)

        time_delta = sample_window.time_until_end(current_time)

        assert time_delta == timedelta(hours=-2)
        assert time_delta.total_seconds() < 0

    def test_defaults_to_current_time(self, sample_window):
        """Test uses current time when none provided."""
        time_delta = sample_window.time_until_end()

        # Can't predict exact value, but should be a timedelta
        assert isinstance(time_delta, timedelta)


class TestTimezoneHandling:
    """Test timezone handling in window status methods."""

    def test_handles_naive_datetime(self):
        """Test works with naive (no timezone) datetimes."""
        # Create window with naive datetimes
        start_time = datetime(2025, 12, 9, 2, 0)  # No timezone
        end_time = datetime(2025, 12, 9, 6, 0)

        window = ChargingWindow(
            start=start_time,
            end=end_time,
            avg_price=10.0,
            avg_carbon=100,
            total_cost=3.0,
            total_carbon=3000,
            opportunity_score=80.0,
            rating=OpportunityRating.GOOD,
            reason="cheap",
            savings_vs_baseline=1.0,
        )

        # Before window
        current_time = datetime(2025, 12, 9, 1, 0)
        assert window.get_status(current_time) == WindowStatus.UPCOMING

        # During window
        current_time = datetime(2025, 12, 9, 4, 0)
        assert window.get_status(current_time) == WindowStatus.ACTIVE

        # After window
        current_time = datetime(2025, 12, 9, 7, 0)
        assert window.get_status(current_time) == WindowStatus.PASSED

    def test_handles_utc_timezone(self):
        """Test works with UTC timezone."""
        start_time = datetime(2025, 12, 9, 2, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 9, 6, 0, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start_time,
            end=end_time,
            avg_price=10.0,
            avg_carbon=100,
            total_cost=3.0,
            total_carbon=3000,
            opportunity_score=80.0,
            rating=OpportunityRating.GOOD,
            reason="cheap",
            savings_vs_baseline=1.0,
        )

        current_time = datetime(2025, 12, 9, 4, 0, tzinfo=timezone.utc)
        assert window.get_status(current_time) == WindowStatus.ACTIVE


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_short_window(self):
        """Test 30-minute window."""
        start_time = datetime(2025, 12, 9, 2, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 9, 2, 30, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start_time,
            end=end_time,
            avg_price=10.0,
            avg_carbon=100,
            total_cost=0.75,
            total_carbon=900,
            opportunity_score=80.0,
            rating=OpportunityRating.GOOD,
            reason="cheap",
            savings_vs_baseline=0.25,
        )

        # 15 minutes into window
        current_time = start_time + timedelta(minutes=15)
        assert window.get_status(current_time) == WindowStatus.ACTIVE

        # Just passed
        current_time = end_time + timedelta(minutes=1)
        assert window.get_status(current_time) == WindowStatus.PASSED

    def test_overnight_window_crossing_midnight(self):
        """Test window that crosses midnight."""
        start_time = datetime(2025, 12, 9, 23, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 10, 3, 0, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start_time,
            end=end_time,
            avg_price=10.0,
            avg_carbon=100,
            total_cost=3.0,
            total_carbon=3000,
            opportunity_score=85.0,
            rating=OpportunityRating.EXCELLENT,
            reason="both",
            savings_vs_baseline=1.5,
        )

        # Before midnight (23:30)
        current_time = datetime(2025, 12, 9, 23, 30, tzinfo=timezone.utc)
        assert window.get_status(current_time) == WindowStatus.ACTIVE

        # After midnight (01:00)
        current_time = datetime(2025, 12, 10, 1, 0, tzinfo=timezone.utc)
        assert window.get_status(current_time) == WindowStatus.ACTIVE

        # After window (04:00)
        current_time = datetime(2025, 12, 10, 4, 0, tzinfo=timezone.utc)
        assert window.get_status(current_time) == WindowStatus.PASSED
