# CLAUDE.md — PagePilot

Local browser automation agent: plain-English tasks become explicit plans, with human gates and an audit trail.

## What it is
- Task language: a task in plain English becomes an explicit step plan shown before anything runs.
- Executor: resilient selectors (multiple strategies, self-healing), waits, retries with backoff.
- Human gates: stop and ask before sign-in, payment, submit, send, delete, or anything irreversible. Dry-run mode plans without acting.
- Audit trail: step log + screenshot per step + final report of what changed.
- Recipes: saved reusable tasks with parameters.
- Safety: credentials are never stored in the agent; it uses the browser's own saved logins or the user's session. Respect site rules, no CAPTCHA solving as a feature, rate-limit.

## Run
- `python3 -m pagepilot "check my order status"` (plan shown first, gates enforced).
- `python3 -m pagepilot --dry-run "..."` plans without acting.

## Test
- `python3 tests/run_tests.py` (planner on mock pages, selector fallback, gate enforcement, dry-run, audit logs).
- Gate tests must prove the agent stops before irreversible steps.

## Conventions
- Planner is separate from the executor, so plans are testable without a browser.
- No secrets, tokens, or passwords in the repo.
- Playwright for browser control; `playwright install chromium` if browsers are missing.
