# Adventure Tracker

Zero-cost orchestrator for tracking cheap flights and adventure activities in Colombia.

## Features

- **Flight Tracking**: Monitor prices for weekend getaway flights (BAQ/CTG → MDE)
- **Activity Tracking**: Discover new adventure activities from Instagram accounts
- **Smart Notifications**: Telegram alerts for price drops and wishlist matches
- **Dual Execution**: Runs locally and on GitHub Actions
- **Anti-Detection**: Stealth scraping with Playwright

## Quick Start

### Prerequisites

- Python 3.11+
- Tesseract OCR with Spanish language pack
- Telegram Bot (create via @BotFather)
- GitHub Personal Access Token (for Gist storage)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd aventure-tracker

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit the YAML files in `config/`:

- `routes.yaml` - Flight routes to monitor
- `accounts.yaml` - Instagram accounts to follow
- `wishlist.yaml` - Destinations of interest
- `done.yaml` - Completed activities (excluded from alerts)
- `holidays.yaml` - Colombian holidays for bridge weekend detection

### Usage

```bash
# Run full tracker
python -m aventure_tracker.main

# Run only flight tracker
python -m aventure_tracker.main --flights-only

# Run only activity tracker
python -m aventure_tracker.main --activities-only

# Dry run (no notifications)
python -m aventure_tracker.main --dry-run
```

## Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run linter
ruff check src tests

# Format code
ruff format src tests
```

## License

MIT
