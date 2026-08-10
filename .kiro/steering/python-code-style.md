---
inclusion: always
---

# Python Code Style Guidelines

## General Principles

- Follow PEP 8 style guidelines
- Write clean, readable, and self-documenting code
- Prefer explicit over implicit
- Keep functions and methods small and focused (single responsibility)

## Formatting

- Use 4 spaces for indentation (no tabs)
- Maximum line length: 88 characters (Black/Ruff default)
- Use double quotes for strings consistently
- Add trailing commas in multi-line collections

## Naming Conventions

- **Variables and functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private attributes**: prefix with single underscore `_private`
- **Module-level "dunder" names**: `__all__`, `__version__`

## Imports

- Group imports in this order:
  1. Standard library
  2. Third-party packages
  3. Local application imports
- Separate each group with a blank line
- Use absolute imports over relative imports
- Avoid wildcard imports (`from module import *`)

```python
# Good
import os
import sys
from typing import Optional

import requests
from pydantic import BaseModel

from aventure_tracker.models import User
```

## Type Hints

- Always use type hints for function signatures
- Use `Optional[T]` for values that can be `None`
- Use `list[T]`, `dict[K, V]` instead of `List[T]`, `Dict[K, V]` (Python 3.9+)
- Use `|` union syntax instead of `Union` (Python 3.10+)

```python
# Good
def get_user(user_id: int) -> User | None:
    ...

def process_items(items: list[str]) -> dict[str, int]:
    ...
```

## Documentation

- Use docstrings for all public modules, classes, and functions
- Follow Google-style docstrings format
- Document parameters, return values, and exceptions

```python
def calculate_distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    """Calculate the Euclidean distance between two points.

    Args:
        point_a: The first point as (x, y) coordinates.
        point_b: The second point as (x, y) coordinates.

    Returns:
        The distance between the two points.

    Raises:
        ValueError: If coordinates are invalid.
    """
    ...
```

## Error Handling

- Be specific with exception types (avoid bare `except:`)
- Use context managers for resource management
- Prefer EAFP (Easier to Ask for Forgiveness than Permission) over LBYL

```python
# Good
try:
    value = data["key"]
except KeyError:
    value = default_value

# With context manager
with open("file.txt") as f:
    content = f.read()
```
