# Implementation Tasks

## Task 1: Project Setup and Configuration

**Requirements:** REQ-13, REQ-17

**Description:**
Set up the project structure, dependencies, and configuration system with dual environment support (local/.env and GitHub Actions/secrets).

**Acceptance Criteria:**
- Project structure follows `src/aventure_tracker/` layout
- `pyproject.toml` configured with all dependencies and tool settings
- `requirements.txt` and `requirements-dev.txt` generated
- `Settings` class using pydantic-settings with CI detection
- `.env.example` with all required variables documented
- `.gitignore` configured for Python project
- Virtual environment can be created and dependencies installed

**Implementation Details:**
1. Create directory structure as defined in design.md
2. Create `pyproject.toml` with project metadata and dependencies
3. Create `src/aventure_tracker/__init__.py` with version
4. Create `src/aventure_tracker/config.py` with Settings class
5. Create `config/` directory with example YAML files
6. Create `.env.example` with placeholder values
7. Set up `.pre-commit-config.yaml` for ruff

**Test Requirements:**
- Test Settings loads from environment variables
- Test Settings detects CI=true correctly
- Test Settings validates required fields

**Demo:**
```bash
python -c "from aventure_tracker.config import settings; print(settings.model_dump())"
```

---

## Task 2: Data Models

**Requirements:** REQ-1, REQ-6, REQ-11

**Description:**
Create Pydantic models for flights, activities, configuration, and state persistence.

**Acceptance Criteria:**
- `RouteConfig` model with validation for airport codes
- `FlightResult` model with price, airline, times, link
- `InstagramPost` model with id, url, images, caption
- `StateData` model for Gist persistence
- `WeekendTrip` model for date calculations
- All models have proper type hints and validation

**Implementation Details:**
1. Create `src/aventure_tracker/models/__init__.py`
2. Create `src/aventure_tracker/models/flight.py` with RouteConfig, FlightResult, WeekendTrip
3. Create `src/aventure_tracker/models/activity.py` with InstagramPost
4. Create `src/aventure_tracker/models/state.py` with FlightState, InstagramState, StateData
5. Add YAML config loaders for routes.yaml and accounts.yaml

**Test Requirements:**
- Test model validation rejects invalid data
- Test model serialization to/from JSON
- Test YAML config loading

**Demo:**
```bash
python -c "from aventure_tracker.models import RouteConfig; r = RouteConfig(origin='BAQ', destination='MDE', price_threshold=150000, drop_percentage=15); print(r)"
```

---

## Task 3: State Manager with GitHub Gist

**Requirements:** REQ-11

**Description:**
Implement StateManager class that persists and retrieves shared state using a GitHub Gist as backend storage.

**Acceptance Criteria:**
- StateManager initializes with gist_id and token
- `read()` retrieves and parses Gist content as JSON
- `write()` updates Gist content via PATCH request
- Convenience methods for flight prices and seen posts
- Retry logic for transient failures (3 attempts)
- Handles missing/empty Gist gracefully

**Implementation Details:**
1. Create `src/aventure_tracker/infrastructure/__init__.py`
2. Create `src/aventure_tracker/infrastructure/state_manager.py`
3. Implement async methods using `requests` library
4. Add retry decorator for network operations
5. Add state migration logic for version changes

**Test Requirements:**
- Test read() with mocked HTTP response
- Test write() sends correct PATCH payload
- Test retry logic on transient failures
- Test empty Gist returns default state

**Demo:**
Create a test Gist, write state, read it back, verify persistence.

---

## Task 4: Telegram Notifier

**Requirements:** REQ-5, REQ-10, REQ-12

**Description:**
Implement TelegramNotifier class that sends formatted messages via Telegram Bot API with rate limiting.

**Acceptance Criteria:**
- Notifier initializes with bot_token and chat_id
- `send_flight_alert()` formats message with emojis, price, airline, date, link, % change
- `send_activity_alert()` formats message with account, text, link, matched destination
- `send_error_alert()` sends warning notifications
- Rate limiting: max 20 messages per minute
- Graceful handling of API failures

**Implementation Details:**
1. Create `src/aventure_tracker/infrastructure/notifier.py`
2. Implement message formatting with Markdown
3. Add rate limiter using token bucket algorithm
4. Use Telegram sendMessage API endpoint
5. Log errors but don't raise on API failures

**Test Requirements:**
- Test message formatting produces expected output
- Test rate limiter blocks excess messages
- Test API failure is logged but doesn't raise

