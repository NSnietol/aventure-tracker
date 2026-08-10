---
inclusion: always
---

# Task Completion Workflow

## Required Steps After Each Task

When completing any task in this project, you MUST follow this workflow:

### 1. Run Unit Tests

Before committing, always run the test suite to verify nothing is broken:

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short
```

- All tests MUST pass before proceeding
- If tests fail, fix the issues before committing
- Do not skip this step

### 2. Create a Commit

After tests pass, create a commit with changes from the completed task:

```bash
git add <specific-files>
git commit -m "<type>(<scope>): <description>"
```

Follow Conventional Commits format:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring
- `test`: Adding/modifying tests
- `docs`: Documentation changes
- `chore`: Maintenance tasks

### Example Workflow

```bash
# 1. Run tests
source .venv/bin/activate && pytest tests/ -v --tb=short

# 2. If tests pass, stage and commit
git add src/aventure_tracker/models/adventure.py tests/unit/test_adventure.py
git commit -m "feat(models): add Adventure model with validation"
```

## Important Rules

1. **Never skip tests** - Every task completion requires test validation
2. **Atomic commits** - Each task should result in one focused commit
3. **Descriptive messages** - Commit messages should clearly describe what was done
4. **Stage specific files** - Prefer staging specific files over `git add -A`
