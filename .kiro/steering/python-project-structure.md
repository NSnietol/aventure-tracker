---
inclusion: always
---

# Python Project Structure

## Directory Layout

This project follows the `src` layout pattern:

```
aventure-tracker/
├── .kiro/
│   └── steering/          # Kiro steering files
├── src/
│   └── aventure_tracker/  # Main package
│       ├── __init__.py
│       ├── main.py        # Application entry point
│       ├── config.py      # Configuration management
│       ├── models/        # Data models
│       ├── services/      # Business logic
│       ├── api/           # API layer (if applicable)
│       └── utils/         # Utility functions
├── tests/
│   ├── __init__.py
│   ├── conftest.py        # Pytest fixtures
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── docs/                  # Documentation
├── scripts/               # Utility scripts
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml         # Project configuration
├── requirements.txt       # Production dependencies
└── requirements-dev.txt   # Development dependencies
```

## Module Organization

### When to Create a New Module

- When functionality is logically distinct
- When a file exceeds ~300-400 lines
- When code can be reused across the application

### Module Naming

- Use lowercase names with underscores
- Be descriptive but concise
- Avoid generic names like `utils.py`, `helpers.py` (unless truly generic)

## Package Imports

The main package should expose a clean public API:

```python
# src/aventure_tracker/__init__.py
from aventure_tracker.main import main
from aventure_tracker.config import Settings

__version__ = "0.1.0"
__all__ = ["main", "Settings", "__version__"]
```

## Entry Points

For CLI applications, define entry points in `pyproject.toml`:

```toml
[project.scripts]
aventure-tracker = "aventure_tracker.main:main"
```

## Configuration Files

- `pyproject.toml`: Primary configuration (project metadata, tools)
- `requirements.txt`: Production dependencies (pip)
- `requirements-dev.txt`: Development dependencies
- `.pre-commit-config.yaml`: Pre-commit hook configuration