**Demo:**
```bash
python -c "from aventure_tracker.infrastructure.notifier import TelegramNotifier; n = TelegramNotifier('token', 'chat_id'); import asyncio; asyncio.run(n.send_flight_alert('BAQ→MDE', 145000, 'Avianca', None, 'https://...', 160000))"
```

---

## Task 5: Colombian Holiday Service

**Requirements:** REQ-2, REQ-3

**Description:**
Implement HolidayService that provides Colombian holidays with hardcoded data and API fallback.

**Acceptance Criteria:**
- Hardcoded holidays for 2025 and 2026 in `config/holidays.yaml`
- `get_holidays(year)` returns list of dates
- `is_holiday(date)` checks if date is a holiday
- `is_bridge_weekend(friday)` detects Monday holidays creating puentes
- Fallback to Nager.Date API for years not in config
- Graceful handling when API fails

**Implementation Details:**
1. Create `src/aventure_tracker/services/__init__.py`
2. Create `src/aventure_tracker/services/holidays.py`
3. Create `config/holidays.yaml` with 2025-2026 Colombian holidays
4. Implement Nager.Date API client as fallback
5. Cache API results in memory for the session

**Test Requirements:**
- Test known holidays return True for is_holiday()
- Test bridge weekend detection (e.g., 2025-08-18 is Monday holiday)
- Test API fallback when year not in config
- Test graceful degradation when API fails

**Demo:**
```bash
python -c "from aventure_tracker.services.holidays import HolidayService; from datetime import date; h = HolidayService(); print(h.is_bridge_weekend(date(2025, 8, 15)))"
```

---

## Task 6: Flight Date Calculator

**Requirements:** REQ-2

**Description:**
Implement FlightDateCalculator that generates valid flight dates based on weekend trip logic and holiday awareness.

**Acceptance Criteria:**
- `get_upcoming_weekends(weeks_ahead)` returns list of WeekendTrip objects
- Outbound dates: Thursday after 6PM, Friday before 4PM
- Return dates: Sunday after 2PM, Monday before 10AM
- Bridge weekends extend Monday return window to evening
- Integrates with HolidayService for puente detection

**Implementation Details:**
1. Create `src/aventure_tracker/services/flight_dates.py`
2. Implement weekend iteration logic
3. Add time range calculations for valid flights
4. Integrate HolidayService for bridge detection
5. Handle edge cases (year boundaries, etc.)

**Test Requirements:**
- Test upcoming weekends returns correct dates
- Test bridge weekend extends Monday return
- Test holiday on Friday allows Thursday outbound
- Test time ranges are within expected bounds

**Demo:**
```bash
python -c "from aventure_tracker.services.flight_dates import FlightDateCalculator; from aventure_tracker.services.holidays import HolidayService; calc = FlightDateCalculator(HolidayService()); print(calc.get_upcoming_weekends(4))"
```

---

## Task 7: Base Scraper with Playwright Stealth

**Requirements:** REQ-16

**Description:**
Create BaseScraper class with Playwright and stealth configuration that other scrapers inherit from.

**Acceptance Criteria:**
- Context manager for browser lifecycle (`async with`)
- playwright-stealth applied on browser context
- `random_delay(min_ms, max_ms)` adds jitter between actions
- `safe_goto(url)` with timeout and retry
- `wait_and_click(selector)` with human-like delay
- Headless by default, headed option for debugging

**Implementation Details:**
1. Create `src/aventure_tracker/scrapers/__init__.py`
2. Create `src/aventure_tracker/scrapers/base.py`
3. Configure Playwright with stealth plugin
4. Implement async context manager pattern
5. Add configurable viewport and user agent

**Test Requirements:**
- Test browser launches and closes properly
- Test random_delay produces values in range
- Test stealth is applied (check navigator.webdriver)

**Demo:**
```bash
python -c "from aventure_tracker.scrapers.base import BaseScraper; import asyncio; async def test(): async with BaseScraper() as s: await s.safe_goto('https://example.com'); print('Success'); asyncio.run(test())"
```

---

## Task 8: Google Flights Scraper (Page Object Model)

**Requirements:** REQ-1, REQ-16

**Description:**
Implement GoogleFlightsPage class using Page Object Model pattern for flight search and price extraction.

