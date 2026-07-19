# Window Analysis Validation Report

**Date:** 2025-12-08
**Test Suite:** `tests/test_window_analysis.py`

## Summary

✅ **All scheduled messages are correctly analyzing the intended time windows.**

## Test Results

### 1. Daily Notification (Runs at 16:00) ✅

**Purpose:** Analyze tonight's charging window and send recommendation

**Validation:**

- ✅ Fetches 24 hours of price data starting from 16:00
- ✅ Finds optimal window 6 hours ahead (22:00-02:00)
- ✅ Window overlaps with cheap overnight period (22:00-06:00)
- ✅ Rating: EXCELLENT
- ✅ Provides cost (£3.26 for 30kWh) and carbon data (135 gCO2/kWh)

**Key Finding:** The daily notification correctly analyzes tonight's charging window, not just the next few hours. At 16:00, it identifies the optimal window starting at 22:00 (6 hours later), which is perfect for overnight charging.

---

### 2. Charge Reminder (Runs at 20:00) ✅

**Purpose:** Remind user of today's recommendation

**Validation:**

- ✅ Reads stored recommendation from daily_notification
- ✅ Does NOT re-analyze data
- ✅ Only sends if rating was EXCELLENT or GOOD
- ✅ Provides window times (23:00-03:00) and action prompt

**Key Finding:** The charge reminder correctly references the recommendation created at 16:00, reminding users to plug in before bed if there's a good opportunity tonight.

---

### 3. Weekly Forecast (Runs Monday 07:00) ✅

**Purpose:** Provide 7-day forward-looking forecast

**Validation:**

- ✅ Fetches 7-day forecast from Guy Lipman API
- ✅ Analyzes next 7 days (2025-12-08 to 2025-12-14)
- ✅ Identifies best days (EXCELLENT/GOOD ratings)
- ✅ Identifies days to avoid (POOR ratings)
- ✅ Provides weekly cost estimate

**Key Finding:** The weekly forecast correctly looks forward 7 days, helping users plan their charging schedule for the week ahead.

---

### 4. Weekly Summary (Runs Sunday 18:00) ✅

**Purpose:** Analyze past 7 days of performance

**Validation:**

- ✅ Analyzes past 7 days (2025-12-01 to 2025-12-08)
- ✅ Compares recommendations vs user actions
- ✅ Calculates adherence rate (83%)
- ✅ Shows total savings (£8.50)
- ✅ Provides performance feedback

**Key Finding:** The weekly summary correctly looks backward 7 days, providing users with insights on their charging behavior and cost savings.

---

## Scheduling Configuration

| Script | Schedule | Purpose | Window Analyzed |
|--------|----------|---------|-----------------|
| `daily_notification.py` | Daily 16:00 | Next-day recommendation | Tonight (22:00+) |
| `charge_reminder.py` | Daily 20:00 | Evening reminder | Today's stored rec |
| `weekly_forecast.py` | Monday 07:00 | Week planning | Next 7 days |
| `weekly_summary.py` | Sunday 18:00 | Performance review | Past 7 days |

## Window Analysis Logic

The key to correct window analysis is in the **daily_notification.py** script:

1. **At 16:00:** Script runs
2. **Fetches:** 24 hours of price data (16:00 today → 16:00 tomorrow)
3. **Analyzes:** All available windows within that 24-hour period
4. **Finds:** Optimal 4-hour window (typically 22:00-02:00)
5. **Stores:** Recommendation for later retrieval by charge_reminder

### Example Timeline (for 16:00 run)

```yaml
16:00 ─────────────────────────────────────────────── 16:00 (next day)
  │                                                         │
  │        Data Range Available                            │
  │                                                         │
  │              22:00 ───────── 02:00                     │
  │                │    Window   │                         │
  │                └─────────────┘                         │
  │              Optimal 4-hour window                     │
  │              (EXCELLENT rating)                        │
  │              10.88p/kWh avg                            │
```

## Validation Methodology

The test suite creates realistic price patterns:

- **Evening (18:00-22:00):** High prices (~20p/kWh)
- **Night (22:00-06:00):** Low prices (~10p/kWh)
- **Morning (06:00-08:00):** Medium prices (~15p/kWh)
- **Day (08:00-18:00):** High prices (~18p/kWh)

This mimics real Octopus Agile behavior and ensures the analyzer correctly identifies overnight periods as optimal.

## Conclusion

✅ **All scheduled messages are working correctly:**

1. **Daily Notification (16:00)** correctly analyzes tonight's window (not just the next few hours)
2. **Charge Reminder (20:00)** correctly references today's stored recommendation
3. **Weekly Forecast (Monday 07:00)** correctly analyzes next 7 days
4. **Weekly Summary (Sunday 18:00)** correctly analyzes past 7 days

The system is functioning as designed. Users will receive:

- Timely notifications about tonight's charging opportunity
- Helpful reminders before bedtime
- Weekly planning information on Mondays
- Weekly performance summaries on Sundays

No changes needed! 🎉
