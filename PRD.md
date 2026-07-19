# Product Requirements Document: EV Charging Optimizer

**Version:** 1.0
**Date:** 2025-12-07
**Status:** Draft
**Author:** Orchestrator Project

---

## Executive Summary

### Vision
Enable cost-effective and environmentally conscious EV charging through intelligent automation that balances electricity pricing with carbon intensity, delivering measurable savings while maintaining user control.

### Problem Statement
EV owners on variable tariffs (Octopus Agile) face:

- Electricity prices varying 48x per day (£0.01 to £0.48/kWh observed)
- No visibility into optimal charging windows
- Trade-offs between cost savings and environmental impact
- Manual effort required to monitor and respond to price changes

### Solution
A two-phase intelligent charging system:

1. **Phase 1**: Manual alerts with actionable recommendations (Mac Mini platform)
2. **Phase 2**: Full automation via Home Assistant Green integration (future)

### Success Metrics
- **Primary**: £50-70/year cost savings from optimized charging
- **Secondary**:
  - User follows 70%+ of recommendations
  - System uptime >99% over 30 days
  - Notifications are actionable without requiring calculation

---

## User Personas

### Primary User: Tom (EV Owner)
- **Vehicle**: Standard EV with 3-pin slow charger (7.4kW)
- **Tariff**: Octopus Agile (London/Eastern England region H)
- **Priorities**: 60% cost savings, 40% environmental impact
- **Technical**: Comfortable with Mac Mini setup, wants simple notifications
- **Behavior**: Charges 2-3 times per week, typically overnight

---

## Technical Requirements

### TR-1: Data Collection APIs

#### Octopus Energy Agile API
- **Endpoint**: `https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25/electricity-tariffs/E-1R-AGILE-FLEX-22-11-25-H/standard-unit-rates/`
- **Region**: H (Southern England/London)
- **Data**: Half-hourly prices for next 24 hours (published daily at 16:00)
- **Format**: JSON with `valid_from`, `valid_to`, `value_inc_vat`
- **Update Frequency**: Daily at 16:00
- **Fallback**: Retry with exponential backoff (5s, 15s, 30s)

#### Carbon Intensity API
- **Endpoint**: `https://api.carbonintensity.org.uk/regional/intensity/fw48h/postcode/{postcode}`
- **Data**: 48-hour carbon intensity forecast
- **Units**: gCO2/kWh
- **Update Frequency**: Every 12 hours
- **Fallback**: Use last successful fetch if API unavailable

#### Guy Lipman Forecasting Model
- **Endpoint**: `https://energy.guylipman.com/forecasts?region=H`
- **Data**: 7-day forward price forecasts
- **Method**: HTML parsing with BeautifulSoup4
- **Model**: Linear regression based on BMRS data (demand, wind, solar)
- **Update Frequency**: Every 6 hours
- **Fallback**: Use Octopus next-day only if unavailable
- **Key Feature**: Multi-day optimization (e.g., "charge Tuesday not Wednesday")

### TR-2: Data Storage

#### JSON-Based Persistence
```json
{
  "forecast_history.json": "7-day rolling price forecasts",
  "daily_recommendations.json": "30-day recommendation archive",
  "user_actions.json": "Manual logging of charge events",
  "config.json": "User preferences and API keys"
}
```

#### Data Retention
- Price forecasts: 7 days rolling
- Recommendations: 30 days archive
- User actions: Indefinite (for pattern analysis)
- Logs: 14 days

### TR-3: Notification System

#### Pushover Integration
- **Endpoint**: `https://api.pushover.net/1/messages.json`
- **Auth**: User Key + API Token (stored in environment variables)
- **Features**:
  - Priority levels: Quiet (-1), Normal (0), High (1)
  - HTML formatting support
  - Chart attachments (matplotlib PNG)
  - Custom sounds: cashregister (cheap), cosmic (clean), pushover (urgent)
  - 1024 character message limit
- **Rate Limit**: Max 5 messages/day
- **Retry Logic**: 3 attempts with 30s delay

### TR-4: Analysis Engine

#### Price/Carbon Scoring Algorithm
```
def calculate_opportunity_score(price, carbon, weights):
    """
    Score = (price_weight * price_score) + (carbon_weight * carbon_score)

    Price Score:
      EXCELLENT: <= 10p/kWh (score: 100)
      GOOD: <= 15p/kWh (score: 75)
      AVERAGE: <= 20p/kWh (score: 50)
      POOR: > 20p/kWh (score: 25)

    Carbon Score:
      EXCELLENT: <= 100 gCO2/kWh (score: 100)
      GOOD: <= 150 gCO2/kWh (score: 75)
      AVERAGE: <= 200 gCO2/kWh (score: 50)
      POOR: > 200 gCO2/kWh (score: 25)
    """
    return combined_score
```

