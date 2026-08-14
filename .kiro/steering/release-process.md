---
inclusion: auto
---

# Release Process — Adventure Tracker

## Repository

`https://github.com/NSnietol/aventure-tracker`

## Workflow Summary

```
feature branch → PR to main → Quality Gate passes → merge → tag release
```

## Quality Gate (required to merge)

Every PR to `main` must pass `.github/workflows/quality-gate.yaml`:
- Lint (ruff)
- Format check (ruff)
- Unit tests with 70% coverage minimum

No Playwright or Tesseract in the gate — scrapers are mocked.

## Scheduled Job

`.github/workflows/tracker.yaml` runs Mon/Wed/Fri at 8AM Colombia time.
Runs `--mode flights`: extracts inbox images → searches flights → sends email report.

## When Declaring a New Release

When the user says "this is v0.X" or "create a new version":

1. **Update `CHANGELOG.md`** — add a new section at the top:
   ```
   ## [0.X.0] - YYYY-MM-DD
   ### Added
   ### Fixed
   ### Changed
   ```
2. **Tag the release**:
   ```bash
   git tag -a v0.X.0 -m "v0.X.0: brief description"
   git push origin v0.X.0
   ```
3. **Create GitHub release** from the tag with CHANGELOG entry as description.

## CHANGELOG Rules

- Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
- Versioning: [Semantic Versioning](https://semver.org/)
- One line per change, grouped by: Added / Fixed / Changed / Removed
- Date in ISO format (YYYY-MM-DD)

## Version Numbering

- `0.X.0` — feature releases (new capabilities)
- `0.X.Y` — patch releases (bug fixes only)
- `1.0.0` — production-ready

## GitHub Secrets Required

| Secret | Purpose |
|--------|---------|
| `RESEND_API_KEY` | Email notifications |
| `EMAIL_TO` | Recipient email |
| `GEMINI_API_KEY` | Image event extraction |
| `GIST_ID` | State persistence in CI |
| `GIST_TOKEN` | GitHub PAT with gist scope |
