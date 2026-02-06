#!/usr/bin/env python3
"""Forecast Evolution CLI Tool

Query and display how price forecasts have evolved over time for target dates.
Shows snapshot history, savings drift, and confidence scores.

Usage:
    python forecast_evolution.py --date 2026-02-12    # Show evolution for date
    python forecast_evolution.py --list                # List all tracked dates
    python forecast_evolution.py --drifted             # Show forecasts with drift
    python forecast_evolution.py --cleanup             # Remove old data
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.forecast_evolution import ForecastEvolutionTracker


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Query forecast evolution data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python forecast_evolution.py --date 2026-02-12    # Show evolution for date
  python forecast_evolution.py --list               # List all tracked dates
  python forecast_evolution.py --drifted            # Show forecasts with drift
  python forecast_evolution.py --drifted --min 15   # Drift >= 15%
  python forecast_evolution.py --cleanup            # Remove old data
  python forecast_evolution.py --date 2026-02-12 --json  # JSON output
        """,
    )

    parser.add_argument(
        "--date",
        type=str,
        help="Target date to show evolution for (YYYY-MM-DD)",
        default=None,
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all tracked target dates",
    )

    parser.add_argument(
        "--drifted",
        action="store_true",
        help="Show forecasts with significant drift",
    )

    parser.add_argument(
        "--min",
        type=float,
        help="Minimum drift percentage for --drifted (default: 10)",
        default=10.0,
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove evolution data older than retention period",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    return parser.parse_args()


def format_date_display(date_str: str) -> str:
    """Format date string for display."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%b %d")


def display_evolution(
    tracker: ForecastEvolutionTracker, target_date: str, as_json: bool = False
) -> None:
    """Display evolution history for a target date."""
    evolution = tracker.get_evolution(target_date)

    if not evolution:
        print(f"No evolution data found for {target_date}")
        return

    if as_json:
        print(json.dumps(evolution, indent=2))
        return

    display_date = format_date_display(target_date)
    print(f"\nForecast Evolution: {display_date} ({target_date})")
    print("=" * 50)

    snapshots = evolution.get("snapshots", [])
    if not snapshots:
        print("No snapshots recorded")
        return

    print("\nSnapshot History:")
    for snap in snapshots:
        snap_date = format_date_display(snap["snapshot_date"])
        days_out = snap["days_until_target"]
        savings = snap["predicted_savings_pct"]
        confidence = snap["confidence_score"]
        source = snap["price_source"]

        source_indicator = "✅" if source == "octopus_actual" else "📊"
        print(
            f"  {snap_date} ({days_out} days out): "
            f"{savings:+.1f}% savings (confidence: {confidence}%) {source_indicator}"
        )

    # Display summary
    summary = evolution.get("evolution_summary")
    if summary:
        print("\nEvolution Summary:")
        print(f"  Initial: {summary['initial_savings_pct']:.1f}% savings")
        print(f"  Current: {summary['current_savings_pct']:.1f}% savings")
        drift = summary["savings_drift"]
        direction = summary["savings_drift_direction"]
        drift_emoji = (
            "📈"
            if direction == "improved"
            else "📉" if direction == "worsened" else "➡️"
        )
        print(f"  Drift: {drift:+.1f}% ({direction}) {drift_emoji}")

        if summary.get("price_volatility", 0) > 0:
            print(f"  Volatility: £{summary['price_volatility']:.2f}")

    # Latest snapshot details
    latest = snapshots[-1]
    print("\nLatest Forecast:")
    print(f"  Cost: £{latest['predicted_cost']:.2f}")
    print(f"  Avg Price: {latest['predicted_avg_price']:.1f}p/kWh")
    print(f"  Rating: {latest['rating']}")
    print(f"  Data Source: {latest['price_source']}")

    # Actual result if recorded
    actual = evolution.get("actual_result")
    if actual:
        print("\nActual Result:")
        print(f"  Cost: £{actual['actual_cost']:.2f}")
        print(f"  Avg Price: {actual['actual_avg_price']:.1f}p/kWh")


def display_list(tracker: ForecastEvolutionTracker, as_json: bool = False) -> None:
    """Display all tracked target dates."""
    dates = tracker.get_all_tracked_dates()

    if as_json:
        print(json.dumps({"tracked_dates": dates}, indent=2))
        return

    if not dates:
        print("No forecasts being tracked")
        return

    print("\nTracked Target Dates:")
    print("=" * 50)

    for target_date in sorted(dates):
        evolution = tracker.get_evolution(target_date)
        if not evolution:
            continue

        snapshots = evolution.get("snapshots", [])
        summary = evolution.get("evolution_summary")

        display_date = format_date_display(target_date)
        num_snapshots = len(snapshots)

        if summary:
            drift = summary.get("savings_drift", 0)
            current = summary.get("current_savings_pct", 0)
            drift_str = f"{drift:+.1f}%"
            if abs(drift) >= 10:
                drift_str += " ⚠️"
        else:
            current = 0
            drift_str = "N/A"

        print(
            f"  {display_date} ({target_date}): "
            f"{current:.1f}% savings, drift: {drift_str}, "
            f"{num_snapshots} snapshots"
        )


def display_drifted(
    tracker: ForecastEvolutionTracker, min_drift: float, as_json: bool = False
) -> None:
    """Display forecasts with significant drift."""
    drifted = tracker.get_forecasts_with_drift(min_drift)

    if as_json:
        print(json.dumps({"drifted_forecasts": drifted}, indent=2))
        return

    if not drifted:
        print(f"No forecasts with drift >= {min_drift}%")
        return

    print(f"\nForecasts with Significant Drift (>= {min_drift}%):")
    print("=" * 50)

    for item in drifted:
        target_date = item["target_date"]
        display_date = format_date_display(target_date)
        initial = item["initial_savings_pct"]
        current = item["current_savings_pct"]
        drift = item["savings_drift"]
        num_snapshots = item["num_snapshots"]

        direction = "📈" if drift > 0 else "📉"
        print(f"\n  {display_date} ({target_date}):")
        print(f"    Initial: {initial:.1f}% → Current: {current:.1f}%")
        print(f"    Drift: {drift:+.1f}% {direction}")
        print(f"    Snapshots: {num_snapshots}")


def run_cleanup(tracker: ForecastEvolutionTracker) -> None:
    """Run cleanup to remove old data."""
    removed = tracker.cleanup_old_data()
    print(f"Cleaned up {removed} old forecast evolution entries")


def main():
    """Main execution function."""
    args = parse_args()

    tracker = ForecastEvolutionTracker()

    if args.cleanup:
        run_cleanup(tracker)
        return 0

    if args.date:
        display_evolution(tracker, args.date, as_json=args.json)
    elif args.drifted:
        display_drifted(tracker, args.min, as_json=args.json)
    elif args.list:
        display_list(tracker, as_json=args.json)
    else:
        # Default: show list
        display_list(tracker, as_json=args.json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
