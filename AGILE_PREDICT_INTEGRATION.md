# agile_predict Integration — Implementation Handover

**Branch:** `feature/agile-predict-integration`
**Status:** Planning complete · Implementation not started
**Goal:** Replace Guy Lipman HTML scraper with agile_predict ML API; add forward-looking
"better day ahead" hints to daily alerts and weekly summaries.

---

## What agile_predict Is

GitHub: https://github.com/fboundy/agile_predict
Live API: https://prices.fly.dev/api/

A Django/XGBoost ML service that forecasts Octopus Agile prices up to **14 days ahead**
using National Grid ESO demand/wind/solar data + weather. Provides 30-min half-hourly
slots with **confidence intervals** (p10/p90 bands).

### Why It's Better Than Guy Lipman (Current)

| | Guy Lipman (current) | agile_predict |
|---|---|---|
| Method | HTML scraping — fragile | Clean REST JSON API |
| Horizon | 7 days | 14 days |
| Resolution | ~hourly (approximated) | 30-min native Agile slots |
| Confidence | None | `agile_low` / `agile_high` bands |
| Model | Linear regression | XGBoost (demand, wind, solar, weather) |
| Region codes | `?region=H` | `/api/H/` — **identical codes** |

### API Call

Region `H` = Southern England / London — used as the default for accurate London
pricing and weather data. Read from `config["user"]["region"]` at runtime; do not
hardcode.

```
GET https://prices.fly.dev/api/H/?days=14&high_low=true
```

No authentication. Response: JSON array with one object:

```json
[{
  "name": "Region | H 2026-03-22 16:15",
  "created_at": "2026-03-22T16:15:00Z",
  "prices": [
    {
      "date_time": "2026-03-23T00:00:00Z",
      "agile_pred": 12.5,
      "agile_low": 8.2,
      "agile_high": 18.7
    }
  ]
}]
```

All values in **pence/kWh**. `date_time` is UTC ISO 8601.

---

## User-Facing Features Being Added

### 1. Daily Notification — "Better Day Ahead" Hint

When today's window is AVERAGE or POOR, append to the Pushover alert:

> 💡 **Tomorrow looks cheaper** — forecast 10.2p/kWh (vs 16.5p today, high confidence)

or for multiple good days:

> 📅 **Better charging days ahead:** Tomorrow (10.2p), Thursday (8.9p ⭐)

Confidence indicator derived from `agile_high - agile_low` band width:

- Band < 5p/kWh → "high confidence"
- Band 5–10p/kWh → "moderate confidence"
- Band > 10p/kWh → "uncertain forecast"

### 2. Weekly Summary — "Best Days Next Week" Section

New section at the bottom of Sunday Pushover summary:

> **📅 Best forecast days next week:**
> Mon 8.2p/kWh (high confidence) ⭐
> Sat 9.1p/kWh (moderate confidence)
> Wed 11.3p/kWh

---

## Implementation Steps (in order)

### Step 1 — New API client

**Create:** `src/modules/agile_predict_api.py`

```python
# Fetches from https://prices.fly.dev/api/<region>/?days=14&high_low=true
# Returns list of PriceSlot + stores confidence band separately
# Follows same BaseAPIClient pattern as octopus_api.py
# Key method: get_forecasts(region: str) -> List[Dict]
# Output dict: {date_time, agile_pred, agile_low, agile_high}
```

Inherit from `BaseAPIClient` in `octopus_api.py` (already has retry logic).

### Step 2 — Config addition

**Edit:** `config/config.yaml` — add under `apis:`:

```yaml
  agile_predict:
    base_url: "https://prices.fly.dev"
    default_region: "H"               # H = Southern England / London — accurate pricing & weather
    days: 14
    high_low: true
    confidence_narrow_threshold: 5.0   # p/kWh band = "high confidence"
    confidence_wide_threshold: 10.0    # p/kWh band = "uncertain"
```

### Step 3 — Upgrade MultiDayPlanner fallback chain

**Edit:** `src/modules/multi_day_planner.py`

In `_get_multi_day_prices()`, change the fallback for days beyond Octopus coverage:

```
Current: Octopus actual → Guy Lipman
New:     Octopus actual → agile_predict → Guy Lipman
```

When using agile_predict data, store `price_source = "agile_predict"` on `DayComparison`.
Also store min/max confidence band per day for use in notifications.

### Step 4 — "Better day ahead" hint in daily notification

**Edit:** `src/scripts/daily_notification.py`

After `format_notification()` builds the base message, add a new helper:

```python
def build_better_day_hint(plan: MultiDayPlan, today_window: ChargingWindow, config) -> str:
    """If any future day is >15% cheaper than today, return a hint string."""
```

Append the hint to the notification message before sending.
Only show if: today's rating is AVERAGE or POOR, or savings > 20%.

### Step 5 — "Best days next week" in weekly summary

**Edit:** `src/scripts/weekly_summary.py`

Add a new section generator:

```python
def build_week_ahead_section(config) -> str:
    """Fetch 7-day agile_predict forecast, rank days by optimal window cost."""
```

Call `AgilePredict` client directly here (not via MultiDayPlanner) to keep it simple.
Append section to weekly summary message before sending.

---

## Files to Create/Edit

| File | Action | Notes |
|---|---|---|
| `src/modules/agile_predict_api.py` | **CREATE** | REST client, ~80 lines |
| `config/config.yaml` | **EDIT** | Add `apis.agile_predict` block |
| `src/modules/multi_day_planner.py` | **EDIT** | Insert agile_predict in fallback chain |
| `src/scripts/daily_notification.py` | **EDIT** | Add `build_better_day_hint()` |
| `src/scripts/weekly_summary.py` | **EDIT** | Add `build_week_ahead_section()` |
| `docs/architecture.md` | **CREATED** ✅ | Fishbone / system diagram |

---

## Key Patterns to Follow

- All API clients inherit `BaseAPIClient` from `src/modules/octopus_api.py`
- `PriceSlot(time: datetime, price: float, source: str)` — defined in `analyzer.py`
- Notifications built as HTML strings, sent via `PushoverClient.send_notification()`
- Config loaded via `yaml.safe_load()` + `os.getenv()` for secrets
- Atomic JSON writes via `DataStore._save_json()` (temp file + rename)
- All datetimes are UTC-aware (`timezone.utc`)

---

## Testing Approach

After implementing, validate by running:

```bash
# Test the new API client directly
cd /Users/tomeldridge/ev-charging-optimizer
python -c "
from src.modules.agile_predict_api import AgilePredict
client = AgilePredict()
data = client.get_forecasts('H')
print(f'Got {len(data)} slots, first: {data[0]}')
"

# Run daily notification in dry-run / log-only mode
python src/scripts/daily_notification.py
```

Check `logs/daily_notification.log` for output.

---

## What NOT to Do

- Do not remove Guy Lipman client — keep as final fallback
- Do not change `PriceSlot` dataclass signature (breaks analyzer)
- Do not send notifications during testing — check `is_exceptional` gating in main()
- Do not hardcode region — read from `config["user"]["region"]` (defaults to `H` = London)
