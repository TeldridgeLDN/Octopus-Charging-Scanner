"""Tests for analyzer module"""

import pytest
from datetime import datetime, timezone, timedelta
from src.modules.analyzer import (
    Analyzer,
    OpportunityRating,
    PriceSlot,
    CarbonSlot,
    ChargingWindow,
)


class TestAnalyzer:
    """Test Analyzer class"""

    def test_init_default_params(self):
        """Test analyzer initialization with defaults"""
        analyzer = Analyzer()
        assert analyzer.price_weight == 0.6
        assert analyzer.carbon_weight == 0.4
        assert analyzer.price_excellent == 10
        assert analyzer.carbon_excellent == 100

    def test_init_custom_params(self):
        """Test analyzer initialization with custom parameters"""
        analyzer = Analyzer(
            price_weight=0.7,
            carbon_weight=0.3,
            price_excellent=12,
            carbon_excellent=90,
        )
        assert analyzer.price_weight == 0.7
        assert analyzer.carbon_weight == 0.3
        assert analyzer.price_excellent == 12
        assert analyzer.carbon_excellent == 90

    def test_init_weights_validation(self):
        """Test that weights must sum to 1.0"""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            Analyzer(price_weight=0.5, carbon_weight=0.3)

    def test_calculate_price_score_excellent(self):
        """Test price score calculation for excellent prices"""
        analyzer = Analyzer()
        assert analyzer.calculate_price_score(5) == 100.0
        assert analyzer.calculate_price_score(10) == 100.0

    def test_calculate_price_score_good(self):
        """Test price score calculation for good prices"""
        analyzer = Analyzer()
        assert analyzer.calculate_price_score(12) == 75.0
        assert analyzer.calculate_price_score(15) == 75.0

    def test_calculate_price_score_average(self):
        """Test price score calculation for average prices"""
        analyzer = Analyzer()
        assert analyzer.calculate_price_score(18) == 50.0
        assert analyzer.calculate_price_score(20) == 50.0

    def test_calculate_price_score_poor(self):
        """Test price score calculation for poor prices"""
        analyzer = Analyzer()
        assert analyzer.calculate_price_score(25) == 25.0
        assert analyzer.calculate_price_score(30) == 25.0

    def test_calculate_carbon_score_excellent(self):
        """Test carbon score calculation for excellent intensity"""
        analyzer = Analyzer()
        assert analyzer.calculate_carbon_score(50) == 100.0
        assert analyzer.calculate_carbon_score(100) == 100.0

    def test_calculate_carbon_score_good(self):
        """Test carbon score calculation for good intensity"""
        analyzer = Analyzer()
        assert analyzer.calculate_carbon_score(120) == 75.0
        assert analyzer.calculate_carbon_score(150) == 75.0

    def test_calculate_carbon_score_average(self):
        """Test carbon score calculation for average intensity"""
        analyzer = Analyzer()
        assert analyzer.calculate_carbon_score(180) == 50.0
        assert analyzer.calculate_carbon_score(200) == 50.0

    def test_calculate_carbon_score_poor(self):
        """Test carbon score calculation for poor intensity"""
        analyzer = Analyzer()
        assert analyzer.calculate_carbon_score(250) == 25.0
        assert analyzer.calculate_carbon_score(300) == 25.0

    def test_calculate_opportunity_score_excellent(self):
        """Test combined score for excellent opportunity"""
        analyzer = Analyzer()  # 60% price, 40% carbon
        # Excellent price (100) + excellent carbon (100) = 100
        score = analyzer.calculate_opportunity_score(8, 80)
        assert score == 100.0

    def test_calculate_opportunity_score_weighted(self):
        """Test combined score with weighting"""
        analyzer = Analyzer()  # 60% price, 40% carbon
        # Good price (75) + poor carbon (25) = 0.6*75 + 0.4*25 = 55
        score = analyzer.calculate_opportunity_score(12, 250)
        assert score == 55.0

    def test_classify_opportunity_excellent(self):
        """Test opportunity classification - excellent"""
        analyzer = Analyzer()
        assert analyzer.classify_opportunity(95) == OpportunityRating.EXCELLENT
        assert analyzer.classify_opportunity(90) == OpportunityRating.EXCELLENT

    def test_classify_opportunity_good(self):
        """Test opportunity classification - good"""
        analyzer = Analyzer()
        assert analyzer.classify_opportunity(80) == OpportunityRating.GOOD
        assert analyzer.classify_opportunity(70) == OpportunityRating.GOOD

    def test_classify_opportunity_average(self):
        """Test opportunity classification - average"""
        analyzer = Analyzer()
        assert analyzer.classify_opportunity(60) == OpportunityRating.AVERAGE
        assert analyzer.classify_opportunity(50) == OpportunityRating.AVERAGE

    def test_classify_opportunity_poor(self):
        """Test opportunity classification - poor"""
        analyzer = Analyzer()
        assert analyzer.classify_opportunity(40) == OpportunityRating.POOR
        assert analyzer.classify_opportunity(25) == OpportunityRating.POOR

    def test_determine_reason_both(self):
        """Test reason determination - both cheap and clean"""
        analyzer = Analyzer()
        # Cheap (<=15p) and clean (<=150g)
        assert analyzer.determine_reason(10, 100) == "both"

    def test_determine_reason_cheap(self):
        """Test reason determination - cheap only"""
        analyzer = Analyzer()
        # Cheap (<=15p) but not clean (>150g)
        assert analyzer.determine_reason(12, 200) == "cheap"

    def test_determine_reason_clean(self):
        """Test reason determination - clean only"""
        analyzer = Analyzer()
        # Not cheap (>15p) but clean (<=150g)
        assert analyzer.determine_reason(20, 120) == "clean"

    def test_determine_reason_neither(self):
        """Test reason determination - neither"""
        analyzer = Analyzer()
        # Not cheap (>15p) and not clean (>150g)
        assert analyzer.determine_reason(25, 200) == "neither"

    def test_find_optimal_window_basic(self):
        """Test finding optimal charging window with basic data"""
        analyzer = Analyzer()

        # Create test data - 24 hours of half-hourly slots
        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        price_slots = []
        carbon_slots = []

        for i in range(48):
            slot_time = start_time + timedelta(minutes=30 * i)

            # Night time (00:00-06:00) is cheaper
            if 0 <= i < 12:
                price = 8.0  # Excellent
                carbon = 90  # Excellent
            else:
                price = 18.0  # Average
                carbon = 180  # Average

            price_slots.append(PriceSlot(slot_time, price, "octopus"))
            carbon_slots.append(CarbonSlot(slot_time, carbon))

        # Find 4-hour window (8 slots)
        window = analyzer.find_optimal_window(price_slots, carbon_slots, 4.0)

        assert window is not None
        assert window.start == start_time  # Should find 00:00
        assert window.rating == OpportunityRating.EXCELLENT
        assert window.avg_price == 8.0
        assert window.avg_carbon == 90

    def test_find_optimal_window_calculates_cost(self):
        """Test that optimal window calculates cost correctly"""
        analyzer = Analyzer()

        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        price_slots = [
            PriceSlot(start_time + timedelta(minutes=30 * i), 10.0, "octopus")
            for i in range(8)
        ]
        carbon_slots = [
            CarbonSlot(start_time + timedelta(minutes=30 * i), 100) for i in range(8)
        ]

        window = analyzer.find_optimal_window(price_slots, carbon_slots, 4.0)

        # 4 hours @ 7.4kW = 29.6 kWh
        # 29.6 kWh @ 10p/kWh = £2.96
        assert abs(window.total_cost - 2.96) < 0.01

    def test_find_optimal_window_calculates_carbon(self):
        """Test that optimal window calculates carbon correctly"""
        analyzer = Analyzer()

        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        price_slots = [
            PriceSlot(start_time + timedelta(minutes=30 * i), 10.0, "octopus")
            for i in range(8)
        ]
        carbon_slots = [
            CarbonSlot(start_time + timedelta(minutes=30 * i), 100) for i in range(8)
        ]

        window = analyzer.find_optimal_window(price_slots, carbon_slots, 4.0)

        # 4 hours @ 7.4kW = 29.6 kWh
        # 29.6 kWh @ 100 gCO2/kWh = 2960 gCO2
        assert window.total_carbon == 2960

    def test_find_optimal_window_respects_charge_rate(self):
        """Rate-awareness: kWh (and cost) scale with charge_rate_kw, not a
        hardcoded 7.4kW.

        Arithmetic (8 slots @ 10.0p, 4.0h duration):
          default 7.4kW -> kWh = 4.0 * 7.4 = 29.6 -> cost = 10.0*29.6/100 = £2.96
          2.3kW charger -> kWh = 4.0 * 2.3 =  9.2 -> cost = 10.0* 9.2/100 = £0.92
        """
        analyzer = Analyzer()

        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        price_slots = [
            PriceSlot(start_time + timedelta(minutes=30 * i), 10.0, "octopus")
            for i in range(8)
        ]
        carbon_slots = [
            CarbonSlot(start_time + timedelta(minutes=30 * i), 100) for i in range(8)
        ]

        window_23 = analyzer.find_optimal_window(
            price_slots, carbon_slots, 4.0, charge_rate_kw=2.3
        )
        window_default = analyzer.find_optimal_window(price_slots, carbon_slots, 4.0)

        # 4.0h * 2.3kW = 9.2 kWh @ 10p/kWh = £0.92
        assert abs(window_23.total_cost - 0.92) < 0.001
        # Default 7.4kW branch remains £2.96 and differs from the 2.3kW result
        assert abs(window_default.total_cost - 2.96) < 0.001
        assert window_23.total_cost != window_default.total_cost

    def test_find_optimal_window_savings_from_real_baseline(self):
        """Savings are computed from a real evening baseline when slots exist.

        Setup (48 half-hourly slots from 00:00):
          optimal window = 00:00-04:00 (8 slots @ 8.0p)
          evening baseline @ 18:00 = 8 slots @ 20.0p
        Default 7.4kW, 4.0h -> kWh = 29.6
          total_cost    = 8.0  * 29.6 / 100 = £2.368
          baseline_cost = 20.0 * 29.6 / 100 = £5.92
          savings       = 5.92 - 2.368       = £3.552
        """
        analyzer = Analyzer()

        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        price_slots = []
        carbon_slots = []
        for i in range(48):
            slot_time = start_time + timedelta(minutes=30 * i)
            if i < 8:
                price = 8.0  # cheap overnight (optimal)
            elif 36 <= i < 44:
                price = 20.0  # expensive evening baseline (18:00-22:00)
            else:
                price = 18.0
            price_slots.append(PriceSlot(slot_time, price, "octopus"))
            carbon_slots.append(CarbonSlot(slot_time, 180))

        baseline_time = start_time + timedelta(hours=18)  # 18:00
        window = analyzer.find_optimal_window(
            price_slots, carbon_slots, 4.0, baseline_time=baseline_time
        )

        assert abs(window.total_cost - 2.368) < 0.001
        assert window.savings_vs_baseline is not None
        assert abs(window.savings_vs_baseline - 3.552) < 0.001

    def test_find_optimal_window_no_baseline_savings_is_none(self):
        """Without a baseline time, savings is None (not fabricated via *1.5)."""
        analyzer = Analyzer()

        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        price_slots = [
            PriceSlot(start_time + timedelta(minutes=30 * i), 10.0, "octopus")
            for i in range(8)
        ]
        carbon_slots = [
            CarbonSlot(start_time + timedelta(minutes=30 * i), 100) for i in range(8)
        ]

        window = analyzer.find_optimal_window(price_slots, carbon_slots, 4.0)

        assert window.savings_vs_baseline is None

    def test_find_optimal_window_insufficient_baseline_savings_is_none(self):
        """When baseline slots are insufficient, savings is None (no fake £5)."""
        analyzer = Analyzer()

        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        # Only 8 slots of data; baseline time points past the end of the data,
        # so no baseline window can be formed.
        price_slots = [
            PriceSlot(start_time + timedelta(minutes=30 * i), 10.0, "octopus")
            for i in range(8)
        ]
        carbon_slots = [
            CarbonSlot(start_time + timedelta(minutes=30 * i), 100) for i in range(8)
        ]

        baseline_time = start_time + timedelta(hours=18)  # beyond available data
        window = analyzer.find_optimal_window(
            price_slots, carbon_slots, 4.0, baseline_time=baseline_time
        )

        assert window.savings_vs_baseline is None

    def test_find_optimal_window_empty_data(self):
        """Test that empty data raises ValueError"""
        analyzer = Analyzer()

        with pytest.raises(ValueError, match="Price and carbon data required"):
            analyzer.find_optimal_window([], [], 4.0)

    def test_find_optimal_window_no_overlap(self):
        """Test that non-overlapping data raises ValueError"""
        analyzer = Analyzer()

        price_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        carbon_time = datetime(2025, 12, 9, 0, 0, tzinfo=timezone.utc)

        price_slots = [PriceSlot(price_time, 10.0, "octopus")]
        carbon_slots = [CarbonSlot(carbon_time, 100)]

        with pytest.raises(ValueError, match="No overlapping"):
            analyzer.find_optimal_window(price_slots, carbon_slots, 4.0)

    def test_find_optimal_window_prefers_high_score(self):
        """Test that optimal window prefers highest combined score"""
        analyzer = Analyzer()

        start_time = datetime(2025, 12, 8, 0, 0, tzinfo=timezone.utc)
        price_slots = []
        carbon_slots = []

        for i in range(48):
            slot_time = start_time + timedelta(minutes=30 * i)

            # 02:00-06:00 (slots 4-11): Both cheap and clean (score: 100)
            # 06:00-10:00 (slots 12-19): Cheap but dirty (score: 70)
            # 10:00-24:00: Expensive and dirty (score: 25)
            if 4 <= i < 12:
                price, carbon = 8.0, 80  # Excellent both
            elif 12 <= i < 20:
                price, carbon = 10.0, 200  # Excellent price, poor carbon
            else:
                price, carbon = 25.0, 250  # Poor both

            price_slots.append(PriceSlot(slot_time, price, "octopus"))
            carbon_slots.append(CarbonSlot(slot_time, carbon))

        window = analyzer.find_optimal_window(price_slots, carbon_slots, 4.0)

        # Should select 02:00-06:00 (excellent both) over 06:00-10:00 (cheap only)
        expected_start = start_time + timedelta(hours=2)
        assert window.start == expected_start
        assert window.rating == OpportunityRating.EXCELLENT


class TestDataClasses:
    """Test data classes"""

    def test_price_slot_creation(self):
        """Test PriceSlot creation"""
        now = datetime.now(timezone.utc)
        slot = PriceSlot(now, 12.5, "octopus")
        assert slot.time == now
        assert slot.price == 12.5
        assert slot.source == "octopus"

    def test_carbon_slot_creation(self):
        """Test CarbonSlot creation"""
        now = datetime.now(timezone.utc)
        slot = CarbonSlot(now, 150)
        assert slot.time == now
        assert slot.intensity == 150

    def test_charging_window_creation(self):
        """Test ChargingWindow creation"""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=4)
        window = ChargingWindow(
            start=start,
            end=end,
            avg_price=10.5,
            avg_carbon=120,
            total_cost=3.15,
            total_carbon=3600,
            opportunity_score=85.0,
            rating=OpportunityRating.GOOD,
            reason="both",
            savings_vs_baseline=1.50,
        )
        assert window.start == start
        assert window.end == end
        assert window.rating == OpportunityRating.GOOD
        assert window.reason == "both"
