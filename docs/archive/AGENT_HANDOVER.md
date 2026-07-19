# Agent Handover Document: EV Charging Optimizer

**Project**: ev-charging-optimizer
**Created**: 2025-12-07
**Status**: Foundation complete, ready for implementation
**Next Agent**: Implementation specialist

---

## Project Summary

You're inheriting a **fully planned** EV charging optimization system that's ready for implementation. All architectural decisions have been made, requirements documented, and tasks broken down. Your job is to implement the Python code following the detailed specifications.

---

## What's Already Done ✅

### 1. Complete Project Structure
```
~/ev-charging-optimizer/
├── README.md                 # Project overview
├── PRD.md                    # Complete Product Requirements Document
├── requirements.txt          # All dependencies listed
├── .env.example             # Environment template
├── .gitignore               # Configured
├── config/
│   └── config.yaml          # User configuration template
├── src/
│   ├── modules/             # Empty, ready for API clients
│   └── scripts/             # Empty, ready for executable scripts
├── data/                    # For JSON storage
├── logs/                    # For application logs
├── charts/                  # For matplotlib outputs
├── tests/                   # For pytest tests
├── docs/
│   ├── PAI_DIET103_ALIGNMENT.md  # Architectural validation
│   └── (setup.md, user-guide.md to be created)
└── .taskmaster/
    ├── config.json          # TaskMaster AI configuration
    ├── docs/prd.txt         # Quick reference PRD
    └── tasks/tasks.json     # Complete task breakdown (5 epics, 26 subtasks)
```

### 2. Comprehensive Documentation
- **PRD.md**: 400+ line Product Requirements Document with:
  - Technical requirements for all APIs
  - Functional requirements for all 5 scripts
  - Non-functional requirements (performance, security, etc.)
  - Configuration schema
  - Success criteria
- **README.md**: Project overview and quick start
- **PAI_DIET103_ALIGNMENT.md**: Architectural validation (98/100 score)
- **.taskmaster/tasks/tasks.json**: Week-by-week task breakdown

### 3. Configuration Files
- **config.yaml**: Complete user configuration template
- **requirements.txt**: All Python dependencies
- **.env.example**: Environment variable template
- **.taskmaster/config.json**: AI model settings (Claude 3.7 Sonnet)

---

## What You Need to Implement 🎯

### Phase 1: Week 1 - Foundation (Task 1.x)

#### Task 1.2: Octopus Energy Agile API Client
**File**: `src/modules/octopus_api.py`

**Requirements** (from PRD.md):

- Endpoint: `https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25/electricity-tariffs/E-1R-AGILE-FLEX-22-11-25-H/standard-unit-rates/`
- Fetch next 24 hours of half-hourly prices
- No authentication required
- Return structured data: `List[Dict]` with `valid_from`, `valid_to`, `value_inc_vat`
- Error handling: Retry with exponential backoff (5s, 15s, 30s)
- Timeout: 10 seconds per request

**Pattern to Follow**:
```
from typing import Dict, List, Any
from datetime import datetime
import requests
import time

class BaseAPIClient:
    """Base class for all API clients (UFC pattern)"""
    def __init__(self, timeout: int = 10, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    def fetch(self, url: str) -> Dict[str, Any]:
        """Unified fetch with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(5 * (2 ** attempt))

class OctopusAPIClient(BaseAPIClient):
    """Fetch Octopus Agile electricity prices"""
    def get_prices(self, region: str = "H") -> List[Dict[str, Any]]:
        # Implementation here
        pass
```

**Test File**: `tests/test_octopus_api.py`

- Mock API responses
- Test error handling
- Test data parsing
- Target: 90%+ coverage

#### Task 1.3: Carbon Intensity API Client
**File**: `src/modules/carbon_api.py`

**Requirements**:

- Endpoint: `https://api.carbonintensity.org.uk/regional/intensity/fw48h/postcode/{postcode}`
- Fetch 48-hour carbon intensity forecast
- Parse nested regional data
- Return: `List[Dict]` with `time`, `intensity` (gCO2/kWh)
- Similar error handling as Octopus client

#### Task 1.4: Guy Lipman Forecast Scraper
**File**: `src/modules/forecast_api.py`

**Requirements**:

