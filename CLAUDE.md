# PagePilot

Local-only browser automation CLI. Plain-English task -> explicit plan ->
printed and confirmed -> executed with Playwright behind human gates.

## Layout

- `pagepilot/planner.py`: task string or recipe -> `Plan` of `Step`s. Pure.
- `pagepilot/gates.py`: REVERSIBLE / IRREVERSIBLE classification. Pure.
- `pagepilot/locators.py`: ordered selector strategies (role, css, text,
  label, attribute). Pure; works on any page-like object. Not named
  `selectors.py` because that would shadow the stdlib module asyncio uses.
- `pagepilot/recipes.py`: load JSON recipes, fill `{param}` templates. Pure.
- `pagepilot/audit.py`: log.json, report.md, screenshot paths. Pure.
- `pagepilot/executor.py`: runs a plan; imports Playwright only in
  `open_browser()`.
- `pagepilot/fakepage.py`: fake page for tests and the demo mock run.
- `pagepilot/__main__.py`: CLI. `main(argv, input_fn, out, run_fn)` is
  injectable for tests.
- `recipes/*.json`, `demo/`, `scripts/build_demo.py`, `tests/`.

## Commands

- Tests: `python3 tests/run_tests.py` (plain asserts, no pytest).
- Dry run: `python3 -m pagepilot --dry-run "check my order status"`
- Demo: `python3 scripts/build_demo.py` after any change to planner,
  gates, executor, audit, or the contact-form recipe, or the drift test fails.

## Rules that must not regress

- Every browser action appears in the printed plan before it runs.
- Irreversible steps (signin, payment, submit, send, delete, marked) always
  ask "yes" on the terminal. `--yes` never skips them.
- `--dry-run` never imports the executor or Playwright and writes nothing.
- Unknown tasks give an empty clarify plan, never a guessed action list.
- Never fill passwords, card numbers, or other secrets. Never solve CAPTCHAs.
- Irreversible actions are never retried once the action was attempted.
- `runs/` is runtime data and gitignored. No personal data in recipes.
- No em dashes in docs or output text.
- Only third-party dependency: Playwright. Standard library otherwise.
