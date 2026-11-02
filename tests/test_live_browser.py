"""LIVE BROWSER test: needs Playwright and an installed Chromium.

Skipped cleanly (reported as SKIP, never as a pass) when either is missing.
Uses a local file:// page, so it makes no network calls.
"""

import importlib.util
import os
import unittest

from helpers import Recorder, tempdir

from pagepilot import planner
from pagepilot.audit import AuditLog

PAGE = """<!doctype html><html><body>
<h1>Contact</h1>
<label>Name <input name="name"></label>
<label>Topic <select name="topic"><option>Sales</option><option>General</option></select></label>
<button id="go" onclick="document.getElementById('out').textContent='Hello ' +
  document.querySelector('input').value">Preview</button>
<p id="out" role="status"></p>
<button onclick="document.body.innerHTML='<h1>Sent</h1>'">Submit</button>
</body></html>"""


def open_live_page():
    if importlib.util.find_spec("playwright") is None:
        raise unittest.SkipTest("live browser: Playwright is not installed")
    from pagepilot import executor
    cm = executor.open_browser(headless=True)
    try:
        page = cm.__enter__()
    except Exception as e:
        raise unittest.SkipTest(f"live browser: Chromium could not launch ({str(e).splitlines()[0]})")
    return cm, page


def test_live_run_with_gate_stop():
    cm, page = open_live_page()
    from pagepilot.executor import Executor
    try:
        with tempdir() as d:
            html = os.path.join(d, "page.html")
            with open(html, "w") as f:
                f.write(PAGE)
            plan = planner.plan_task(
                f"go to file://{html} then fill Ada into Name then select General from Topic "
                "then click Preview then extract text of #out then submit")
            assert plan.ok, plan.clarify
            rec = Recorder(["no"])
            log, report = Executor(page, AuditLog(plan, os.path.join(d, "run")), lambda p: rec.input(p) == "yes",
                                   step_delay=0, out=rec.out).run(plan)
            assert log["outcomes"][4]["text"] == "Hello Ada", log["outcomes"]
            assert log["final_status"] == "stopped_at_gate"
            assert page.locator("text=Sent").count() == 0  # the submit never happened
            assert len([f for f in os.listdir(os.path.join(d, "run")) if f.endswith(".png")]) == 5
    finally:
        cm.__exit__(None, None, None)
