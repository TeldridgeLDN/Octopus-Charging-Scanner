#!/usr/bin/env python3
"""ACIX Session Detection Script

Processes usage data to detect EV charging sessions and stores them.
Runs after fetch_usage.py as part of the ACIX detection pipeline.

Part of the ACIX (Adaptive Charging Intelligence Extension) system.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any
import logging
import argparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ev_detector import EVDetector
from modules.data_store import DataStore
import yaml
from dotenv import load_dotenv

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "acix_detect_sessions.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml and .env

    Returns:
        Configuration dictionary
    """
    load_dotenv()

    config_path = Path("config/config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config


def detect_and_store_sessions(
    days: int = 7, min_confidence: int = 60
) -> Dict[str, Any]:
    """Detect EV charging sessions and store them.

    Args:
        days: Number of days of usage data to analyze
        min_confidence: Minimum confidence score to save a session

    Returns:
        Summary of detection results
    """
    logger.info(f"Starting session detection for last {days} days")

    # Load config
    config = load_config()
    acix_config = config.get("acix", {})

    # Initialize components
    data_store = DataStore()

    detector = EVDetector(
        power_threshold_kw=acix_config.get("ev_power_threshold_kw", 2.3),
        min_intervals=acix_config.get("min_charging_intervals", 2),
        baseline_power_kw=0.5,  # Typical household baseline
    )

    # Get usage data
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    usage_data = data_store.get_usage(start=start_time, end=end_time)

    if not usage_data:
        logger.warning("No usage data available for detection")
        return {
            "success": True,
            "sessions_detected": 0,
            "sessions_saved": 0,
            "message": "No usage data available",
        }

    logger.info(f"Analyzing {len(usage_data)} usage records")

    # Detect sessions
    sessions = detector.detect_sessions(usage_data)

    # Get existing sessions to avoid duplicates
    existing_sessions = data_store.get_sessions(days=days)
    existing_starts = {s.get("start") for s in existing_sessions}

    # Filter and save new sessions
    sessions_saved = 0
    for session in sessions:
        if session.confidence < min_confidence:
            logger.debug(f"Skipping low-confidence session: {session.confidence}%")
            continue

        session_dict = session.to_dict()

        # Check for duplicates (same start time)
        if session_dict["start"] in existing_starts:
            logger.debug(f"Session already exists: {session_dict['start']}")
            continue

        # Save event
        data_store.save_event(session_dict)

        # Save session summary
        session_summary = {
            "date": session.start.strftime("%Y-%m-%d"),
            "plug_in_time": None,  # Will be detected in Phase 2
            "charge_start": session_dict["start"],
            "charge_end": session_dict["end"],
            "total_kwh": session_dict["total_kwh"],
            "avg_power_kw": session_dict["avg_power_kw"],
            "duration_hours": session_dict["duration_hours"],
            "confidence": session_dict["confidence"],
        }
        data_store.save_session(session_summary)
        sessions_saved += 1

        logger.info(
            f"Saved session: {session_dict['start']} - "
            f"{session_dict['total_kwh']:.1f}kWh @ {session_dict['confidence']}% confidence"
        )

    # Generate summary
    summary = detector.get_session_summary(sessions)

    result = {
        "success": True,
        "usage_records_analyzed": len(usage_data),
        "sessions_detected": len(sessions),
        "sessions_saved": sessions_saved,
        "sessions_skipped_low_confidence": len(sessions) - sessions_saved,
        "total_kwh_detected": summary["total_kwh"],
        "avg_confidence": summary["avg_confidence"],
    }

    logger.info(
        f"Detection complete: {len(sessions)} detected, " f"{sessions_saved} saved"
    )

    return result


def show_recent_sessions(days: int = 7) -> None:
    """Display recently detected sessions.

    Args:
        days: Number of days to show
    """
    data_store = DataStore()
    sessions = data_store.get_sessions(days=days)

    if not sessions:
        print("No sessions detected in the last", days, "days")
        return

    print(f"\n{'='*60}")
    print(f"EV Charging Sessions (last {days} days)")
    print(f"{'='*60}")

    for s in sorted(sessions, key=lambda x: x.get("charge_start", ""), reverse=True):
        date = s.get("date", "Unknown")
        start = s.get("charge_start", "")
        end = s.get("charge_end", "")
        kwh = s.get("total_kwh", 0)
        power = s.get("avg_power_kw", 0)
        duration = s.get("duration_hours", 0)
        confidence = s.get("confidence", 0)

        print(f"\n{date}:")
        print(f"  Time: {start} to {end}")
        print(f"  Duration: {duration:.1f}h | Energy: {kwh:.1f} kWh")
        print(f"  Avg Power: {power:.2f} kW | Confidence: {confidence}%")

    print(f"\n{'='*60}")
    print(f"Total sessions: {len(sessions)}")
    total_kwh = sum(s.get("total_kwh", 0) for s in sessions)
    print(f"Total energy: {total_kwh:.1f} kWh")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect EV charging sessions from usage data"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)",
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=60,
        help="Minimum confidence to save session (default: 60)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show recent sessions without running detection",
    )

    args = parser.parse_args()

    # Load config to check if ACIX is enabled
    config = load_config()
    acix_config = config.get("acix", {})

    if not acix_config.get("enabled", False):
        logger.info("ACIX is disabled in config, exiting")
        print("ACIX is disabled. Enable it in config/config.yaml")
        return

    if args.show:
        show_recent_sessions(args.days)
        return

    # Run detection
    result = detect_and_store_sessions(
        days=args.days,
        min_confidence=args.min_confidence,
    )

    if result["success"]:
        print(f"Analyzed {result['usage_records_analyzed']} usage records")
        print(f"Detected {result['sessions_detected']} session(s)")
        print(f"Saved {result['sessions_saved']} new session(s)")
        if result["sessions_detected"] > 0:
            print(f"Total energy: {result['total_kwh_detected']:.1f} kWh")
            print(f"Average confidence: {result['avg_confidence']:.0f}%")
    else:
        print(f"Detection failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
