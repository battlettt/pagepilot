# PagePilot

PagePilot is a local-only browser automation agent for the command line.
You give it a plain-English task. It turns the task into an explicit,
numbered step plan, prints the whole plan before anything runs, asks you to
confirm, and then runs it in a real browser on your machine. Any step that
cannot be undone stops and waits for you to type `yes`.

There is no server, no hosted version, no account, and no telemetry. The
only network traffic is the browser loading the pages your plan names.

## Install

PagePilot is plain Python 3 (3.9 or newer) plus one real dependency:
[Playwright](https://playwright.dev/python/), which drives the browser.

```sh
pip install playwright
playwright install chromium
```

Or, from this directory, `pip install -e .` (pyproject.toml declares the
Playwright dependency), then `playwright install chromium`.

Everything except actually running a plan (planning, dry runs, recipes,
tests, the demo) works without Playwright installed.

## Usage

```sh
python3 -m pagepilot "check my order status"            # plan, confirm, run with gates
python3 -m pagepilot --dry-run "check my order status"  # print the plan, exit, no browser
python3 -m pagepilot --list-recipes                     # list saved recipes
python3 -m pagepilot --recipe site-search --param query=lamps
python3 -m pagepilot --help                             # every option
```

Useful options: `--yes` skips only the "Run this plan?" question (gates
still ask), `--headless` hides the window, `--timeout` sets seconds to wait
for each element (default 10), `--step-delay` sets seconds between steps
(default 0.5), `--runs-dir` changes where run data goes, `--profile DIR`
opts in to a persistent browser profile.

### Task language

Clauses are joined with `then`. The first clause must open a page.

| You write | Step |
|-----------|------|
| `go to URL`, `open URL`, `visit URL` | goto |
| `click X`, `press X` | click |
| `fill VALUE into X`, `fill X with VALUE` | fill |
| `select VALUE from X` | select |
| `wait for X` | wait_for |
| `take a screenshot` | screenshot |
| `extract text of X`, `read X` | extract_text |
| `sign in`, `submit`, `pay`, `place order`, `send`, `delete X` | gated click |

Example: `go to https://example.com then click "More information" then take a screenshot`

A task that matches a recipe trigger (such as "check my order status") uses
that recipe. A task PagePilot does not understand produces no plan and a
message asking you to rephrase. It never guesses an action list.

### Recipes

Recipes are JSON files in `recipes/` with a name, description, optional
trigger phrases, parameters with defaults, and a step template using
`{param}` placeholders. Shipped examples (example.com placeholders, no
personal data): `order-status`, `site-search`, `contact-form`. A step can
set `"irreversible": true` to force a gate.

## Human gates

These steps are always IRREVERSIBLE and stop for an explicit `yes` on the
terminal before they run:

- sign-in (log in, submit credentials)
- payment (pay, buy, purchase, checkout, place order)
- submit (form submission, confirm, register)
- send (send a message or email, post, publish, reply)
- delete (delete, remove, cancel order, close account)
- any step marked `"irreversible": true` in a plan or recipe

Anything other than `y` or `yes`, including no input at all, means no. A
declined gate stops the run cleanly, and the log records where it stopped.
`--yes` does not skip gates. `--dry-run` prints the plan and exits without
importing the executor, launching a browser, or writing any file.

## How it runs a step

- Selectors are resolved by trying strategies in order: exact accessible
  role and name, CSS selector, visible text, form label, then attribute
  fallback (aria-label, placeholder, name, title). The strategy that worked
  is recorded in the log.
- Elements must be visible before PagePilot acts. A failed step retries up
  to 3 times with increasing delays (1s, 2s, 4s), then the run stops. An
  irreversible step is never retried once the action was attempted.
- There is a pause between steps (default 0.5s) so a site is never hammered.

## Audit trail

Each real run writes `runs/<run-id>/` with `log.json` (planned steps and
per-step outcome: status, strategy, retries, screenshot, extracted text,
errors), `report.md` (final report, including what actually changed or a
plain statement that nothing changed), and one `step-NN.png` screenshot per
executed step. The report is also printed. `runs/` is gitignored runtime
data; never commit it.

## Safety rules

- PagePilot never asks for, stores, logs, or types a password. It refuses
  plans that fill passwords, PINs, card numbers, or similar secrets.
  Credentials never go in recipes, logs, or screenshots.
- By default each run uses a fresh browser context with no saved logins.
  To use your own existing session, opt in with `--profile DIR` and sign in
  yourself in that browser.
- No CAPTCHA solving. If a CAPTCHA appears, the run pauses and asks you to
  solve it yourself in the browser window, or it stops. In `--headless`
  mode it always stops.
- Respect site rules. PagePilot only visits URLs written in your plan and
  has no crawling mode. Do not use it to spam, to scrape behind a login you
  do not own, or to get around access controls. If you script anything
  crawl-like on top of it, obey robots.txt and keep the rate limit.

## Demo

`demo/index.html` is a static sample audit report built from a mock run
(the real planner, gates, executor, and audit code against a fake page).
Regenerate it with `python3 scripts/build_demo.py`. A test fails if the page
drifts from `demo/mock_run.json`.

## Tests

```sh
python3 tests/run_tests.py
```

Plain asserts, no pytest. The exit code is 0 only if every test passes. The
one live-browser test (`tests/test_live_browser.py`) is reported as SKIP when
Playwright or Chromium is missing; everything else runs without a browser.

## Honest limits

- The planner is rule based, not an AI model. It understands the task
  language above and recipe triggers, nothing more.
- Gate detection uses step kinds and keywords on click targets. A button
  labelled with an unusual word could slip past keyword detection, so mark
  such steps `"irreversible": true` in recipes.
- "What changed" is reported from the steps that ran. PagePilot cannot see
  server-side effects, so clicks are reported as "may change" the page.
- Chromium only in v1. Recipes are read from this checkout's `recipes/`.
- robots.txt is not fetched, because v1 never crawls.
