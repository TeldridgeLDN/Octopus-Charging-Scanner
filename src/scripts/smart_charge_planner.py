#!/usr/bin/env python3
"""Smart Charging Planner - Find optimal charging window based on current battery level

Usage:
    python src/scripts/smart_charge_planner.py --current 57 --target 80
    python src/scripts/smart_charge_planner.py --current 45 --target 70 --deadline "08:00"
    python src/scripts/smart_charge_planner.py --current 60  # Defaults to 80% target

This tool analyzes real-time Octopus Energy prices to find the cheapest charging window
that gets your BMW iX1 from current charge to target charge by your deadline.
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.octopus_api import OctopusAPIClient
from modules.analyzer import Analyzer, PriceSlot, CarbonSlot
from modules.pushover import PushoverClient
from dotenv import load_dotenv
import yaml

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Keep quiet unless there's an issue
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# BMW iX1 xLine specs
BATTERY_CAPACITY_KWH = 66.5  # Total battery capacity
USABLE_CAPACITY_KWH = 64.8  # Usable capacity (BMW limits to ~97.5%)
CHARGING_EFFICIENCY = 0.90  # Account for ~10% charging losses


def load_config() -> dict:
    """Load configuration from config.yaml"""
    config_path = Path("config/config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def calculate_charge_needed(
    current_percent: float, target_percent: float
) -> Tuple[float, float]:
    """Calculate energy needed and time required.

    Args:
        current_percent: Current battery state of charge (%)
        target_percent: Target battery state of charge (%)

    Returns:
        Tuple of (energy_needed_kwh, time_needed_hours)
    """
    current_kwh = (current_percent / 100) * USABLE_CAPACITY_KWH
    target_kwh = (target_percent / 100) * USABLE_CAPACITY_KWH
    energy_needed = target_kwh - current_kwh

    return current_kwh, target_kwh, energy_needed


def find_optimal_window(
    price_slots: List[PriceSlot],
    carbon_slots: List[CarbonSlot],
    charge_duration_hours: float,
    target_time: datetime,
    energy_needed: float,
) -> dict:
    """Find the optimal charging window.

    Args:
        price_slots: Available price data
        carbon_slots: Carbon intensity data
        charge_duration_hours: How long charging takes
        target_time: When charging must be complete by
        energy_needed: kWh to charge

    Returns:
        Dict with optimal window details and alternatives
    """
    # Filter to only slots before target time
    available_slots = [s for s in price_slots if s.time < target_time]

    if not available_slots:
        raise ValueError("No price data available before target time")

    # Use analyzer to find optimal window
    analyzer = Analyzer()
    optimal_window = analyzer.find_optimal_window(
        price_slots=available_slots,
        carbon_slots=carbon_slots,
        charge_duration_hours=charge_duration_hours,
    )

    # Calculate actual cost based on energy needed
    actual_cost = optimal_window.avg_price * energy_needed / 100

    # Find alternative windows for comparison
    uk_tz = ZoneInfo("Europe/London")
    now = datetime.now(uk_tz)

    alternatives = []

    # Alternative 1: Start now (if possible)
    if now < target_time - timedelta(hours=charge_duration_hours):
        now_slots = [
            s
            for s in available_slots
            if now <= s.time < now + timedelta(hours=charge_duration_hours)
        ]
        if len(now_slots) >= int(charge_duration_hours * 2):
            avg_price = sum(s.price for s in now_slots) / len(now_slots)
            alternatives.append(
                {
                    "name": "Start Now",
                    "start": now,
                    "avg_price": avg_price,
                    "cost": avg_price * energy_needed / 100,
                }
            )

    # Alternative 2: Start at 9 PM tonight
    tonight_9pm = now.replace(hour=21, minute=0, second=0, microsecond=0)
    if tonight_9pm < now:
        tonight_9pm += timedelta(days=1)

    if tonight_9pm < target_time - timedelta(hours=charge_duration_hours):
        evening_slots = [
            s
            for s in available_slots
            if tonight_9pm
            <= s.time
            < tonight_9pm + timedelta(hours=charge_duration_hours)
        ]
        if len(evening_slots) >= int(charge_duration_hours * 2):
            avg_price = sum(s.price for s in evening_slots) / len(evening_slots)
            alternatives.append(
                {
                    "name": "9 PM Tonight",
                    "start": tonight_9pm,
                    "avg_price": avg_price,
                    "cost": avg_price * energy_needed / 100,
                }
            )

    # Alternative 3: Start at 2 AM (super cheap period)
    tomorrow = now + timedelta(days=1)
    early_morning = tomorrow.replace(hour=2, minute=0, second=0, microsecond=0)

    if early_morning < target_time - timedelta(hours=charge_duration_hours):
        morning_slots = [
            s
            for s in available_slots
            if early_morning
            <= s.time
            < early_morning + timedelta(hours=charge_duration_hours)
        ]
        if len(morning_slots) >= int(charge_duration_hours * 2):
            avg_price = sum(s.price for s in morning_slots) / len(morning_slots)
            alternatives.append(
                {
                    "name": "2 AM Tomorrow",
                    "start": early_morning,
                    "avg_price": avg_price,
                    "cost": avg_price * energy_needed / 100,
                }
            )

    return {
        "optimal": {
            "window": optimal_window,
            "cost": actual_cost,
            "energy": energy_needed,
        },
        "alternatives": alternatives,
        "target_time": target_time,
        "charge_duration": charge_duration_hours,
    }


def format_pushover_notification(
    result: dict, current_percent: float, target_percent: float
) -> tuple[str, str]:
    """Format results as a Pushover notification.

    Args:
        result: Analysis results with optimal window and alternatives
        current_percent: Current battery percentage
        target_percent: Target battery percentage

    Returns:
        Tuple of (title, message) for Pushover notification
    """
    optimal = result["optimal"]
    window = optimal["window"]
    alternatives = result["alternatives"]

    # Find best option (cheapest)
    best_option = None
    if alternatives:
        all_options = [
            {"name": "Recommended", "cost": optimal["cost"], "start": window.start}
        ] + alternatives
        best_option = min(all_options, key=lambda x: x["cost"])
    else:
        best_option = {
            "name": "Recommended",
            "cost": optimal["cost"],
            "start": window.start,
        }

    # Title
    title = f"🔋 {current_percent}%→{target_percent}% (£{best_option['cost']:.2f})"

    # Message body
    lines = []

    # Best recommendation
    start_time = best_option["start"]
    lines.append(f"👉 Plug in at {start_time.strftime('%I:%M %p')}")
    lines.append(f"⏱️  {result['charge_duration']:.1f}h charge time")
    lines.append("")

    # Cost breakdown
    lines.append(f"💰 Cost: £{best_option['cost']:.2f}")
    lines.append(f"📊 Rate: {window.avg_price:.1f}p/kWh avg")
    lines.append(f"⚡ Energy: {optimal['energy']:.1f} kWh")
    lines.append("")

    # Deadline info
    target_time = result["target_time"]
    lines.append(f"🎯 Ready by {target_time.strftime('%I:%M %p %a')}")

    # Savings vs alternatives
    if alternatives and best_option["name"] != "Recommended":
        savings = optimal["cost"] - best_option["cost"]
        lines.append("")
        lines.append(f"💵 Saves £{savings:.2f} vs {window.start.strftime('%I:%M %p')}")

    # Show if there are cheaper alternatives (even if not recommended due to timing)
    if alternatives:
        alternatives_sorted = sorted(alternatives, key=lambda x: x["cost"])
        cheapest = alternatives_sorted[0]
        if cheapest["cost"] < best_option["cost"]:
            lines.append("")
            lines.append(
                f"ℹ️  {cheapest['start'].strftime('%I:%M %p')} is £{best_option['cost'] - cheapest['cost']:.2f} cheaper"
            )

    message = "\n".join(lines)

    return title, message


def format_output(result: dict, current_percent: float, target_percent: float):
    """Format and print the results in a user-friendly way."""
    optimal = result["optimal"]
    window = optimal["window"]
    alternatives = result["alternatives"]

    print("=" * 80)
    print("🔋 BMW iX1 SMART CHARGING PLAN")
    print("=" * 80)

    # Battery status
    print("\n📊 Battery:")
    print(f"   Current: {current_percent}%")
    print(f"   Target:  {target_percent}%")
    print(f"   Energy needed: {optimal['energy']:.1f} kWh")
    print(f"   Charging time: {result['charge_duration']:.1f} hours")

    # Target deadline
    target_time = result["target_time"]
    print(f"\n🎯 Deadline: {target_time.strftime('%A %d %B, %I:%M %p')}")

    latest_start = target_time - timedelta(hours=result["charge_duration"])
    print(f"   Latest start: {latest_start.strftime('%I:%M %p')}")

    # Optimal window
    print("\n" + "=" * 80)
    print("⚡ RECOMMENDED CHARGING WINDOW")
    print("=" * 80)
    print(f"🕐 Start:  {window.start.strftime('%A %I:%M %p')}")
    print(f"🕐 End:    {window.end.strftime('%A %I:%M %p')}")
    print(f"💰 Cost:   £{optimal['cost']:.2f}")
    print(f"📊 Rate:   {window.avg_price:.1f}p/kWh (average)")
    print(f"⭐ Rating: {window.rating.value}")

    # Check if finishes on time
    if window.end <= target_time:
        margin = target_time - window.end
        hours = margin.total_seconds() / 3600
        print(f"✅ Finishes {hours:.1f}h before deadline")
    else:
        overrun = window.end - target_time
        hours = overrun.total_seconds() / 3600
        print(f"⚠️  Finishes {hours:.1f}h AFTER deadline")

    # Show alternatives if available
    if alternatives:
        print("\n" + "=" * 80)
        print("💡 ALTERNATIVE OPTIONS")
        print("=" * 80)

        # Sort by cost
        alternatives_sorted = sorted(alternatives, key=lambda x: x["cost"])

        for alt in alternatives_sorted:
            print(f"\n{alt['name']}:")
            print(f"   Start: {alt['start'].strftime('%A %I:%M %p')}")
            print(f"   Rate:  {alt['avg_price']:.2f}p/kWh")
            print(f"   Cost:  £{alt['cost']:.2f}")

            # Compare to optimal
            savings = optimal["cost"] - alt["cost"]
            if savings > 0:
                print(f"   📉 £{abs(savings):.2f} CHEAPER than recommended")
            elif savings < 0:
                print(f"   📈 £{abs(savings):.2f} more expensive")
            else:
                print("   ≈ Same cost as recommended")

        # Show best alternative
        cheapest = alternatives_sorted[0]
        if cheapest["cost"] < optimal["cost"]:
            savings = optimal["cost"] - cheapest["cost"]
            print(
                f"\n💰 Best deal: {cheapest['name']} saves £{savings:.2f} vs recommended window"
            )

    print("\n" + "=" * 80)
    print("✅ READY TO CHARGE")
    print("=" * 80)

    # Provide action recommendation
    best_option = None
    if alternatives:
        all_options = [
            {"name": "Recommended", "cost": optimal["cost"], "start": window.start}
        ] + alternatives
        best_option = min(all_options, key=lambda x: x["cost"])

        if best_option["name"] == "Recommended":
            print(f"👉 Plug in at {window.start.strftime('%I:%M %p')}")
        else:
            start = best_option["start"]
            print(f"👉 Best value: Plug in at {start.strftime('%I:%M %p')}")
            print(
                f"   (Saves £{optimal['cost'] - best_option['cost']:.2f} vs other options)"
            )
    else:
        print(f"👉 Plug in at {window.start.strftime('%I:%M %p')}")

    print(
        f"\n💵 Total cost: £{best_option['cost'] if best_option else optimal['cost']:.2f}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Find optimal EV charging window based on current battery level",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/scripts/smart_charge_planner.py --current 57 --target 80
  python src/scripts/smart_charge_planner.py --current 45 --target 70 --deadline "08:00"
  python src/scripts/smart_charge_planner.py --current 60  # Defaults to 80% target
        """,
    )

    parser.add_argument(
        "--current",
        "-c",
        type=float,
        required=True,
        help="Current battery percentage (0-100)",
    )

    parser.add_argument(
        "--target",
        "-t",
        type=float,
        default=80,
        help="Target battery percentage (default: 80)",
    )

    parser.add_argument(
        "--deadline",
        "-d",
        type=str,
        default="08:00",
        help='Deadline time in HH:MM format (default: "08:00")',
    )

    parser.add_argument(
        "--region", "-r", type=str, help="Octopus region (default: from config)"
    )

    parser.add_argument(
        "--notify",
        "-n",
        action="store_true",
        help="Send Pushover notification with charging plan",
    )

    args = parser.parse_args()

    # Validation
    if not 0 <= args.current <= 100:
        print("❌ Error: Current battery must be between 0 and 100%")
        return 1

    if not 0 <= args.target <= 100:
        print("❌ Error: Target battery must be between 0 and 100%")
        return 1

    if args.current >= args.target:
        print("❌ Error: Target must be higher than current charge level")
        return 1

    # Load config
    config = load_config()
    region = args.region or config["user"]["region"]
    charger_power_kw = config["user"]["charging_rate_kw"]

    # Calculate charging requirements
    current_kwh, target_kwh, energy_needed = calculate_charge_needed(
        args.current, args.target
    )

    charge_duration_hours = energy_needed / (charger_power_kw * CHARGING_EFFICIENCY)

    # Parse deadline
    uk_tz = ZoneInfo("Europe/London")
    now = datetime.now(uk_tz)
    tomorrow = now + timedelta(days=1)

    try:
        deadline_hour, deadline_minute = map(int, args.deadline.split(":"))
        target_time = tomorrow.replace(
            hour=deadline_hour, minute=deadline_minute, second=0, microsecond=0
        )
    except ValueError:
        print(f'❌ Error: Invalid deadline format "{args.deadline}". Use HH:MM format.')
        return 1

    # Check if deadline is achievable
    if charge_duration_hours > 24:
        print(
            f"❌ Error: Charging requires {charge_duration_hours:.1f} hours, which is too long"
        )
        print(
            f"   Consider using a faster charger or reducing target to {args.current + (24 * charger_power_kw * CHARGING_EFFICIENCY / USABLE_CAPACITY_KWH * 100):.0f}%"
        )
        return 1

    # Fetch prices
    try:
        octopus = OctopusAPIClient()
        prices = octopus.get_prices(region=region, hours=48)

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

        # Create carbon slots (use estimated value)
        carbon_slots = [
            CarbonSlot(time=slot.time, intensity=150) for slot in price_slots
        ]

    except Exception as e:
        print(f"❌ Error fetching prices: {e}")
        logger.exception("Failed to fetch prices")
        return 1

    # Find optimal window
    try:
        result = find_optimal_window(
            price_slots=price_slots,
            carbon_slots=carbon_slots,
            charge_duration_hours=charge_duration_hours,
            target_time=target_time,
            energy_needed=energy_needed,
        )

        # Display results
        format_output(result, args.current, args.target)

        # Send Pushover notification if requested
        if args.notify:
            try:
                load_dotenv()
                pushover = PushoverClient(
                    user_key=os.getenv("PUSHOVER_USER"),
                    api_token=os.getenv("PUSHOVER_API_TOKEN"),
                )

                title, message = format_pushover_notification(
                    result, args.current, args.target
                )

                pushover.send_notification(
                    message=message,
                    title=title,
                    priority=0,  # Normal priority
                    sound="cosmic",  # Pleasant notification sound
                )

                print("\n✅ Pushover notification sent!")

            except Exception as e:
                print(f"\n⚠️  Failed to send notification: {e}")
                logger.exception("Failed to send Pushover notification")
                # Don't fail the whole script if notification fails
                return 0

    except Exception as e:
        print(f"❌ Error finding optimal window: {e}")
        logger.exception("Failed to find optimal window")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