#### Configurable Weights
- Default: 60% price, 40% carbon
- User adjustable in config.yaml
- Validates weights sum to 1.0

---

## Functional Requirements

### FR-1: Weekly Forecast Analysis
**Script**: `weekly_forecast.py`
**Schedule**: Monday 07:00 via launchd
**Duration**: <30 seconds

**Process**:

1. Fetch 7-day price forecasts from Guy Lipman API
2. Parse HTML and extract forecast data
3. Store in `forecast_history.json` with timestamp
4. Generate weekly trend chart (matplotlib)
5. Send Pushover notification with:
   - Best charging days for the week
   - Expected cost for 30kWh charge each day
   - Chart attachment showing price trends
   - Recommendation: "Charge Tuesday/Thursday, avoid Monday/Wednesday"

**Notification Priority**: Normal (0)
**Sound**: pushover
**Format**: HTML with bold for best days

### FR-2: Daily Charging Recommendation
**Script**: `daily_notification.py`
**Schedule**: Daily 16:00 (after Octopus price publish)
**Duration**: <15 seconds

**Process**:

1. Fetch next-day actual prices from Octopus Agile API
2. Fetch 48-hour carbon intensity forecast
3. Combine data and calculate optimal windows
4. Classify opportunity: EXCELLENT/GOOD/AVERAGE
5. Send notification with:
   - Tonight's recommendation (Yes/No/Maybe)
   - Best time window (e.g., "02:00-08:00")
   - Expected cost for 30kWh charge
   - Carbon footprint estimate
   - Savings vs average charging time
   - "Why": cheap/clean/both

**Notification Priority**:

- EXCELLENT: High (1), sound: cashregister
- GOOD: Normal (0), sound: cosmic
- AVERAGE: Quiet (-1), sound: none

**Example Notification**:
```yaml
🔋 Tonight: EXCELLENT charging opportunity

⚡ Best window: 02:00 - 08:00
💰 Cost: £2.10 (save £1.50 vs 18:00)
🌱 Carbon: 85 gCO2/kWh (very clean)

Why: Both cheap AND clean
Action: Plug in before bed
```

### FR-3: Evening Charge Reminder
**Script**: `charge_reminder.py`
**Schedule**: Daily 20:00
**Duration**: <5 seconds

**Process**:

1. Check if today had EXCELLENT/GOOD recommendation
2. If yes, send gentle reminder
3. Include quick summary of tonight's window

**Notification Priority**: Normal (0)
**Sound**: pushover
**Message**: "Reminder: Tonight is a good night to charge (best window: 02:00-08:00)"

### FR-4: Appliance Planning (Bonus Feature)
**Script**: `appliance_planner.py`
**Schedule**: Daily 06:00
**Duration**: <10 seconds

**Process**:

1. Identify cheapest 3-hour windows today
2. Send notification suggesting:
   - Dishwasher run time
   - Washing machine run time
   - Tumble dryer time
   - Any other high-energy appliances

**Notification Priority**: Quiet (-1)
**Sound**: none
**Format**: Simple bullet list

### FR-5: Weekly Summary Report
**Script**: `weekly_summary.py`
**Schedule**: Sunday 18:00
**Duration**: <20 seconds

**Process**:

1. Analyze past 7 days of recommendations vs actions
2. Calculate actual savings achieved
3. Report carbon reduction
4. Identify missed opportunities
5. Suggest threshold adjustments if needed

**Notification Priority**: Normal (0)
**Sound**: pushover
**Format**: HTML report with charts

---

## Non-Functional Requirements

### NFR-1: Performance
- API calls complete in <5 seconds (95th percentile)
- Total script execution <30 seconds for weekly forecast
- Daily notification <15 seconds end-to-end
- Notification delivery <10 seconds via Pushover

### NFR-2: Reliability
- **Uptime**: 99%+ over 30-day periods
- **API Fallbacks**: Graceful degradation if APIs unavailable
- **Error Handling**: Log errors, retry with backoff, notify user of persistent failures
- **Data Integrity**: Atomic JSON writes, backup before overwrite

### NFR-3: Security
- **API Keys**: Stored in environment variables only (`.env` file, not committed)
- **File Permissions**: 600 for config files, 755 for scripts
- **Data Privacy**: All data stored locally, no third-party analytics

### NFR-4: Usability
- **Notifications**: Actionable without requiring calculations
- **Configuration**: Single YAML file for all user preferences
- **Setup**: <30 minutes from clone to first notification
- **Maintenance**: Zero ongoing maintenance required

### NFR-5: Maintainability
- **Code Style**: Black formatter, flake8 linter
- **Module Size**: <500 lines per module (PAI principle)
- **Documentation**: Inline docstrings, type hints
- **Testing**: 80%+ code coverage, pytest framework