- URL: `https://energy.guylipman.com/forecasts?region=H`
- HTML parsing with BeautifulSoup4
- Extract 7-day price forecasts
- Fallback: If unavailable, return empty list (script uses Octopus only)
- **Critical**: Robust HTML parsing (structure may change)

**Reference**: See original conversation note for HTML structure examples

#### Task 1.5: Pushover Notification Client
**File**: `src/modules/pushover.py`

**Requirements**:

- Endpoint: `https://api.pushover.net/1/messages.json`
- API keys from environment variables: `PUSHOVER_USER_KEY`, `PUSHOVER_API_TOKEN`
- Support:
  - Priority levels: -2 (quiet) to 2 (emergency)
  - HTML formatting
  - Image attachments (matplotlib charts)
  - Custom sounds: cashregister, cosmic, pushover
- Message limit: 1024 characters
- Rate limit: Track calls, max 5/day

**Method Signature**:
```
def send_notification(
    self,
    title: str,
    message: str,
    priority: int = 0,
    sound: str = "pushover",
    html: bool = True,
    attachment: Optional[str] = None
) -> bool:
    """Send Pushover notification"""
    pass
```

#### Task 1.6: Data Storage Layer
**File**: `src/modules/data_store.py`

**Requirements**:

- JSON-based persistence to `data/` directory
- Files:
  - `forecast_history.json` - 7-day rolling forecasts
  - `daily_recommendations.json` - 30-day archive
  - `user_actions.json` - Manual charge logs
- Atomic writes (backup before overwrite)
- Data retention enforcement
- Type hints and validation

**Class Structure**:
```
class DataStore:
    def save_forecast(self, forecast: Dict) -> None:
        pass

    def get_latest_forecast(self) -> Optional[Dict]:
        pass

    def save_recommendation(self, rec: Dict) -> None:
        pass

    def get_recommendations(self, days: int = 30) -> List[Dict]:
        pass

    def cleanup_old_data(self) -> None:
        """Apply retention policies"""
        pass
```

#### Task 1.7: Unit Tests
**Directory**: `tests/`

**Files to Create**:

- `tests/conftest.py` - Shared fixtures, mock API responses
- `tests/test_octopus_api.py` - Octopus client tests
- `tests/test_carbon_api.py` - Carbon client tests
- `tests/test_forecast_api.py` - Forecast scraper tests
- `tests/test_pushover.py` - Pushover client tests
- `tests/test_data_store.py` - Storage layer tests

**Coverage Target**: 80%+ overall, 90%+ for API clients

---

## Critical Information for Implementation

### 1. API Credentials

**Pushover** (required immediately):

- User needs to provide: `PUSHOVER_USER_KEY` and `PUSHOVER_API_TOKEN`
- Store in `.env` file (create from `.env.example`)
- Load with `python-dotenv`

**Other APIs** (no auth required):

- Octopus Energy: Public API, no key needed
- Carbon Intensity: Public API, no key needed
- Guy Lipman: Web scraping, no auth

### 2. Configuration Loading

**Pattern**:
```
import os
import yaml
from dotenv import load_dotenv

def load_config():
    load_dotenv()  # Load .env file
    with open('config/config.yaml') as f:
        config = yaml.safe_load(f)

    # Override with environment variables
    config['apis']['pushover']['user_key'] = os.getenv('PUSHOVER_USER_KEY')
    config['apis']['pushover']['api_token'] = os.getenv('PUSHOVER_API_TOKEN')

    return config
```

### 3. Data Models

**Suggested Dataclass Structure**:
```
from dataclasses import dataclass
from datetime import datetime
from typing import List

@dataclass
class PriceSlot:
    time: datetime
    price: float  # pence/kWh
    source: str   # "octopus" or "forecast"

@dataclass
class CarbonSlot:
    time: datetime
    intensity: int  # gCO2/kWh

@dataclass
class Recommendation:
    date: str
    rating: str  # EXCELLENT/GOOD/AVERAGE
    best_window_start: datetime
    best_window_end: datetime
    estimated_cost: float
    carbon_footprint: int
    savings: float
    reason: str  # "cheap", "clean", "both"
```

### 4. Error Handling Pattern

**Every API call should**:
```
import logging

logger = logging.getLogger(__name__)

try:
    data = api_client.fetch(url)
except requests.exceptions.Timeout:
    logger.error("API timeout")
    # Retry or fallback
except requests.exceptions.HTTPError as e:
    logger.error(f"HTTP error: {e.response.status_code}")
    # Handle 4xx vs 5xx differently
except Exception as e:
    logger.exception("Unexpected error")
    # Last resort error handling
```

