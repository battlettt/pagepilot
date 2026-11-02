"""Regenerate demo/mock_run.json and demo/index.html from a MOCK run.

The mock run uses the real planner, gates, executor, and audit code against
a fake page (pagepilot/fakepage.py). No browser is launched.

  python3 scripts/build_demo.py           rewrite the demo files
  python3 scripts/build_demo.py --check   exit 1 if the demo files drifted
"""

import html
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pagepilot import audit, gates, planner, recipes  # noqa: E402
from pagepilot.executor import Executor  # noqa: E402
from pagepilot.fakepage import FakePage  # noqa: E402

DEMO_DIR = os.path.join(ROOT, "demo")
MOCK_JSON = os.path.join(DEMO_DIR, "mock_run.json")
INDEX_HTML = os.path.join(DEMO_DIR, "index.html")
CLOCK = "2026-11-02T09:00:00Z"
ATTR_MESSAGE = 'css:[aria-label*="Message" i], [placeholder*="Message" i], [name*="Message" i], [title*="Message" i]'


def mock_run():
    """Run the contact-form recipe against a fake page and decline the submit gate."""
    recipe = recipes.load_recipes()["contact-form"]
    plan = planner.plan_recipe(recipe)
    page = FakePage(
        matches={"role:textbox:Name": 1, "role:combobox:Topic": 1, ATTR_MESSAGE: 1, "role:button:Submit": 1},
        fail={ATTR_MESSAGE: 1},  # first fill attempt times out, the retry succeeds
    )
    run_dir = tempfile.mkdtemp(prefix="pagepilot-demo-")
    try:
        log = audit.AuditLog(plan, run_dir, "demo-contact-form", clock=lambda: CLOCK)
        result, _ = Executor(page, log, approve=lambda prompt: False, sleep=lambda s: None,
                             out=lambda *a: None).run(plan)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    return result


def _rows(items, cells):
    return "\n".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in cells(i)) + "</tr>"
                     for i in items)


def render_html(log):
    e = html.escape
    planned = _rows(log["planned"], lambda s: [
        s["step"], s["action"], s["description"],
        "IRREVERSIBLE, needs approval" if s["classification"] == "IRREVERSIBLE" else "reversible"])
    outcomes = _rows(log["outcomes"], lambda o: [
        o["step"], o["action"], o["status"], o["strategy"] or "-", o["retries"],
        o["screenshot"] or "-", o["error"] or ""])
    gate = next((o for o in log["outcomes"] if o["status"] == "stopped_at_gate"), None)
    gate_html = ""
    if gate:
        fields = {k: v for k, v in log["planned"][gate["step"] - 1].items() if k not in ("step", "classification")}
        prompt = gates.approval_prompt(planner.Step(**fields), gate["step"]).strip() + " no"
        gate_html = (
            "<h2>Gate stop</h2>\n<div class=\"gate\">"
            f"<p>Step {gate['step']} ({e(gate['description'])}) is IRREVERSIBLE. PagePilot stopped and asked:</p>"
            f"<pre>{e(prompt)}</pre>"
            f"<p>The answer was no, so step {gate['step']} and every later step did not run.</p></div>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PagePilot sample audit report</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1d1d1f; line-height: 1.5; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.92rem; }}
th, td {{ border: 1px solid #d0d0d7; padding: 0.35rem 0.5rem; text-align: left; vertical-align: top; }}
th {{ background: #f2f2f5; }}
pre {{ background: #f6f6f8; padding: 0.8rem; overflow-x: auto; white-space: pre-wrap; }}
.note {{ background: #fff8e1; border-left: 4px solid #e0a800; padding: 0.6rem 0.8rem; }}
.gate {{ border-left: 4px solid #c62828; padding: 0.2rem 0.8rem; background: #fdecea; }}
</style>
</head>
<body>
<h1>PagePilot sample audit report</h1>
<p class="note">This is a static page and cannot automate a browser; it shows the saved report from a mock run that used a fake page.</p>
<p>Task: <strong>{e(log['task'])}</strong> (source: {e(log['source'])}). Result: <strong>{e(log['final_status'])}</strong>. {e(log['message'])}</p>
<h2>Plan (printed before anything ran)</h2>
<table>
<tr><th>#</th><th>Action</th><th>Description</th><th>Gate</th></tr>
{planned}
</table>
<h2>Per-step outcomes</h2>
<table>
<tr><th>#</th><th>Action</th><th>Status</th><th>Strategy</th><th>Retries</th><th>Screenshot</th><th>Notes</th></tr>
{outcomes}
</table>
{gate_html}
<h2>Final report</h2>
<pre>{e(audit.render_report(log))}</pre>
<p>Regenerate with <code>python3 scripts/build_demo.py</code>. Source data: <code>demo/mock_run.json</code>.</p>
</body>
</html>
"""


def mock_json(log):
    return json.dumps(log, indent=2) + "\n"


def main(argv):
    log = mock_run()
    expected = {MOCK_JSON: mock_json(log), INDEX_HTML: render_html(log)}
    if "--check" in argv:
        drifted = [p for p, text in expected.items()
                   if not os.path.exists(p) or open(p, encoding="utf-8").read() != text]
        for p in drifted:
            print(f"drift: {os.path.relpath(p, ROOT)} is out of date, run python3 scripts/build_demo.py")
        return 1 if drifted else 0
    os.makedirs(DEMO_DIR, exist_ok=True)
    for path, text in expected.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
