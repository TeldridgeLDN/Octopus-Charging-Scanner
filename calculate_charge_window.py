#!/usr/bin/env python3
"""Calculate optimal charging window for specific battery target"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from modules.analyzer import Analyzer, PriceSlot, CarbonSlot
from modules.octopus_api import OctopusAPIClient

# BMW iX1 xLine specs
BATTERY_CAPACITY_KWH = 66.5  # Total battery capacity
USABLE_CAPACITY_KWH = 64.8  # Usable capacity

# Your charger
CHARGER_POWER_KW = 2.3  # From config.yaml

# Current state
CURRENT_SOC_PERCENT = 57
TARGET_SOC_PERCENT = 80
TARGET_TIME = "08:00"  # 8 AM tomorrow

# Octopus region
REGION = "H"


def main():
    print("=" * 80)
    print("BMW iX1 CHARGING WINDOW CALCULATOR")
    print("=" * 80)

    # Calculate energy needed
    current_kwh = (CURRENT_SOC_PERCENT / 100) * USABLE_CAPACITY_KWH
    target_kwh = (TARGET_SOC_PERCENT / 100) * USABLE_CAPACITY_KWH
    energy_needed = target_kwh - current_kwh

    print("\n📊 Battery Analysis:")
    print(f"   Current: {CURRENT_SOC_PERCENT}% ({current_kwh:.1f} kWh)")
    print(f"   Target:  {TARGET_SOC_PERCENT}% ({target_kwh:.1f} kWh)")
    print(f"   Energy needed: {energy_needed:.1f} kWh")

    # Calculate charging time at 2.3kW
    # Account for ~10% charging losses
    charging_efficiency = 0.90
    charge_duration_hours = energy_needed / (CHARGER_POWER_KW * charging_efficiency)

    print("\n⚡ Charging Requirements:")
    print(f"   Charger power: {CHARGER_POWER_KW} kW")
    print(f"   Time needed: {charge_duration_hours:.1f} hours")
    print("   (Accounting for ~10% charging losses)")

    # Parse target time
    uk_tz = ZoneInfo("Europe/London")
    now = datetime.now(uk_tz)
    tomorrow = now + timedelta(days=1)
    target_time = tomorrow.replace(
        hour=int(TARGET_TIME.split(":")[0]),
        minute=int(TARGET_TIME.split(":")[1]),
        second=0,
        microsecond=0,
    )

    print(f"\n🎯 Target: {target_time.strftime('%A %d %B, %I:%M %p')}")

    # Latest possible start time
    latest_start = target_time - timedelta(hours=charge_duration_hours)
    print(f"   Latest start: {latest_start.strftime('%I:%M %p')} (to finish by 8 AM)")

    # Fetch prices
    print("\n📊 Fetching Octopus Energy Prices...")
    octopus = OctopusAPIClient()

    try:
        prices = octopus.get_prices(region=REGION, hours=48)
        print(f"✅ Retrieved {len(prices)} price slots")

        # Convert to PriceSlot objects
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

        # Filter to only slots before target time
        available_slots = [s for s in price_slots if s.time < target_time]
        print(
            f"   Available slots before {target_time.strftime('%I:%M %p')}: {len(available_slots)}"
        )

    except Exception as e:
        print(f"❌ Failed to fetch prices: {e}")
        return 1

    # Create mock carbon data
    carbon_slots = [
        CarbonSlot(time=slot.time, intensity=150) for slot in available_slots
    ]

    # Find optimal window
    print(f"\n🔍 Finding cheapest {charge_duration_hours:.1f}h window...")
    analyzer = Analyzer()

    try:
        window = analyzer.find_optimal_window(
            price_slots=available_slots,
            carbon_slots=carbon_slots,
            charge_duration_hours=charge_duration_hours,
        )

        print("\n" + "=" * 80)
        print("⚡ RECOMMENDED CHARGING WINDOW")
        print("=" * 80)
        print(f"🕐 Start:  {window.start.strftime('%A %d %B, %I:%M %p')}")
        print(f"🕐 End:    {window.end.strftime('%A %d %B, %I:%M %p')}")
        print(f"💰 Cost:   £{window.total_cost:.2f} for {energy_needed:.1f}kWh")
        print(f"📊 Price:  {window.avg_price:.1f}p/kWh (average)")
        print(f"⭐ Rating: {window.rating.value}")
        print(f"📈 Score:  {window.opportunity_score:.1f}/100")

        # Check if it finishes on time
        if window.end <= target_time:
            margin = target_time - window.end
            print(
                f"✅ Finishes {margin.total_seconds()/3600:.1f}h BEFORE your 8 AM target"
            )
        else:
            overrun = window.end - target_time
            print(
                f"⚠️  Warning: Finishes {overrun.total_seconds()/3600:.1f}h AFTER 8 AM"
            )

        # Show price comparison for tonight vs early morning
        print("\n" + "=" * 80)
        print("💡 COST COMPARISON")
        print("=" * 80)

        # Tonight (9 PM start)
        tonight_start = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if tonight_start < now:
            tonight_start += timedelta(days=1)

        tonight_slots = [
            s
            for s in available_slots
            if tonight_start
            <= s.time
            < tonight_start + timedelta(hours=charge_duration_hours)
        ]

        if tonight_slots:
            tonight_avg = sum(s.price for s in tonight_slots) / len(tonight_slots)
            tonight_cost = tonight_avg * energy_needed / 100
            print("Starting at 9 PM tonight:")
            print(f"   Average price: {tonight_avg:.2f}p/kWh")
            print(f"   Total cost: £{tonight_cost:.2f}")

        # Early morning (2 AM start)
        morning_start = tomorrow.replace(hour=2, minute=0, second=0, microsecond=0)
        morning_slots = [
            s
            for s in available_slots
            if morning_start
            <= s.time
            < morning_start + timedelta(hours=charge_duration_hours)
        ]

        if morning_slots:
            morning_avg = sum(s.price for s in morning_slots) / len(morning_slots)
            morning_cost = morning_avg * energy_needed / 100
            print("\nStarting at 2 AM Wednesday:")
            print(f"   Average price: {morning_avg:.2f}p/kWh")
            print(f"   Total cost: £{morning_cost:.2f}")

            if tonight_slots:
                savings = tonight_cost - morning_cost
                percent_saving = (savings / tonight_cost) * 100
                print(
                    f"\n💰 Savings by waiting: £{savings:.2f} ({percent_saving:.0f}%)"
                )

        # Optimal window comparison
        optimal_savings = (
            max(
                tonight_cost if tonight_slots else 0,
                morning_cost if morning_slots else 0,
            )
            - window.total_cost
        )
        if optimal_savings > 0:
            print(f"\n⭐ OPTIMAL window saves: £{optimal_savings:.2f} vs alternatives")

    except Exception as e:
        print(f"❌ Failed to analyze: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
