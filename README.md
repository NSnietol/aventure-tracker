# Adventure Tracker

Zero-cost orchestrator for tracking cheap flights and Instagram adventure activities, with Telegram notifications and GitHub Gist state persistence.

## Features

- **Flight Tracking**: Monitor Google Flights for cheap weekend trips (BAQ/CTG→MDE)
- **Activity Tracking**: Scrape Instagram accounts for adventure deals
- **Smart Notifications**: Telegram alerts for prices below threshold or significant drops
- **State Persistence**: GitHub Gist storage for tracking price history
- **Colombian Holidays**: Built-in support for puentes (bridge weekends)
- **OCR Processing**: Extract activity details from Instagram images
- **Zero Cost**: Runs on GitHub Actions free tier

## Architecture

```
aventure-tracker/
├── src/aventure_tracker/
│   ├── config.py           # Settings with env vars
│   ├── main.py             # CLI and orchestrator
│   ├── models/             # Pydantic data models
│   ├── services/           # Business logic
│   │   ├── flight_tracker.py
│   │   ├── activity_tracker.py
│   │   ├── flight_dates.py
│   │   ├── holidays.py
│   │   ├── inventory.py
│   │   └── ocr.py
│   ├── scrapers/           # Web scraping
│   │   ├── base.py
│   │   ├── google_flights/
│   │   └── instagram/
│   └── infrastructure/     # External services
│       ├── notifier.py
│       └── state_manager.py
├── config/                 # YAML configuration
├── tests/                  # Unit and integration tests
└── .github/workflows/      # CI/CD automation
```

## Quick Start

### Prerequisites

- Python 3.12+
- Tesseract OCR with Spanish support
- Playwright browsers

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/aventure-tracker.git
cd aventure-tracker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Install Tesseract (macOS)
brew install tesseract tesseract-lang

# Install Tesseract (Ubuntu)
sudo apt-get install tesseract-ocr tesseract-ocr-spa
```

### Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:
```env
# Telegram Bot (from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# GitHub Gist (for state persistence)
GITHUB_GIST_ID=your_gist_id
GITHUB_GIST_TOKEN=your_pat_with_gist_scope
```

3. Configure tracking in `config/`:
   - `routes.yaml` - Flight routes and price thresholds
   - `accounts.yaml` - Instagram accounts to monitor
   - `wishlist.yaml` - Desired destinations
   - `done.yaml` - Completed activities
   - `holidays.yaml` - Colombian holidays for puentes

### Running Locally

```bash
# Run all trackers
aventure-tracker

# Run only flight tracking
aventure-tracker --mode flights

# Run only activity tracking
aventure-tracker --mode activities

# Check fewer weeks ahead
aventure-tracker --weeks 4

# Verbose logging
aventure-tracker --verbose

# Dry run (no notifications)
aventure-tracker --dry-run
```

## Configuration Files

### routes.yaml

```yaml
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 150000  # Alert below this price (COP)
    drop_percentage: 15      # Alert on 15%+ price drop
  - origin: CTG
    destination: MDE
    price_threshold: 150000
    drop_percentage: 15
```

### accounts.yaml

```yaml
accounts:
  - username: viajeros_colombia
    name: Viajeros Colombia
    enabled: true
  - username: adventure_tours
    name: Adventure Tours
    enabled: true
```

### wishlist.yaml

```yaml
destinations:
  - Guatapé
  - Santa Marta
  - San Gil
  - Salento
  - Cartagena
```

### holidays.yaml

```yaml
holidays:
  2025:
    - date: "2025-01-06"
      name: "Reyes Magos"
    - date: "2025-03-24"
      name: "San José"
    # ... more holidays
```

## GitHub Actions

### Scheduled Runs

The tracker runs automatically via GitHub Actions:

| Workflow | Schedule | Description |
|----------|----------|-------------|
| `tracker.yaml` | Daily 8 AM COL | Full tracking (flights + activities) |
| `flights-only.yaml` | 7 AM, 7 PM COL | Flight prices only |

### Manual Triggers

You can also trigger runs manually from the Actions tab with custom parameters.

### Required Secrets

Add these secrets to your GitHub repository:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GIST_ID`
- `GIST_TOKEN`

## Development

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit -v

# Integration tests only
pytest tests/integration -v -m integration

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality

```bash
# Linting
ruff check src/ tests/

# Formatting
ruff format src/ tests/

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

### Project Structure

| Directory | Purpose |
|-----------|---------|
| `src/aventure_tracker/models/` | Pydantic models for flights, activities, state |
| `src/aventure_tracker/services/` | Business logic and orchestration |
| `src/aventure_tracker/scrapers/` | Playwright-based web scrapers |
| `src/aventure_tracker/infrastructure/` | External service integrations |
| `tests/unit/` | Unit tests with mocks |
| `tests/integration/` | Integration tests |

## How It Works

### Flight Tracking

1. **FlightDateCalculator** generates upcoming weekend dates
2. **HolidayService** identifies puentes (bridge weekends)
3. **GoogleFlightsScraper** fetches prices from Google Flights
4. **FlightTrackerService** compares prices against thresholds
5. **TelegramNotifier** sends alerts for good deals
6. **StateManager** persists price history to GitHub Gist

### Activity Tracking

1. **InstagramScraper** fetches recent posts from monitored accounts
2. **OCRProcessor** extracts activity details from images
3. **InventoryManager** matches against wishlist/done lists
4. **ActivityTrackerService** generates alerts for new activities
5. **TelegramNotifier** sends activity alerts

## Travel Pattern

The tracker is configured for weekend trips with this pattern:

**Outbound:**
- Thursday evening (after 6 PM)
- Friday daytime (before 4 PM)

**Return:**
- Sunday afternoon (after 2 PM)
- Monday morning (before 10 AM)

This maximizes time at the destination while minimizing work impact.

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest tests/ -v`
4. Submit a pull request

## Acknowledgments

- [Playwright](https://playwright.dev/) for browser automation
- [Instaloader](https://instaloader.github.io/) for Instagram scraping
- [Tesseract](https://github.com/tesseract-ocr/tesseract) for OCR
- [Nager.Date](https://date.nager.at/) for holiday API fallback
