"""Tests for negative pricing alert functionality."""

import pytest
from datetime import datetime, timezone

from src.modules.analyzer import ChargingWindow, OpportunityRating


@pytest.fixture
def negative_pricing_window():
    """Create a charging window with negative pricing."""
    start_time = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
    end_time = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

    return ChargingWindow(
        start=start_time,
        end=end_time,
        avg_price=-5.5,  # Negative pricing!
        avg_carbon=85,
        total_cost=-1.65,  # Negative cost = earnings
        total_carbon=2550,
        opportunity_score=100.0,
        rating=OpportunityRating.EXCELLENT,
        reason="cheap",
        savings_vs_baseline=6.15,  # Massive savings!
    )


@pytest.fixture
def positive_pricing_window():
    """Create a normal charging window with positive pricing."""
    start_time = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
    end_time = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

    return ChargingWindow(
        start=start_time,
        end=end_time,
        avg_price=8.5,
        avg_carbon=100,
        total_cost=2.55,
        total_carbon=3000,
        opportunity_score=90.0,
        rating=OpportunityRating.EXCELLENT,
        reason="both",
        savings_vs_baseline=2.0,
    )


@pytest.fixture
def zero_pricing_window():
    """Create a charging window with exactly zero pricing."""
    start_time = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
    end_time = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

    return ChargingWindow(
        start=start_time,
        end=end_time,
        avg_price=0.0,  # Free!
        avg_carbon=90,
        total_cost=0.0,
        total_carbon=2700,
        opportunity_score=95.0,
        rating=OpportunityRating.EXCELLENT,
        reason="cheap",
        savings_vs_baseline=4.5,
    )


class TestHasNegativePricing:
    """Test has_negative_pricing() method."""

    def test_detects_negative_pricing(self, negative_pricing_window):
        """Test correctly identifies negative pricing."""
        assert negative_pricing_window.has_negative_pricing() is True

    def test_rejects_positive_pricing(self, positive_pricing_window):
        """Test returns False for positive pricing."""
        assert positive_pricing_window.has_negative_pricing() is False

    def test_rejects_zero_pricing(self, zero_pricing_window):
        """Test returns False for exactly zero pricing."""
        assert zero_pricing_window.has_negative_pricing() is False

    def test_very_small_negative_price(self):
        """Test detects even very small negative prices."""
        start = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=-0.01,  # Tiny negative price
            avg_carbon=100,
            total_cost=-0.003,
            total_carbon=3000,
            opportunity_score=80.0,
            rating=OpportunityRating.GOOD,
            reason="cheap",
            savings_vs_baseline=4.5,
        )

        assert window.has_negative_pricing() is True

    def test_large_negative_price(self):
        """Test handles very large negative prices."""
        start = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=-50.0,  # Extremely negative
            avg_carbon=80,
            total_carbon=2400,
            total_cost=-15.0,
            opportunity_score=100.0,
            rating=OpportunityRating.EXCELLENT,
            reason="cheap",
            savings_vs_baseline=30.0,
        )

        assert window.has_negative_pricing() is True


class TestGetEarningsEstimate:
    """Test get_earnings_estimate() method."""

    def test_calculates_earnings_for_default_kwh(self, negative_pricing_window):
        """Test earnings calculation with default 30kWh."""
        earnings = negative_pricing_window.get_earnings_estimate()

        # avg_price = -5.5p/kWh
        # 30kWh * -5.5p = -165p = -£1.65
        # Earnings (absolute value) = £1.65
        assert earnings == pytest.approx(1.65, abs=0.01)

    def test_calculates_earnings_for_custom_kwh(self, negative_pricing_window):
        """Test earnings calculation with custom kWh amount."""
        earnings = negative_pricing_window.get_earnings_estimate(kwh=50.0)

        # 50kWh * -5.5p = -275p = -£2.75
        # Earnings = £2.75
        assert earnings == pytest.approx(2.75, abs=0.01)

    def test_returns_none_for_positive_pricing(self, positive_pricing_window):
        """Test returns None when pricing is positive."""
        earnings = positive_pricing_window.get_earnings_estimate()

        assert earnings is None

    def test_returns_none_for_zero_pricing(self, zero_pricing_window):
        """Test returns None when pricing is exactly zero."""
        earnings = zero_pricing_window.get_earnings_estimate()

        assert earnings is None

    def test_small_earnings(self):
        """Test calculates small earnings correctly."""
        start = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=-0.5,  # Small negative price
            avg_carbon=100,
            total_cost=-0.15,
            total_carbon=3000,
            opportunity_score=85.0,
            rating=OpportunityRating.EXCELLENT,
            reason="cheap",
            savings_vs_baseline=4.65,
        )

        earnings = window.get_earnings_estimate(kwh=30.0)

        # 30kWh * -0.5p = -15p = -£0.15
        assert earnings == pytest.approx(0.15, abs=0.01)

    def test_large_earnings(self):
        """Test calculates large earnings correctly."""
        start = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=-20.0,  # Large negative price
            avg_carbon=75,
            total_cost=-6.0,
            total_carbon=2250,
            opportunity_score=100.0,
            rating=OpportunityRating.EXCELLENT,
            reason="cheap",
            savings_vs_baseline=10.5,
        )

        earnings = window.get_earnings_estimate(kwh=30.0)

        # 30kWh * -20p = -600p = -£6.00
        assert earnings == pytest.approx(6.0, abs=0.01)

    def test_earnings_with_different_kwh_values(self, negative_pricing_window):
        """Test earnings scale linearly with kWh."""
        earnings_10 = negative_pricing_window.get_earnings_estimate(kwh=10.0)
        earnings_20 = negative_pricing_window.get_earnings_estimate(kwh=20.0)
        earnings_30 = negative_pricing_window.get_earnings_estimate(kwh=30.0)

        # Should scale linearly
        assert earnings_20 == pytest.approx(earnings_10 * 2, abs=0.01)
        assert earnings_30 == pytest.approx(earnings_10 * 3, abs=0.01)


