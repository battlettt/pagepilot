"""PagePilot command line.

  python3 -m pagepilot "task"                  plan, confirm, run with gates
  python3 -m pagepilot --dry-run "task"        plan only, no browser
  python3 -m pagepilot --list-recipes          list saved recipes
  python3 -m pagepilot --recipe NAME [--param k=v ...]
"""

import argparse
import importlib.util
import os
import sys

from . import gates, planner, recipes

EXIT_OK, EXIT_STOPPED, EXIT_NO_PLAN, EXIT_NO_BROWSER, EXIT_FAILED = 0, 1, 2, 3, 4

DESCRIPTION = """\
PagePilot turns a plain-English task into an explicit step plan, prints the
plan before anything runs, and then executes it in a real local browser.

Every browser action appears in the printed plan first. Irreversible steps
(sign-in, payment, submit, send, delete, or anything marked irreversible)
always stop and ask you 'yes' on the terminal, even with --yes.
"""

EPILOG = """\
examples:
  python3 -m pagepilot "check my order status"
  python3 -m pagepilot --dry-run "check my order status"
  python3 -m pagepilot --dry-run "go to https://example.com then click 'More information'"
  python3 -m pagepilot --list-recipes
  python3 -m pagepilot --recipe site-search --param query=lamps
  python3 -m pagepilot --recipe contact-form --param url=https://www.example.com/contact --dry-run

task language (clauses joined by 'then'):
  go to URL | click X | fill VALUE into X | select VALUE from X | wait for X |
  take a screenshot | extract text of X | sign in | submit | pay | send | delete X

exit codes: 0 done, 1 stopped by you (declined plan, gate, or CAPTCHA),
  2 no plan (unclear task, unknown recipe), 3 Playwright or browser missing,
  4 a step failed after retries.

Run data (log.json, report.md, step screenshots) goes to runs/<run-id>/.
PagePilot never asks for, stores, or types passwords, and never solves CAPTCHAs.
"""


def build_parser():
    p = argparse.ArgumentParser(prog="python3 -m pagepilot", description=DESCRIPTION, epilog=EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task", nargs="?", help="plain-English task, in quotes")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan and exit; no browser is launched and nothing is written")
    p.add_argument("--yes", action="store_true",
                   help="skip the 'run this plan?' question; irreversible-step gates still ask")
    p.add_argument("--list-recipes", action="store_true", help="list saved recipes and exit")
    p.add_argument("--recipe", metavar="NAME", help="run a saved recipe by name")
    p.add_argument("--param", action="append", default=[], metavar="K=V",
                   help="recipe parameter, repeatable")
    p.add_argument("--recipes-dir", default=recipes.DEFAULT_DIR, help="recipe directory (default: recipes/)")
    p.add_argument("--runs-dir", default="runs", help="where run logs and screenshots go (default: runs/)")
    p.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for each element (default: 10)")
    p.add_argument("--step-delay", type=float, default=0.5, help="seconds between steps (default: 0.5)")
    p.add_argument("--headless", action="store_true",
                   help="hide the browser window (CAPTCHAs then stop the run, since you cannot solve them)")
    p.add_argument("--profile", metavar="DIR",
                   help="opt in to a persistent browser profile in DIR to reuse your own saved logins")
    return p


def list_recipes(all_recipes, out):
    if not all_recipes:
        out("No recipes found.")
        return
    for name, r in sorted(all_recipes.items()):
        out(f"{name}: {r['description']}")
        for key, spec in r.get("params", {}).items():
            out(f"    --param {key}=...  (default: {spec.get('default', 'required')})")


def ask(input_fn, prompt):
    try:
        return gates.is_yes(input_fn(prompt))
    except EOFError:
        return False  # no terminal answer means no


def run_live(plan, args, approve, captcha_prompt, out):
    """Launch a real browser and execute the plan. Returns an exit code."""
    if importlib.util.find_spec("playwright") is None:
        out("Playwright is not installed. Run: pip install playwright && playwright install chromium")
        return EXIT_NO_BROWSER
    from . import audit, executor

    run_id = audit.make_run_id(plan.task)
    run_dir = os.path.join(args.runs_dir, run_id)
    try:
        with executor.open_browser(headless=args.headless, profile_dir=args.profile) as page:
            log = audit.AuditLog(plan, run_dir, run_id)
            ex = executor.Executor(page, log, approve, captcha_prompt,
                                   timeout_ms=int(args.timeout * 1000), step_delay=args.step_delay, out=out)
            result, report = ex.run(plan)
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
            out("No browser found for Playwright. Run: playwright install chromium")
            return EXIT_NO_BROWSER
        raise
    out("")
    out(report)
    out(f"Run log, report, and screenshots: {run_dir}")
    return {"completed": EXIT_OK, "failed": EXIT_FAILED}.get(result["final_status"], EXIT_STOPPED)


def main(argv=None, input_fn=input, out=print, run_fn=run_live):
    args = build_parser().parse_args(argv)
    try:
        all_recipes = recipes.load_recipes(args.recipes_dir)
        if args.list_recipes:
            list_recipes(all_recipes, out)
            return EXIT_OK
        if args.recipe:
            recipe = recipes.get_recipe(all_recipes, args.recipe)
            plan = planner.plan_recipe(recipe, recipes.parse_params(args.param))
        elif args.task:
            plan = planner.plan_task(args.task, all_recipes)
        else:
            out("Give a task in quotes, --recipe NAME, or --list-recipes. See --help.")
            return EXIT_NO_PLAN
    except (recipes.RecipeError, planner.PlanError) as e:
        out(f"Error: {e}")
        return EXIT_NO_PLAN

    out(planner.format_plan(plan))
    if not plan.ok:
        return EXIT_NO_PLAN
    if args.dry_run:
        out("Dry run: no browser launched, nothing executed, nothing written.")
        return EXIT_OK
    if not args.yes and not ask(input_fn, "\nRun this plan? [y/N] "):
        out("Not run. Nothing happened.")
        return EXIT_STOPPED

    approve = lambda prompt: ask(input_fn, prompt)
    captcha_prompt = None if args.headless else approve
    return run_fn(plan, args, approve, captcha_prompt, out)


if __name__ == "__main__":
    sys.exit(main())
