"""Time-of-day labelling helpers.

Converts UTC-aware datetimes to Europe/London local time and maps them to
human-friendly "part of day" labels ("morning", "afternoon", "evening",
"overnight") and phrases ("this afternoon", "Thursday overnight"). Also
provides a canonical forecast-date label helper ("Tomorrow" / weekday name).

All conversions go through Europe/London so labels stay correct across BST,
mirroring the local-time approach used in src/scripts/smart_charge_planner.py.
"""

from datetime import datetime, date
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")


def part_of_day(dt: datetime) -> str:
    """Map a UTC-aware datetime to a bare part-of-day label in London local time.

    Args:
        dt: A timezone-aware datetime (expected UTC), converted to Europe/London.

    Returns:
        One of "overnight" (23:00-04:59), "morning" (05:00-11:59),
        "afternoon" (12:00-16:59), or "evening" (17:00-22:59).
    """
    hour = dt.astimezone(LONDON_TZ).hour
    if hour >= 23 or hour < 5:
        return "overnight"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def part_of_day_phrase(dt: datetime, day_label: str | None = None) -> str:
    """Build a natural part-of-day phrase for a UTC-aware datetime.

    Args:
        dt: A timezone-aware datetime (expected UTC), converted to Europe/London.
        day_label: Optional day prefix (e.g. "Tomorrow", "Thursday"). When
            given, the phrase names that day; when None the phrase refers to
            the current day.

    Returns:
        Same-day (day_label is None): "this morning", "this afternoon",
        "this evening", or "overnight" (note: "overnight" takes no "this").
        Future day (day_label given): "{day_label} {bare}", e.g.
        "Thursday afternoon", "Tomorrow overnight".
    """
    bare = part_of_day(dt)
    if day_label is not None:
        return f"{day_label} {bare}"
    if bare == "overnight":
        return "overnight"
    return f"this {bare}"


def format_day_label(date_str: str) -> str:
    """Return a human-readable label for a forecast date.

    Args:
        date_str: ISO date string e.g. "2026-03-30".

    Returns:
        "Tomorrow" for the next day, the weekday name otherwise (e.g.
        "Thursday"), or "a future day" if the string cannot be parsed.
    """
    try:
        entry_date = date.fromisoformat(date_str)
        delta = (entry_date - date.today()).days
        if delta == 1:
            return "Tomorrow"
        return entry_date.strftime("%A")
    except ValueError:
        return "a future day"
