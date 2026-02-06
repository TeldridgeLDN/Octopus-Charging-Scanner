# EV Charging Optimizer

An intelligent EV charging system that optimizes charging times based on electricity pricing and carbon intensity.

## Overview

This project implements a two-phase EV charging automation system:

**Phase 1: Manual Alert System** (Current)

- Daily analysis of electricity prices and carbon intensity
- Smart notifications via Pushover
- User manually controls charging based on recommendations

**Phase 2: Full Automation** (Future)

- Integration with Home Assistant Green
- Automated smart plug control
- Zero manual intervention

## Key Features

- **Octopus Agile Integration**: Fetch real-time and forecasted electricity pricing
- **Carbon Intensity Tracking**: UK National Grid carbon intensity forecasts
- **Guy Lipman Forecasting**: 7-day forward price predictions for strategic planning
- **Smart Notifications**: Priority-based alerts with cost/carbon analysis
- **Historical Tracking**: 30-day charging history and recommendations
- **Configurable Weighting**: Balance between cost savings and environmental impact

## Technical Stack

- **Language**: Python 3.11+
- **Platform**: macOS (Mac Mini for Phase 1)
- **APIs**:
  - Octopus Energy Agile API
  - Carbon Intensity API (National Grid ESO)
  - Guy Lipman Energy Forecasts
  - Pushover Notifications
- **Scheduling**: macOS launchd

## Project Structure

```
ev-charging-optimizer/
├── src/
│   ├── modules/           # Core library modules
│   │   ├── forecast_api.py
│   │   ├── octopus_api.py
│   │   ├── carbon_api.py
│   │   ├── pushover.py
│   │   ├── analyzer.py
│   │   └── data_store.py
│   └── scripts/           # Executable scripts
│       ├── weekly_forecast.py
│       ├── daily_notification.py
│       ├── charge_reminder.py
│       ├── appliance_planner.py
│       └── weekly_summary.py
├── config/
│   └── config.yaml        # User configuration
├── data/                  # JSON data storage
├── logs/                  # Application logs
├── charts/                # Generated visualizations
├── tests/                 # Unit tests
├── docs/                  # Documentation
└── .taskmaster/           # Task management
```

## Quick Start

See [docs/setup.md](docs/setup.md) for detailed setup instructions.

## Target Savings

- **Cost**: £50-70/year from optimized charging times
- **Carbon**: Reduced emissions by charging during low-carbon periods
- **Automation**: 70%+ recommendation follow-through target

## Documentation

- [PRD](PRD.md) - Product Requirements Document
- [Setup Guide](docs/setup.md) - Installation and configuration
- [User Guide](docs/user-guide.md) - Daily usage instructions
- [Deployment Guide](docs/deployment.md) - Mac Mini deployment

## Alignment with PAI/diet103

This project follows:

- **PAI Principles**: Skills-as-Containers, UFC pattern, token efficiency
- **diet103 Standards**: Modular architecture, <500 line modules
- **Sibling Project Benefits**: Shares orchestration patterns, templates, monitoring

## License

Private project for personal use.

## Author

Created as part of the Orchestrator_Project ecosystem.
