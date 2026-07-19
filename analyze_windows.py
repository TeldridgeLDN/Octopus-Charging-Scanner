#!/usr/bin/env python3
"""Detailed window analysis script to validate charging recommendations"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from modules.analyzer import Analyzer, PriceSlot, CarbonSlot
from modules.octopus_api import OctopusAPIClient

# Configuration
REGION = os.getenv("OCTOPUS_REGION", "H")
POSTCODE = os.getenv("CARBON_POSTCODE", "SW1")
CHARGE_DURATION = 4.05  # hours for 30kWh @ 7.4kW


def main():
    print("=" * 80)
    print("EV CHARGING WINDOW ANALYSIS")
    print("=" * 80)

    # Initialize APIs
    octopus = OctopusAPIClient()
    analyzer = Analyzer()

    # Fetch price data for next 48 hours
    print("\n📊 Fetching Octopus Energy Prices...")
    try:
        prices = octopus.get_prices(region=REGION, hours=48)
        print(f"✅ Retrieved {len(prices)} price slots")

        # Show price range
        prices_sorted = sorted(prices, key=lambda x: x["value_inc_vat"])
        print(
            f"💰 Price range: {prices_sorted[0]['value_inc_vat']:.3f}p to {prices_sorted[-1]['value_inc_vat']:.3f}p/kWh"
        )

    except Exception as e:
        print(f"❌ Failed to fetch prices: {e}")
        return 1

    # Convert to PriceSlot objects
    uk_tz = ZoneInfo("Europe/London")
    price_slots = [
        PriceSlot(
            time=datetime.fromisoformat(
                p["valid_from"].replace("Z", "+00:00")
            ).astimezone(uk_tz),
            price=p["value_inc_vat"],
            source="octopus",
        )
        for p in prices
    ]

    # Create mock carbon data (since API is having issues)
    print("\n🌱 Using estimated carbon intensity data...")
    carbon_slots = [
        CarbonSlot(time=slot.time, intensity=150)  # Reasonable UK average
        for slot in price_slots
    ]

    # Find optimal window
    print(f"\n🔍 Analyzing windows for {CHARGE_DURATION}h charge duration...")
    try:
        window = analyzer.find_optimal_window(
            price_slots=price_slots,
            carbon_slots=carbon_slots,
            charge_duration_hours=CHARGE_DURATION,
        )

        print("\n" + "=" * 80)
        print("⚡ OPTIMAL CHARGING WINDOW")
        print("=" * 80)
        print(f"🕐 Start:  {window.start.strftime('%A %d %B, %I:%M %p')}")
        print(f"🕐 End:    {window.end.strftime('%A %d %B, %I:%M %p')}")
        print(f"💰 Cost:   £{window.total_cost:.2f} for 30kWh")
        print(f"📊 Price:  {window.avg_price:.1f}p/kWh (average)")
        print(f"🌱 Carbon: {window.avg_carbon}g CO2/kWh")
        print(f"⭐ Rating: {window.rating.value}")
        print(f"💵 Savings: £{window.savings_vs_baseline:.2f} vs baseline")
        print(f"📈 Score:  {window.opportunity_score:.1f}/100")

    except Exception as e:
        print(f"❌ Failed to analyze: {e}")
        return 1

    # Now analyze specific time periods mentioned
    print("\n" + "=" * 80)
    print("🔬 DETAILED PERIOD ANALYSIS")
    print("=" * 80)

    # Analysis for "tonight 9pm-6am"
    print("\n📌 Period: Tonight 9 PM - Wednesday 6 AM")
    analyze_period(price_slots, "21:00", "06:00", analyzer)

    # Analysis for the suggested window (7pm-11pm)
    print("\n📌 Period: Tonight 7 PM - 11 PM")
    analyze_period_specific(price_slots, "19:00", "23:00", analyzer)

    # Show hourly breakdown
    print("\n" + "=" * 80)
    print("📊 HOURLY PRICE BREAKDOWN (Next 24 hours)")
    print("=" * 80)

    # Group by hour and show average
    now = datetime.now(uk_tz)
    for hour_offset in range(24):
        target_hour = (now + timedelta(hours=hour_offset)).replace(
            minute=0, second=0, microsecond=0
        )

        # Find slots in this hour
        hour_slots = [
            s
            for s in price_slots
            if s.time.hour == target_hour.hour and s.time.date() == target_hour.date()
        ]

        if hour_slots:
            avg_price = sum(s.price for s in hour_slots) / len(hour_slots)
            time_str = target_hour.strftime("%a %I %p")

            # Visual bar
            bar_length = int(avg_price / 2)  # Scale for display
            bar = "█" * min(bar_length, 40)

            print(f"{time_str:12} | {avg_price:6.2f}p | {bar}")

    return 0


def analyze_period(price_slots, start_hour, end_hour, analyzer):
    """Analyze a time period spanning potential multiple days"""
    uk_tz = ZoneInfo("Europe/London")
    now = datetime.now(uk_tz)

    # Parse times for tonight
    start_time = now.replace(
        hour=int(start_hour.split(":")[0]),
        minute=int(start_hour.split(":")[1]),
        second=0,
        microsecond=0,
    )

    # If start time is in past, move to tomorrow
    if start_time < now:
        start_time += timedelta(days=1)

    # Handle end time (might be next day)
    end_hour_val = int(end_hour.split(":")[0])
    if end_hour_val < int(start_hour.split(":")[0]):
        # Crosses midnight
        end_time = (start_time + timedelta(days=1)).replace(hour=end_hour_val, minute=0)
    else:
        end_time = start_time.replace(hour=end_hour_val, minute=0)

    # Find slots in this period
    period_slots = [s for s in price_slots if start_time <= s.time < end_time]

    if period_slots:
        avg_price = sum(s.price for s in period_slots) / len(period_slots)
        min_price = min(s.price for s in period_slots)
        max_price = max(s.price for s in period_slots)

        print(
            f"   Duration: {len(period_slots) * 0.5:.1f} hours ({len(period_slots)} slots)"
        )
        print(f"   Average price: {avg_price:.2f}p/kWh")
        print(f"   Price range: {min_price:.2f}p - {max_price:.2f}p/kWh")
        print(f"   Cost for 30kWh: £{(avg_price * 30 / 100):.2f}")

        # Find best 4-hour window within this period
        if len(period_slots) >= 8:  # Need at least 4 hours
            best_avg = float("inf")
            best_start = None
            for i in range(len(period_slots) - 7):
                window_slots = period_slots[i : i + 8]
                window_avg = sum(s.price for s in window_slots) / len(window_slots)
                if window_avg < best_avg:
                    best_avg = window_avg
                    best_start = window_slots[0].time

            if best_start:
                print(
                    f"   ⭐ Best 4h window: {best_start.strftime('%I:%M %p')} @ {best_avg:.2f}p/kWh"
                )
    else:
        print("   ⚠️  No data available for this period")


def analyze_period_specific(price_slots, start_hour, end_hour, analyzer):
    """Analyze specific 4-hour window"""
    uk_tz = ZoneInfo("Europe/London")
    now = datetime.now(uk_tz)

    # Parse times for tonight
    start_time = now.replace(
        hour=int(start_hour.split(":")[0]), minute=0, second=0, microsecond=0
    )

    # If start time is in past, move to tomorrow
    if start_time < now:
        start_time += timedelta(days=1)

    end_time = start_time.replace(hour=int(end_hour.split(":")[0]), minute=0)

    # Find slots in this exact 4-hour window
    period_slots = [s for s in price_slots if start_time <= s.time < end_time]

    if period_slots:
        avg_price = sum(s.price for s in period_slots) / len(period_slots)

        print(f"   Duration: {len(period_slots) * 0.5:.1f} hours")
        print(f"   Average price: {avg_price:.2f}p/kWh")
        print(f"   Cost for 30kWh: £{(avg_price * 30 / 100):.2f}")

        # Show slot-by-slot
        print("   Slot breakdown:")
        for slot in period_slots:
            print(f"      {slot.time.strftime('%I:%M %p')}: {slot.price:.3f}p/kWh")
    else:
        print("   ⚠️  No data available for this period")


if __name__ == "__main__":
    sys.exit(main())
