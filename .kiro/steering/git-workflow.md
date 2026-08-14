---
inclusion: auto
---

# Git Workflow — Adventure Tracker

## Repository

`git@github.com:NSnietol/aventure-tracker.git`

---

## Before Every Commit

Run tests and make sure they pass:

```bash
source .venv/bin/activate
pytest tests/ -v --tb=short
```

Then commit with conventional commits format:

```bash
git add <specific-files>
git commit -m "type(scope): description"
```

Types: `feat`, `fix`, `refactor`, `docs`, `ci`, `chore`, `test`

---

## Branch Strategy

- `main` — stable, deployed to CI nightly
- `feat/<description>` — new features
- `fix/<description>` — bug fixes
- `chore/<description>` — maintenance

Direct pushes to `main` are allowed for this personal project.
For larger changes, use a feature branch and PR.

---

## Before Pushing

1. Run full test suite: `pytest tests/ -v --tb=short`
2. Check no secrets are staged: `git diff --cached | grep -i "api_key\|token\|password"`
3. Push: `git push -u origin main`

---

## CI Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yaml` | push/PR to main | Runs tests on Python 3.12 + 3.13, linting |
| `tracker.yaml` | Daily 8AM Colombia + manual | Full tracker run (flights + extraction) |
| `flights-only.yaml` | 7AM + 7PM Colombia + manual | Only flight tracking |

Required GitHub secrets: `RESEND_API_KEY`, `EMAIL_TO`, `GIST_ID`, `GIST_TOKEN`, `GEMINI_API_KEY`

---

## Commit Message Examples

```
feat(airlines): add Wingo and JetSMART with 150K threshold
fix(email): segment report by weekend not by flat list
chore(config): update price threshold to 300K COP
docs: rewrite README with correct commands
test(pairing): add weekend pairing logic tests
```
