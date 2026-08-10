---
inclusion: always
---

# Python Testing Guidelines

## Testing Framework

This project uses **pytest** as the testing framework.

## Test Organization

```
tests/
├── __init__.py
├── conftest.py           # Shared fixtures
├── unit/                 # Unit tests (isolated, fast)
│   ├── __init__.py
│   ├── test_models.py
│   └── test_services.py
└── integration/          # Integration tests (may use external resources)
    ├── __init__.py
    └── test_api.py
```

## Naming Conventions

- Test files: `test_<module_name>.py`
- Test functions: `test_<what_is_being_tested>_<expected_behavior>`
- Test classes: `Test<ClassName>`

```python
# Good test names
def test_user_creation_with_valid_email():
    ...

def test_calculate_distance_returns_zero_for_same_point():
    ...

class TestUserService:
    def test_get_user_returns_none_for_invalid_id(self):
        ...
```

## Test Structure (Arrange-Act-Assert)

```python
def test_add_item_increases_count():
    # Arrange
    cart = ShoppingCart()
    item = Item(name="Widget", price=10.0)

    # Act
    cart.add_item(item)

    # Assert
    assert cart.item_count == 1
    assert cart.total == 10.0
```

## Fixtures

Use pytest fixtures for test setup and teardown:

```python
# conftest.py
import pytest
from aventure_tracker.models import User

@pytest.fixture
def sample_user() -> User:
    """Create a sample user for testing."""
    return User(id=1, name="Test User", email="test@example.com")

@pytest.fixture
def db_session():
    """Provide a database session for testing."""
    session = create_test_session()
    yield session
    session.rollback()
    session.close()
```

## Markers

Use markers to categorize tests:

```python
import pytest

@pytest.mark.slow
def test_large_data_processing():
    ...

@pytest.mark.integration
def test_external_api_call():
    ...
```

Run specific markers:
```bash
pytest -m "not slow"           # Skip slow tests
pytest -m integration          # Run only integration tests
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_models.py

# Run specific test
pytest tests/unit/test_models.py::test_user_creation

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

## Coverage Requirements

- Aim for >80% code coverage
- Focus on testing business logic, not boilerplate
- Don't test external libraries