---

## Implementation Phases

### Phase 1: Manual Alert System (Weeks 1-4)

#### Week 1: Foundation
- Set up project structure
- Implement API clients (octopus, carbon, forecast, pushover)
- Create data models and JSON storage
- Write unit tests for API clients
- **Deliverable**: Working API integration

#### Week 2: Core Analysis
- Implement price analyzer module
- Create weekly forecast script
- Create daily notification script
- Test with sample data
- Validate notification formatting
- **Deliverable**: Daily notifications operational

#### Week 3: Enhanced Features
- Implement charge reminder script
- Implement appliance planner script
- Implement weekly summary script
- Create user action logging tools
- End-to-end testing
- **Deliverable**: All 5 scripts functional

#### Week 4: Production Deployment
- Create macOS launch agents
- Configure logging and monitoring
- Set up credential management (`.env`)
- Deploy to Mac Mini
- Monitor for 7 days and tune thresholds
- **Deliverable**: Production system running

### Phase 2: Full Automation (Future - Post 3-Month Validation)

#### Hardware Migration
- Purchase Home Assistant Green (£99)
- Install Tuya/Timeguard smart plug
- Configure HA integration
- Sell Mac Mini (recover ~£60)

#### Software Migration
- Port notification logic to HA automations
- Add consumption monitoring
- Implement automatic plug control
- Add voice assistant integration (Alexa/Google)
- Expand to multi-appliance orchestration

#### Advanced Features
- Machine learning for usage prediction
- Real-time price updates (when available)
- Integration with solar generation (future)
- V2G (Vehicle-to-Grid) support (future)

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| Guy Lipman API unavailable | High | Medium | Fallback to Octopus next-day only, implement HTML parsing robustness |
| Mac Mini sleeps | High | Low | Disable sleep in Energy settings, verify in setup |
| Forecast accuracy degrades | Medium | Medium | Monitor RMSE, adjust weighting, alert user to poor forecasts |
| Pushover rate limit hit | Low | Low | Track message count, cap at 5/day, consolidate messages |
| User ignores notifications | Medium | Medium | Tune timing based on user feedback, adjust priorities |
| Octopus API changes format | Medium | Low | Version API calls, monitor for errors, add schema validation |
| Network outage during fetch | Low | Medium | Retry logic with exponential backoff, use cached data |

---

## Configuration Schema

### config.yaml
```yaml
# User preferences
user:
  postcode: "E1"
  region: "H"  # Octopus Agile region
  charging_rate_kw: 7.4
  typical_charge_kwh: 30

# Thresholds (pence/kWh and gCO2/kWh)
thresholds:
  price_excellent: 10
  price_good: 15
  carbon_excellent: 100
  carbon_good: 150

# Weighting (must sum to 1.0)
preferences:
  price_weight: 0.6
  carbon_weight: 0.4

# Notification preferences
notifications:
  daily_time: "16:00"
  reminder_time: "20:00"
  weekly_summary_time: "18:00"
  max_per_day: 5

# API configuration
apis:
  octopus:
    region: "H"
    product: "AGILE-FLEX-22-11-25"
  pushover:
    user_key: "ENV:PUSHOVER_USER_KEY"
    api_token: "ENV:PUSHOVER_API_TOKEN"
  forecast:
    url: "https://energy.guylipman.com/forecasts"
    update_interval_hours: 6
```

---

## Testing Strategy

### Unit Tests
- API client error handling
- Data model validation
- Score calculation algorithms
- JSON storage operations
- Notification formatting

### Integration Tests
- End-to-end script execution
- API mock responses
- Notification delivery
- Error recovery scenarios

### User Acceptance Tests
- Week 1: Verify notifications arrive on time
- Week 2: Validate recommendation accuracy
- Week 3: Confirm cost savings vs manual charging
- Week 4: System stability over 7-day period

---

## Success Criteria

### Phase 1 Success (Month 1)
- ✅ All 5 scripts operational on Mac Mini
- ✅ Daily notifications arriving at 16:00
- ✅ Weekly forecast on Mondays
- ✅ System uptime >99%
- ✅ User follows >70% of recommendations
- ✅ Zero manual intervention required

### Phase 1 Validation (Months 2-3)
- ✅ Measured savings: £50-70/year on track
- ✅ Forecast accuracy: RMSE <5p/kWh vs actual
- ✅ User satisfaction: Notifications are helpful
- ✅ No missed opportunities due to system failures

### Phase 2 Readiness (Month 4+)
- ✅ Phase 1 validated over 3 months
- ✅ Decision to proceed with HA investment
- ✅ Migration plan documented
- ✅ Automation logic tested in simulation

---

## Dependencies

### Python Packages