### 5. Logging Configuration

**Setup** (in each script):
```
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/ev-optimizer.log'),
        logging.StreamHandler()
    ]
)
```

---

## Code from Original Conversation

The original conversation note contains **working code examples** for:

1. Octopus API client implementation
2. Carbon Intensity API client implementation
3. Price analysis algorithms
4. Notification formatting templates
5. Guy Lipman forecasting model details

**Location**: `/Users/tomeldridge/ClaudeMemory/Daily/2025-12/07-ev-charging-automation-project.md`

**How to Access**:
```
# You can read this file to extract code examples
# The file is 50,846 tokens, so read in chunks
# - Lines 1-1000: Project overview and requirements
# - Lines 1000-3000: API client code examples
# - Lines 3000-5000: Analysis algorithm examples
# - Lines 5000-7000: Notification templates
```

**Key Code Sections to Extract**:

- Search for: `class OctopusAPI` - working Octopus client
- Search for: `class CarbonIntensityAPI` - working carbon client
- Search for: `def analyze_opportunity` - scoring algorithm
- Search for: `def format_notification` - Pushover templates

---

## Development Workflow

### Setup Environment
```bash
cd ~/ev-charging-optimizer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with actual Pushover credentials
```

### Development Loop
```bash
# 1. Implement module (e.g., octopus_api.py)
# 2. Write tests (test_octopus_api.py)
# 3. Run tests
pytest tests/test_octopus_api.py -v

# 4. Check coverage
pytest --cov=src/modules tests/

# 5. Format code
black src/ tests/

# 6. Lint
flake8 src/ tests/

# 7. Type check
mypy src/
```

### TaskMaster Integration
```bash
# Update task status
task-master set-status --id=1.2 --status=done

# Get next task
task-master next

# Add implementation notes
task-master update-subtask --id=1.2 --prompt="Implemented Octopus API client with retry logic, 92% test coverage"
```

---

## Testing Strategy

### Unit Tests (Week 1)
**Mock API Responses**:
```
# tests/conftest.py
import pytest

@pytest.fixture
def mock_octopus_response():
    return {
        "results": [
            {
                "valid_from": "2025-12-07T00:00:00Z",
                "valid_to": "2025-12-07T00:30:00Z",
                "value_inc_vat": 12.5
            },
            # ... more slots
        ]
    }

@pytest.fixture
def mock_requests_get(monkeypatch, mock_octopus_response):
    class MockResponse:
        def __init__(self):
            self.status_code = 200

        def json(self):
            return mock_octopus_response

        def raise_for_status(self):
            pass

    def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(requests, "get", mock_get)
```

### Integration Tests (Week 3)
**End-to-End Script Testing**:
```
# tests/test_integration.py
def test_daily_notification_e2e(tmp_path):
    """Test daily notification script end-to-end"""
    # Set up test environment
    # Run script
    # Verify notification sent
    # Check data saved
    pass
```bash

---

## Success Criteria for Week 1

✅ **All 6 API clients implemented**

- OctopusAPIClient
- CarbonAPIClient
- ForecastAPIClient
- PushoverClient
- DataStore
- BaseAPIClient (UFC pattern)

✅ **Test coverage ≥80%**

- Unit tests for each module
- Mock API responses
- Error handling tested

✅ **Code quality**

- Black formatted
- Flake8 clean
- Type hints on all functions
- Docstrings on all classes/methods

✅ **Working demonstration**

- Can fetch live Octopus prices
- Can fetch live carbon data
- Can send test Pushover notification
- Can persist data to JSON

---

## Common Pitfalls to Avoid

### 1. API Rate Limits
- Octopus: No documented limit, but be respectful
- Carbon Intensity: No limit, but cache 12-hour forecast
- Pushover: 10,000/month free, but limit to 5/day for politeness

### 2. Timezone Handling
- All Octopus times are in UTC
- Carbon Intensity times are in UTC
- User is in UK (GMT/BST)
- **Always use timezone-aware datetimes**

```
from datetime import datetime, timezone
import pytz

# Parse Octopus time (UTC)
dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))

# Convert to UK local time
uk_tz = pytz.timezone('Europe/London')
local_dt = dt.astimezone(uk_tz)