**Acceptance Criteria:**
- `navigate()` opens Google Flights with cookie consent handling
- `set_route(origin, destination)` enters airport codes
- `set_dates(departure, return_date)` selects travel dates
- `search()` triggers flight search
- `get_cheapest_flight()` extracts FlightResult from results
- CAPTCHA detection raises CaptchaDetected exception
- XPath-based selectors for resilience

**Implementation Details:**
1. Create `src/aventure_tracker/scrapers/google_flights.py`
2. Implement POM with private selectors
3. Handle cookie consent modal
4. Extract price using XPath on aria-labels
5. Parse airline, times from result cards
6. Generate booking link

**Test Requirements:**
- Test with mocked page content
- Test CAPTCHA detection
- Test FlightResult extraction

**Demo:**
Run scraper against Google Flights for a real search (requires network).

---

## Task 9: Instagram Scraper (Instaloader + Playwright Fallback)

**Requirements:** REQ-6, REQ-7, REQ-16

**Description:**
Implement InstagramScraper with Instaloader as primary method and Playwright as fallback.

**Acceptance Criteria:**
- `get_recent_posts(account, limit)` returns list of InstagramPost
- Primary: Instaloader fetches public profile posts
- Fallback: Playwright scrapes if Instaloader fails
- Rate limit handling for both methods
- Returns empty list + logs warning on total failure
- Extracts post ID, URL, image URLs, caption, timestamp

**Implementation Details:**
1. Create `src/aventure_tracker/scrapers/instagram.py`
2. Implement Instaloader wrapper with rate limit handling
3. Implement Playwright fallback with stealth
4. Add retry logic with exponential backoff
5. Parse post data from both sources into unified model

**Test Requirements:**
- Test Instaloader success path with mock
- Test fallback triggers when Instaloader fails
- Test rate limit detection and backoff
- Test post parsing from both methods

**Demo:**
```bash
python -c "from aventure_tracker.scrapers.instagram import InstagramScraper; import asyncio; s = InstagramScraper(); posts = asyncio.run(s.get_recent_posts('brutaltravel.co', 3)); print(posts)"
```

---

## Task 10: OCR Processor with Tesseract

**Requirements:** REQ-8

**Description:**
Implement OCRProcessor that extracts text from images using Tesseract with pre-processing for improved accuracy.

**Acceptance Criteria:**
- `download_image(url)` fetches image bytes
- `preprocess_image(bytes)` applies grayscale, threshold, scaling
- `extract_text(image)` runs Tesseract with Spanish language
- `process_post(post)` processes all images in a post
- Handles download failures gracefully
- Returns empty string on OCR failure

**Implementation Details:**
1. Create `src/aventure_tracker/services/ocr.py`
2. Implement image download with requests
3. Use Pillow for pre-processing pipeline
4. Configure pytesseract for Spanish
5. Add text cleaning (remove excess whitespace)

**Test Requirements:**
- Test pre-processing improves sample image
- Test Tesseract extracts known text
- Test download failure returns empty
- Test multiple images in post

**Demo:**
Download a Bungee Instagram image and extract visible text.

---

## Task 11: Inventory Manager

**Requirements:** REQ-9

**Description:**
Implement InventoryManager that manages done and wishlist YAML files for activity filtering.

**Acceptance Criteria:**
- `load_done()` returns set of completed activity strings
- `load_wishlist()` returns set of desired destination strings
- `matches_wishlist(text)` returns list of matched destinations
- `is_done(text)` checks if text matches any done entry
- Case-insensitive matching
- Handles missing files gracefully (returns empty set)

**Implementation Details:**
1. Create `src/aventure_tracker/services/inventory.py`
2. Create `config/done.yaml` example
3. Create `config/wishlist.yaml` example
4. Implement fuzzy matching for destinations
5. Normalize text for comparison

**Test Requirements:**
- Test wishlist matching with various cases
- Test done check excludes matched activities
- Test missing file returns empty set
- Test case-insensitive matching

**Demo:**
```bash
python -c "from aventure_tracker.services.inventory import InventoryManager; i = InventoryManager(); print(i.matches_wishlist('Viaje a Guatapé en Septiembre'))"
```

---

## Task 12: Flight Tracker Service

**Requirements:** REQ-1, REQ-4, REQ-5

**Description:**
Implement FlightTracker that orchestrates flight price checking, deal detection, and notifications.

**Acceptance Criteria:**
- `run()` checks all routes for upcoming weekends
- `is_good_deal()` evaluates threshold and drop conditions
- Sends notification when deal found
- Updates state with new prices
- Returns TrackerResult with stats
- Handles scraper failures gracefully

