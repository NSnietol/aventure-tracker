---
inclusion: always
---

# Documentation Updates

## When to Update README.md

Automatically update `README.md` when making changes that affect how the project works:

### Triggers for README Update

1. **New CLI flags or options** - Document in "Running" or relevant section
2. **New scripts** - Add to "Running" section with usage example
3. **New configuration files** - Document structure in "Configuration" section
4. **New data files** - Document in "Architecture" section
5. **New dependencies** (Ollama models, APIs, services) - Update "Prerequisites" and "Offline Capabilities"
6. **Changed workflows** - Update "How It Works" section
7. **New features** - Add to "Features" section

### What NOT to Trigger Updates

- Internal refactoring (no external behavior change)
- Bug fixes (unless they change documented behavior)
- Test-only changes
- Code style changes

## Update Process

When a README update is triggered:

1. **Identify the section** that needs updating
2. **Make minimal, focused changes** - Don't rewrite unrelated sections
3. **Keep consistent style** - Match existing formatting and tone
4. **Include examples** - Show usage with actual commands

## README Sections Reference

| Section | What it documents |
|---------|-------------------|
| Features | High-level capabilities |
| Quick Start > Prerequisites | Required software/models |
| Quick Start > Running | CLI commands and scripts |
| Configuration | YAML config files format |
| Architecture | Directory structure, data files |
| How It Works | Internal workflows |
| Offline Capabilities | What runs locally vs needs internet |

## Commit Convention

When updating README as part of a feature:
- Include README in the same commit as the feature
- Commit message: `feat(scope): description` (feature takes precedence)

When updating README standalone:
- Commit message: `docs: update README for <change>`
