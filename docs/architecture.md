# EV Charging Optimizer — Architecture Overview

Fishbone / dependency diagram for the full system. Render with VS Code Markdown Preview
(install "Markdown Preview Mermaid Support" extension if diagrams don't display).

## System Fishbone

```mermaid
graph LR
    subgraph SOURCES["📡 Data Sources"]
        OA["<b>Octopus API</b><br/>octopus_api.py<br/>Actual prices · 48h · 30-min"]
        AP["<b>agile_predict API</b><br/>agile_predict_api.py ⭐NEW<br/>ML forecast · 14 days · confidence bands"]
        GL["<b>Guy Lipman</b><br/>forecast_api.py<br/>HTML scrape · 7 days · fallback"]
        CA["<b>Carbon Intensity API</b><br/>carbon_api.py<br/>National Grid · 48h carbon"]
    end

    subgraph ANALYSIS["🔬 Core Analysis"]
        AN["<b>Analyzer</b><br/>analyzer.py<br/>Optimal window scoring<br/>60% price · 40% carbon"]
        MDP["<b>MultiDayPlanner</b><br/>multi_day_planner.py<br/>7-day cost comparisons<br/>best-day identification"]
        FE["<b>ForecastEvolution</b><br/>forecast_evolution.py<br/>Accuracy tracking · MAE grading"]
        CT["<b>CostTracker</b><br/>cost_tracker.py<br/>Monthly aggregation · baseline delta"]
    end

    subgraph SCRIPTS["⚙️ Scheduled Scripts (launchd)"]
        DN["<b>daily_notification.py</b><br/>16:00 daily<br/>Today's window + 'better day' hint ⭐"]
        WS["<b>weekly_summary.py</b><br/>18:00 Sunday<br/>Past 7 days + best days ahead ⭐"]
        MS["<b>monthly_summary.py</b><br/>End of month<br/>Cost & savings report"]
        CR["<b>charge_reminder.py</b><br/>20:00 daily<br/>Evening plug-in nudge"]
    end

    subgraph OUTPUT["📤 Output"]
        PO["<b>Pushover</b><br/>pushover.py<br/>Mobile push notifications"]
        GC["<b>Google Calendar</b><br/>google_calendar.py<br/>7-day charging windows"]
        DS["<b>DataStore</b><br/>data_store.py<br/>/data/*.json · 30-day retention"]
    end

    OA -->|"PriceSlots (actual)"| AN
    OA -->|"PriceSlots (days 0-1)"| MDP
    AP -->|"PriceSlots + confidence bands"| MDP
    GL -->|"PriceSlots (last resort)"| MDP
    CA -->|CarbonSlots| AN
    CA -->|CarbonSlots| MDP
    AN -->|ChargingWindow| DN
    MDP -->|MultiDayPlan| DN
    MDP -->|MultiDayPlan| WS
    MDP -->|MultiDayPlan| GC
    FE -->|"Accuracy grade (A-F)"| WS
    CT -->|"Month-to-date costs"| WS
    CT -->|"Monthly totals"| MS
    DN -->|Notification| PO
    DN -->|Recommendation| DS
    WS -->|Summary| PO
    MS -->|Report| PO
    CR -->|Reminder| PO
    DS -->|"7-day history"| WS
    DS -->|"30-day history"| MS
    DS -->|"User actions"| FE
```

## Data Source Priority (Fallback Chain)

```
Day 0-1:  Octopus actual prices  (published daily ~16:00 UTC)
Day 2-14: agile_predict API      ← NEW primary forecast source
Day 2-7:  Guy Lipman scrape      ← fallback if agile_predict unavailable
```

## Key Data Models

| Model | File | Fields |
|---|---|---|
| `PriceSlot` | analyzer.py | `time, price (p/kWh), source` |
| `CarbonSlot` | analyzer.py | `time, intensity (gCO2/kWh)` |
| `ChargingWindow` | analyzer.py | `start, end, avg_price, avg_carbon, rating, score, savings_vs_baseline` |
| `DayComparison` | multi_day_planner.py | `date, day_name, avg_price, cost, rating, price_source, savings_vs_today` |
| `MultiDayPlan` | multi_day_planner.py | `days[], best_day, kwh_amount` |

## Notification Triggers

| Condition | Priority | Sound |
|---|---|---|
| Negative pricing | 2 (emergency) | cashregister |
| EXCELLENT rating | 1 (high) | cashregister |
| Price ≤ 8p/kWh | 1 (high) | cashregister |
| Savings ≥ £1.50 | 0 (normal) | cosmic |
| Otherwise | skipped | — |

## Config Location

All user-tunable settings: `config/config.yaml`
Secrets (Pushover keys): `.env` file
