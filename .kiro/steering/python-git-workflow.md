---
inclusion: always
---

# Git Workflow Guidelines

## Branch Naming

Use descriptive branch names with prefixes:

- `feature/<description>` - New features
- `fix/<description>` - Bug fixes
- `refactor/<description>` - Code refactoring
- `docs/<description>` - Documentation changes
- `test/<description>` - Test additions or changes

Examples:
- `feature/user-authentication`
- `fix/login-validation-error`
- `refactor/database-queries`

## Commit Messages

Follow the Conventional Commits specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring (no feature or fix)
- `test`: Adding or modifying tests
- `chore`: Maintenance tasks (dependencies, configs)

### Examples

```
feat(auth): add user login endpoint

fix(api): handle null response from external service

docs: update README with installation instructions

refactor(models): simplify user validation logic

test(services): add unit tests for payment processing

chore(deps): update pytest to 8.1.0
```

## Pre-commit Hooks

This project uses pre-commit for automated checks:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: []
```

Setup:
```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

## Workflow

1. Create a feature branch from `main`
2. Make changes and commit frequently
3. Run tests locally before pushing
4. Push and create a pull request
5. Address review comments
6. Merge after approval

## Virtual Environment

Always activate the virtual environment before working:

```bash
# Activate
source .venv/bin/activate

# Deactivate when done
deactivate
```
