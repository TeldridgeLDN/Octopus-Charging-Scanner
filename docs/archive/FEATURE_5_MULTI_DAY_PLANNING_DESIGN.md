# Feature #5: Multi-Day Planning Mode - Design Document

**Status**: Design Phase
**Estimated Effort**: 8-10 hours
**Priority**: Medium Complexity, High Value

---

## Overview

Multi-Day Planning Mode enables users to optimize charging decisions across multiple days by comparing prices for today, tomorrow, and the day after. The system considers battery level, estimated drain rate, and price forecasts to recommend the optimal charging day.

---

## User Story

> "As an EV owner with flexible charging needs, I want to compare prices for the next 3 days so I can defer charging to save money when prices are expected to drop."

**Example Scenario**:

- Monday evening: Prices are 18p/kWh (AVERAGE)
- Tuesday forecast: 8p/kWh (EXCELLENT)
- Wednesday forecast: 15p/kWh (GOOD)
- Battery: 45% remaining (~90 miles range)
- Recommendation: **DEFER to Tuesday** - save £2.00 by waiting

---

## Architecture

### Component Structure (Simplified - No Battery Tracking)

```
Multi-Day Planning System
├── Multi-Day Planner Module (NEW)
│   ├── Fetch 3-day price data (actual + forecast)
│   ├── Calculate cost for each day
│   ├── Calculate savings potential
│   └── Identify best day
│
└── Planning Script (NEW)
    ├── On-demand or scheduled execution
    ├── Format 3-day comparison
    └── Send planning notification
```

**Key Simplification**: No battery tracking needed! User decides based on their own battery knowledge and the price comparison we provide.

---

## Data Model

### Multi-Day Plan Schema

**New Data File**: `data/multi_day_plans.json`

```json
{
  "timestamp": "2025-12-09T16:00:00+00:00",
  "days": [
    {
      "date": "2025-12-09",
      "day_name": "Today",
      "avg_price": 18.2,
      "optimal_window": {
        "start": "22:00",
        "end": "02:00"
      },
      "cost_30kwh": 5.46,
      "rating": "AVERAGE",
      "price_source": "octopus_actual"
    },
    {
      "date": "2025-12-10",
      "day_name": "Tomorrow",
      "avg_price": 8.5,
      "optimal_window": {
        "start": "23:00",
        "end": "03:00"
      },
      "cost_30kwh": 2.55,
      "rating": "EXCELLENT",
      "price_source": "octopus_actual",
      "savings_vs_today": 2.91
    },
    {
      "date": "2025-12-11",
      "day_name": "Day After",
      "avg_price": 15.0,
      "optimal_window": {
        "start": "22:30",
        "end": "02:30"
      },
      "cost_30kwh": 4.50,
      "rating": "GOOD",
      "price_source": "forecast",
      "savings_vs_today": 0.96
    }
  ],
  "best_day": {
    "date": "2025-12-10",
    "reason": "Excellent prices - 53% cheaper than today",
    "savings": 2.91
  }
}
```

---

## Core Algorithms

### 1. Three-Day Price Comparison

**Input**: Price data for 3 days, typical kWh
**Output**: Cost comparison for each day

```python
def compare_three_days(
    kwh_to_charge: float = 30.0
) -> List[DayComparison]:
    """
    Compare charging cost for next 3 days.

    For each day:

    1. Fetch price data (actual or forecast)
    2. Find optimal charging window
    3. Calculate cost
    4. Calculate savings vs charging today
    5. Track price source for transparency

    """
```

### 2. Best Day Identification

**Simple Logic**: Find the cheapest day

```python
def identify_best_day(days: List[DayComparison]) -> Dict:
    """
    Identify the best day to charge based purely on price.

    Logic:

    1. Sort days by cost (cheapest first)
    2. Best day = lowest cost
    3. Calculate savings vs today
    4. Calculate percentage savings
    5. Note data source reliability

    No complex risk assessment - user knows their battery state!
    """
```

---

## Implementation Steps

### Phase 1: Multi-Day Planner Module (3 hours)

**New File**: `src/modules/multi_day_planner.py` (~200 lines)

**Classes**:
```python
@dataclass
class DayComparison:
    date: str
    day_name: str  # "Today", "Tomorrow", "Day After"
    avg_price: float
    optimal_window: ChargingWindow
    cost: float
    rating: OpportunityRating
    price_source: str  # "octopus_actual" or "forecast"
    savings_vs_today: float

@dataclass
class MultiDayPlan:
    timestamp: datetime
    days: List[DayComparison]
    best_day: Dict[str, Any]  # {date, reason, savings}

class MultiDayPlanner:
    def __init__(self, config, analyzer, data_store)
    def get_three_day_prices() -> List[Tuple[date, prices, source]]
    def compare_days() -> List[DayComparison]
    def identify_best_day(comparisons) -> Dict
    def generate_plan() -> MultiDayPlan
```

**Testing**:

- Test 3-day price fetching (actual + forecast)
- Test day comparison logic
- Test best day identification
- Test with various price scenarios

---

### Phase 2: Planning Script (2 hours)

**New File**: `src/scripts/multi_day_planning.py` (~150 lines)

**Features**:

- CLI parameters: `--dry-run`, `--kwh`
- Generate 3-day comparison
- Format rich notification
- Save plan to data store

**Notification Format** (Simplified):
```
📅 3-Day Charging Plan (30kWh)

💰 Price Comparison:
┌─────────────────────────────────┐
│ Today (Mon Dec 9)               │
│ ⚡ Window: 22:00 - 02:00        │
│ 💵 Cost: £5.46 (18.2p/kWh)      │
│ ⭐ Rating: AVERAGE               │
│ 📊 Data: Actual prices ✅       │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ ✨ Tomorrow (Tue Dec 10)        │
│ ⚡ Window: 23:00 - 03:00        │
│ 💵 Cost: £2.55 (8.5p/kWh)       │
│ ⭐ Rating: EXCELLENT! ⚡         │
│ 💚 Save: £2.91 (53% cheaper)    │
│ 📊 Data: Actual prices ✅       │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ Day After (Wed Dec 11)          │
│ ⚡ Window: 22:30 - 02:30        │
│ 💵 Cost: £4.50 (15.0p/kWh)      │
│ ⭐ Rating: GOOD                  │
│ 💚 Save: £0.96 (18% cheaper)    │
│ 📊 Data: Forecast (predicted)   │
└─────────────────────────────────┘

🎯 BEST DAY: TOMORROW (Tue Dec 10)
💰 Savings: £2.91 vs today (53% cheaper)
✨ Excellent pricing opportunity!

💡 Decision is yours - you know your battery!
```

---

### Phase 3: Testing (1.5 hours)

**New Test File**: `tests/test_multi_day_planner.py`

**Test Scenarios**:

1. ✅ Three-day price fetching (actual + forecast)
2. ✅ Day comparison logic
3. ✅ Best day identification (cheapest wins)
4. ✅ Savings calculation
5. ✅ Edge case: Negative pricing on day 2
6. ✅ Edge case: All days have similar prices
7. ✅ Edge case: Tomorrow much more expensive
8. ✅ Data source tracking (actual vs forecast)

---

### Phase 4: Documentation (0.5 hours)

**New File**: `FEATURE_5_MULTI_DAY_PLANNING.md`

**Contents**:

- Feature overview
- How it works
- Usage examples
- Configuration options
- Decision algorithm explanation
- Risk assessment guide

---

## Configuration

**No new configuration needed!** Uses existing config for:

- `user.typical_charge_kwh` - charge amount
- `user.charging_rate_kw` - charging rate
- Thresholds for rating classification

---

## Usage Patterns

### On-Demand Planning

```bash
# User manually requests 3-day plan
python src/scripts/multi_day_planning.py

# With custom kWh amount
python src/scripts/multi_day_planning.py --kwh 40

# Dry run (no notification, just display)
python src/scripts/multi_day_planning.py --dry-run
```

### Scheduled Planning (Optional - Future)

Could add to launchd for automatic comparison, but for MVP it's better as on-demand tool.

---

## Design Philosophy

### Simple Information Display
- **No prescriptive recommendations** - just show the data
- User knows their battery state better than we do
- Present clear cost comparison
- Label data sources (actual vs forecast)
- Let user make informed decision

### Trust the User
- Don't try to be too smart with complex risk models
- Users are intelligent and can assess their own situation
- Just give them the price data cleanly formatted

---

## Success Metrics

**Feature is successful if**:

1. ✅ Users run the comparison tool regularly
2. ✅ Clear, easy-to-understand output
3. ✅ Accurate price data (actual when available)
4. ✅ Helps users make informed deferral decisions

---

## Future Enhancements

### V2 Features (Not in MVP)
- **Battery tracking**: Optional battery level tracking for smarter insights
- **Smart charging reminders**: Auto-alert when prices drop significantly
- **Weather integration**: Show weather impact on range
- **Calendar integration**: Consider upcoming trips

---

## Dependencies

**Required**:

- ✅ Existing Analyzer module
- ✅ Existing data fetching (Octopus + Forecast)
- ✅ Existing DataStore
- ✅ Pushover notifications

**New**:

- Multi-day planner module (~200 lines)
- Planning script (~150 lines)

**No external dependencies** - pure Python with existing infrastructure!

---

## Timeline (Simplified)

| Phase | Task | Hours | Status |
|-------|------|-------|--------|
| 1 | Multi-day planner module | 3 | Pending |
| 2 | Planning script | 2 | Pending |
| 3 | Testing | 1.5 | Pending |
| 4 | Documentation | 0.5 | Pending |
| **Total** | | **7 hours** | ✨ Reduced from 10! |

---

**Status**: Design complete (simplified - no battery tracking)
**Next Step**: Begin Phase 1 (Multi-Day Planner Module)