class TestNegativePricingEdgeCases:
    """Test edge cases for negative pricing functionality."""

    def test_negative_pricing_with_high_carbon(self):
        """Test negative pricing still detected even with high carbon."""
        start = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=-3.0,  # Negative price
            avg_carbon=250,  # High carbon (dirty energy)
            total_cost=-0.9,
            total_carbon=7500,
            opportunity_score=75.0,
            rating=OpportunityRating.GOOD,
            reason="cheap",
            savings_vs_baseline=5.4,
        )

        assert window.has_negative_pricing() is True
        earnings = window.get_earnings_estimate(kwh=30.0)
        assert earnings == pytest.approx(0.9, abs=0.01)

    def test_very_short_negative_pricing_window(self):
        """Test negative pricing works for short windows."""
        start = datetime(2025, 12, 10, 3, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 10, 3, 30, tzinfo=timezone.utc)  # 30 minutes

        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=-8.0,
            avg_carbon=90,
            total_cost=-1.2,  # For 30min charge
            total_carbon=1350,
            opportunity_score=95.0,
            rating=OpportunityRating.EXCELLENT,
            reason="cheap",
            savings_vs_baseline=2.7,
        )

        assert window.has_negative_pricing() is True
        # Earnings should still calculate correctly
        earnings = window.get_earnings_estimate(kwh=15.0)  # 15kWh in 30min
        assert earnings == pytest.approx(1.2, abs=0.01)

    def test_negative_total_cost_matches_avg_price(self):
        """Test that negative total_cost aligns with negative avg_price."""
        start = datetime(2025, 12, 10, 2, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 10, 6, 0, tzinfo=timezone.utc)

        # For consistency: total_cost should be negative when avg_price is negative
        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=-10.0,
            avg_carbon=100,
            total_cost=-3.0,  # Should be negative
            total_carbon=3000,
            opportunity_score=100.0,
            rating=OpportunityRating.EXCELLENT,
            reason="cheap",
            savings_vs_baseline=7.5,
        )

        assert window.has_negative_pricing() is True
        assert window.total_cost < 0  # Verify cost is also negative
        earnings = window.get_earnings_estimate(kwh=30.0)
        assert earnings == pytest.approx(3.0, abs=0.01)


class TestNegativePricingIntegration:
    """Test negative pricing in realistic scenarios."""

    def test_forecast_vs_actual_negative_pricing(self):
        """Test handling when forecast predicts negative but actual differs."""
        # This tests the scenario from SESSION_SUMMARY_2025-12-08.md
        # where forecast predicted -4.17p but actual was +3.69p

        forecast_window = ChargingWindow(
            start=datetime(2025, 12, 8, 4, 0, tzinfo=timezone.utc),
            end=datetime(2025, 12, 8, 5, 0, tzinfo=timezone.utc),
            avg_price=-4.17,  # Forecast prediction
            avg_carbon=100,
            total_cost=-1.25,
            total_carbon=3000,
            opportunity_score=100.0,
            rating=OpportunityRating.EXCELLENT,
            reason="cheap",
            savings_vs_baseline=5.75,
        )

        actual_window = ChargingWindow(
            start=datetime(2025, 12, 8, 4, 0, tzinfo=timezone.utc),
            end=datetime(2025, 12, 8, 5, 0, tzinfo=timezone.utc),
            avg_price=3.69,  # Actual price (positive!)
            avg_carbon=100,
            total_cost=1.11,
            total_carbon=3000,
            opportunity_score=95.0,
            rating=OpportunityRating.EXCELLENT,
            reason="both",
            savings_vs_baseline=3.39,
        )

        # Forecast would trigger negative pricing alert
        assert forecast_window.has_negative_pricing() is True
        assert forecast_window.get_earnings_estimate() == pytest.approx(1.25, abs=0.01)

        # Actual would NOT
        assert actual_window.has_negative_pricing() is False
        assert actual_window.get_earnings_estimate() is None
