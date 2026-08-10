---
inclusion: always
---

# Python Dependency Management

## Virtual Environment

This project uses Python's built-in `venv` module:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Verify activation
which python  # Should point to .venv/bin/python
```

## Installing Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (includes production)
pip install -r requirements-dev.txt

# Install package in editable mode
pip install -e .

# Install with dev extras
pip install -e ".[dev]"
```

## Adding Dependencies

### Production Dependencies

1. Add to `requirements.txt` with version constraint
2. Add to `pyproject.toml` under `[project.dependencies]`

```txt
# requirements.txt
requests>=2.31.0,<3.0.0
pydantic>=2.0.0,<3.0.0
```

### Development Dependencies

1. Add to `requirements-dev.txt`
2. Add to `pyproject.toml` under `[project.optional-dependencies.dev]`

## Version Constraints

Use appropriate version constraints:

- `>=X.Y.Z` - Minimum version (use sparingly)
- `>=X.Y.Z,<X+1.0.0` - Compatible release (recommended)
- `~=X.Y.Z` - Compatible release shorthand
- `==X.Y.Z` - Exact version (for reproducibility)

## Updating Dependencies

```bash
# Check outdated packages
pip list --outdated

# Upgrade a specific package
pip install --upgrade <package>

# Upgrade all packages (be careful)
pip install --upgrade -r requirements.txt
```

## Lock Files (Optional)

For reproducible builds, consider using pip-tools:

```bash
pip install pip-tools

# Generate lock file
pip-compile requirements.txt -o requirements.lock

# Install from lock file
pip install -r requirements.lock
```

## Best Practices

1. **Pin major versions** to avoid breaking changes
2. **Document why** unusual dependencies are included
3. **Keep dependencies minimal** - don't add what you don't need
4. **Update regularly** - don't let dependencies go stale
5. **Test after updates** - run full test suite after dependency changes
