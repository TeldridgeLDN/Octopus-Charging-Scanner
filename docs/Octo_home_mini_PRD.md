
# 📄 Product Requirements Document (PRD)

## Product Name

**Adaptive Charging Intelligence Extension (ACIX)**
*for Octopus-Charging-Scanner*

---

## 1. Problem Statement

The current system:

* Optimises **future EV charging windows** based on Agile price forecasts
* Assumes the EV is available
* Has **no visibility of real-world behaviour**

Key gaps:

* No detection of **EV plug-in events**
* No validation of whether recommendations were followed
* No behavioural feedback loop to improve outcomes over time

---

## 2. Goals & Non-Goals

### Goals

1. Detect **EV plug-in and charging events** using household usage data
2. Compare **recommended vs actual charging**
3. Generate **behavioural insights** to inform future decisions
4. Keep system **forecast-first, hardware-agnostic**

### Non-Goals

* No charger control
* No real-time sub-second detection
* No perfect appliance identification (probabilistic is acceptable)

---

## 3. Architecture Overview

```
Octopus Agile Prices
        ↓
Octopus-Charging-Scanner (existing)
        ↓
Recommended Charge Windows
        ↓
────────────────────────────────────
        ↑
Usage Data (Home Mini)
        ↓
octopus-usage-exporter
        ↓
Event Detection Layer (new)
        ↓
Behaviour & Feedback Engine (new)
```

---

## 4. Key Features & Requirements

### 4.1 EV Plug-In & Charging Detection

**Functional Requirements**

* Detect sustained load increases consistent with EV charging
* Distinguish:

  * Plugged in but waiting
  * Charging started
  * Charging stopped

**Heuristics (initial)**

* Power increase ≥ **5 kW**
* Sustained for ≥ **2 intervals**
* Time-adjacent intervals must be continuous

**Outputs**

```json
{
  "event": "ev_charging_start",
  "timestamp": "2026-02-16T22:30:00Z",
  "estimated_power_kw": 7.2
}
```

---

### 4.2 Recommendation vs Reality Analysis

**Functional Requirements**

* Compare:

  * Forecasted cheapest windows
  * Actual charging intervals
* Compute performance metrics

**Metrics**

* % charging in cheapest X%
* Average price paid vs optimal
* Missed cheap slots
* Plug-in delay (arrival → plug-in)

---

### 4.3 Behaviour Profiling

**Functional Requirements**

* Learn habitual plug-in times
* Detect recurring missed opportunities
* Segment weekday vs weekend behaviour

**Outputs**

```json
{
  "weekday_plug_in_mean": "18:25",
  "missed_slots_last_7_days": 4,
  "charging_efficiency_score": 0.87
}
```

---

### 4.4 Scanner Feedback Loop

**Functional Requirements**

* Use historical behaviour to:

  * Adjust alert timing
  * Adjust forecast confidence thresholds
* No changes to price forecasting logic required

---

## 5. Data Sources

| Source                 | Purpose             |
| ---------------------- | ------------------- |
| Octopus Agile API      | Price forecast      |
| octopus-usage-exporter | Actual import usage |
| Charging Scanner       | Recommendations     |

---

## 6. Storage (Lightweight)

Use JSON or SQLite initially.

```text
data/
 ├─ forecasts.json
 ├─ usage_raw.json
 ├─ events.json
 ├─ sessions.json
 └─ behaviour_metrics.json
```

---

# 🧪 Example Code (Python)

Below are **drop-in style examples** designed to sit *next to* your existing scanner.

---

## 1️⃣ Fetch Usage Data (from exporter)

```python
import requests
from datetime import datetime, timedelta

EXPORTER_URL = "http://localhost:8000/usage"

def fetch_usage(start, end):
    response = requests.get(EXPORTER_URL, params={
        "start": start.isoformat(),
        "end": end.isoformat()
    })
    return response.json()
```

---

## 2️⃣ EV Charging Detection

```python
POWER_THRESHOLD_KW = 5.0
MIN_INTERVALS = 2

def detect_ev_sessions(usage_data):
    sessions = []
    current = []

    for point in usage_data:
        power = point["power_kw"]

        if power >= POWER_THRESHOLD_KW:
            current.append(point)
        else:
            if len(current) >= MIN_INTERVALS:
                sessions.append(current)
            current = []

    if len(current) >= MIN_INTERVALS:
        sessions.append(current)

    return sessions
```

---

## 3️⃣ Convert Sessions to Events

```python
def session_to_event(session):
    return {
        "event": "ev_charging_session",
        "start": session[0]["timestamp"],
        "end": session[-1]["timestamp"],
        "avg_power_kw": sum(p["power_kw"] for p in session) / len(session)
    }
```

---

## 4️⃣ Compare Against Scanner Recommendations

```python
def score_session(session, cheap_windows):
    session_prices = [
        w["price"] for w in cheap_windows
        if w["start"] <= session["start"] <= w["end"]
    ]

    if not session_prices:
        return "outside_recommendation"

    return "optimal" if min(session_prices) <= 5 else "suboptimal"
```

---

## 5️⃣ Behaviour Metrics

```python
def plug_in_delay(arrival_time, plug_in_time):
    delta = plug_in_time - arrival_time
    return delta.total_seconds() / 60
```

---

## 6️⃣ Daily Insight Summary

```python
def daily_summary(sessions, recommendations):
    return {
        "sessions": len(sessions),
        "optimal_sessions": sum(1 for s in sessions if s["score"] == "optimal"),
        "missed_opportunities": len(recommendations) - len(sessions)
    }
```

---

# 📈 Example Insight Output

```json
{
  "date": "2026-02-16",
  "insight": "You plugged in after the cheapest window on 3 of the last 5 weekdays. Plugging in immediately on arrival would have reduced costs by ~18%."
}
```

---

# 🚀 Incremental Rollout Plan

**Phase 1**

* Usage ingestion
* EV charging detection
* Session logging

**Phase 2**

* Forecast vs actual comparison
* Simple dashboards / summaries

**Phase 3**

* Behaviour-aware alert timing
* Habit-based recommendations

---

# 🧠 Why This Works Well for You

* No new hardware
* Clean electrical environment
* Agile volatility amplifies behavioural gains
* Human feedback loop > automation alone