**Implementation Details:**
1. Create `src/aventure_tracker/services/flight_tracker.py`
2. Integrate DateCalculator, Scraper, State, Notifier
3. Implement deal detection logic
4. Add price history tracking
5. Log progress for debugging

**Test Requirements:**
- Test is_good_deal with various scenarios
- Test notification sent on good deal
- Test state updated after check
- Test scraper failure doesn't break flow

**Demo:**
Run FlightTracker in dry-run mode showing detected deals.

---

## Task 13: Activity Tracker Service

**Requirements:** REQ-6, REQ-9, REQ-10

**Description:**
Implement ActivityTracker that orchestrates Instagram monitoring, OCR, inventory matching, and notifications.

**Acceptance Criteria:**
- `run()` checks all configured Instagram accounts
- Skips already-seen posts using State
- Runs OCR on new post images
- Checks extracted text against inventory
- Sends notification for wishlist matches
- Updates state with seen posts
- Returns TrackerResult with stats

**Implementation Details:**
1. Create `src/aventure_tracker/services/activity_tracker.py`
2. Integrate InstagramScraper, OCR, Inventory, State, Notifier
3. Implement new post detection
4. Chain OCR → inventory check → notification
5. Handle OCR failures (skip post, log warning)

**Test Requirements:**
- Test new post detection logic
- Test OCR result feeds into inventory check
- Test notification sent on wishlist match
- Test done items are excluded

**Demo:**
Run ActivityTracker showing detected new activities.

---

## Task 14: Main Orchestrator and CLI

**Requirements:** REQ-13, REQ-14

**Description:**
Implement main.py orchestrator that coordinates all modules and provides CLI interface.

**Acceptance Criteria:**
- Detects execution environment (CI vs local)
- Initializes all services with configuration
- Runs FlightTracker and ActivityTracker
- CLI flags: `--flights-only`, `--activities-only`, `--dry-run`
- Global error handling with appropriate exit codes
- Structured logging with timestamps

**Implementation Details:**
1. Create `src/aventure_tracker/main.py`
2. Add argparse for CLI options
3. Initialize services in correct order
4. Run trackers with error recovery
5. Exit 0 in CI, exit 1 locally on errors
6. Configure logging format

**Test Requirements:**
- Test dry-run doesn't send notifications
- Test flights-only skips activities
- Test CI exit code is 0 on errors
- Test local exit code is 1 on errors

**Demo:**
```bash
python -m aventure_tracker.main --dry-run
```

---

## Task 15: GitHub Actions Workflow

**Requirements:** REQ-15

**Description:**
Create GitHub Actions workflow that runs the tracker on a schedule with all required dependencies.

**Acceptance Criteria:**
- Cron trigger every 6 hours
- Manual trigger via workflow_dispatch
- Python 3.11 setup
- Playwright with Chromium installation
- Tesseract with Spanish language pack
- Secrets for Telegram and GitHub Gist
- CI=true environment variable set

**Implementation Details:**
1. Create `.github/workflows/tracker.yml`
2. Configure cron schedule `0 */6 * * *`
3. Add workflow_dispatch trigger
4. Install system dependencies (Tesseract)
5. Install Python dependencies
6. Run playwright install
7. Execute main with secrets

**Test Requirements:**
- Validate YAML syntax
- Test workflow locally with act (optional)

**Demo:**
Push to repo, manually trigger workflow, verify execution.

---

## Task 16: Integration Testing and Documentation

**Requirements:** All

**Description:**
Create integration tests for scraper modules and complete project documentation.

**Acceptance Criteria:**
- Integration tests for Google Flights scraper (marked slow)
- Integration tests for Instagram scraper (marked slow)
- End-to-end test with mocked external services
- README.md with setup instructions
- Configuration documentation
- Troubleshooting guide

**Implementation Details:**
1. Create `tests/integration/test_scrapers.py`
2. Mark integration tests with `@pytest.mark.integration`
3. Create `tests/integration/test_e2e.py` with mocked services
4. Write README.md with full documentation
5. Document all configuration options
6. Add troubleshooting section

**Test Requirements:**
- Integration tests can be skipped with `-m "not integration"`
- E2E test runs full flow with mocks

**Demo:**
```bash
pytest tests/ -v  # All unit tests pass
pytest tests/ -v -m integration  # Integration tests run
```
