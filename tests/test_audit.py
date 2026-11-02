"""Audit trail from mock runs with a fake page."""

import json
import os

from helpers import goto, plan_of, tempdir

from pagepilot import audit
from pagepilot.audit import AuditLog
from pagepilot.executor import Executor
from pagepilot.fakepage import FakePage
from pagepilot.planner import Step

STEPS = [
    goto(),
    Step("fill", "Search", "lamps", "Type lamps"),
    Step("click", "Go", selector="#go", description="Run search"),
    Step("wait_for", "Results", description="Wait for results"),
    Step("extract_text", "Results", description="Read results"),
    Step("screenshot", "page", description="Screenshot"),
]
PAGE = {"label:Search": 1, "css:#go": 1, "role:heading:Results": 1}


def mock_run(run_dir, steps, page, answers=()):
    answers = list(answers)
    plan = plan_of(*steps)
    log = AuditLog(plan, run_dir, "run-1", clock=lambda: "2026-01-01T00:00:00Z")
    ex = Executor(page, log, lambda p: bool(answers) and answers.pop(0) == "yes",
                  sleep=lambda s: None, out=lambda *a: None)
    return ex.run(plan)


def test_complete_run_log_and_report():
    page = FakePage(PAGE, texts={"role:heading:Results": "3 lamps found"})
    with tempdir() as d:
        run_dir = os.path.join(d, "run-1")
        log, report = mock_run(run_dir, STEPS, page)
        assert log["final_status"] == "completed"
        assert len(log["planned"]) == len(STEPS) == len(log["outcomes"])
        assert [o["status"] for o in log["outcomes"]] == ["success"] * 6
        assert [o["strategy"] for o in log["outcomes"]] == [None, "label", "css", "role", "role", None]
        assert log["outcomes"][4]["text"] == "3 lamps found"
        # one screenshot per executed step, on disk
        shots = [o["screenshot"] for o in log["outcomes"]]
        assert shots == [f"step-{i:02d}.png" for i in range(1, 7)]
        for s in shots:
            assert os.path.isfile(os.path.join(run_dir, s))
        # files written
        assert json.load(open(os.path.join(run_dir, "log.json"))) == log
        assert open(os.path.join(run_dir, "report.md")).read() == report
        assert "## Step outcomes" in report and "| 3 | click | success | css |" in report
        assert "Entered 'lamps' into 'Search'" in report
        assert "Clicked 'Go'" in report


def test_read_only_run_reports_nothing_changed():
    steps = [goto(), Step("extract_text", "Results", description="Read")]
    with tempdir() as d:
        run_dir = os.path.join(d, "run-1")
        log, report = mock_run(run_dir, steps, FakePage({"text:Results": 1}))
        assert log["changes"] == []
        assert "Nothing changed." in report


def test_gate_stop_is_recorded():
    steps = [goto(), Step("fill", "Name", "Sample User", "Name"),
             Step("click", "Submit", kind="submit", description="Submit"), Step("wait_for", "Thanks")]
    with tempdir() as d:
        run_dir = os.path.join(d, "run-1")
        log, report = mock_run(run_dir, steps, FakePage({"label:Name": 1, "role:button:Submit": 1}), ["no"])
        assert log["final_status"] == "stopped_at_gate"
        assert [o["status"] for o in log["outcomes"]] == ["success", "success", "stopped_at_gate", "skipped"]
        assert log["outcomes"][2]["error"] == "You declined this irreversible step"
        assert log["outcomes"][2]["screenshot"] is None
        assert "Stopped at the gate before step 3 (submit)" in report
        assert "| 3 | click | stopped_at_gate |" in report
        assert not any("IRREVERSIBLE" in c for c in log["changes"])
        assert sorted(os.listdir(run_dir)) == ["log.json", "report.md", "step-01.png", "step-02.png"]


def test_retries_with_backoff_then_success():
    page = FakePage({"role:button:Go": 1}, fail={"role:button:Go": 2})
    plan = plan_of(goto(), Step("click", "Go", description="Go"))
    sleeps = []
    with tempdir() as d:
        ex = Executor(page, AuditLog(plan, d), lambda p: True, sleep=sleeps.append,
                      out=lambda *a: None, step_delay=0.5, backoff=1.0)
        log, _ = ex.run(plan)
    assert log["outcomes"][1]["status"] == "success" and log["outcomes"][1]["retries"] == 2
    assert sleeps == [0.5, 1.0, 2.0]  # rate limit, then increasing backoff


def test_gives_up_after_three_retries():
    page = FakePage()
    plan = plan_of(goto(), Step("click", "Missing", description="Missing"), Step("click", "Later"))
    sleeps = []
    with tempdir() as d:
        ex = Executor(page, AuditLog(plan, d), lambda p: True, sleep=sleeps.append,
                      out=lambda *a: None, timeout_ms=0)
        log, report = ex.run(plan)
    assert log["final_status"] == "failed"
    assert log["outcomes"][1]["retries"] == 3 and "SelectorError" in log["outcomes"][1]["error"]
    assert log["outcomes"][2]["status"] == "skipped"
    assert [s for s in sleeps if s != 0.5] == [1.0, 2.0, 4.0]


def test_irreversible_action_is_never_retried_after_it_acted():
    page = FakePage({"role:button:Pay": 1}, fail={"role:button:Pay": 1})
    plan = plan_of(goto(), Step("click", "Pay", kind="payment", description="Pay"))
    with tempdir() as d:
        log, _ = Executor(page, AuditLog(plan, d), lambda p: True, sleep=lambda s: None,
                          out=lambda *a: None).run(plan)
    assert log["final_status"] == "failed" and log["outcomes"][1]["retries"] == 0
    assert page.actions.count(("click", "role:button:Pay")) == 1


def test_captcha_pauses_and_stops_when_not_solved():
    page = FakePage(captcha=True)
    plan = plan_of(goto(), Step("click", "Next"))
    asked = []
    with tempdir() as d:
        log, _ = Executor(page, AuditLog(plan, d), lambda p: True,
                          captcha_prompt=lambda m: asked.append(m) or False,
                          sleep=lambda s: None, out=lambda *a: None).run(plan)
    assert log["final_status"] == "stopped_captcha" and page.actions == []
    assert "Solve it yourself in the browser window" in asked[0]


def test_captcha_continues_after_user_solves_it():
    page = FakePage({"role:button:Next": 1}, captcha=True)

    def solved(msg):
        page.captcha = False
        return True

    plan = plan_of(goto(), Step("click", "Next"))
    with tempdir() as d:
        log, _ = Executor(page, AuditLog(plan, d), lambda p: True, captcha_prompt=solved,
                          sleep=lambda s: None, out=lambda *a: None).run(plan)
    assert log["final_status"] == "completed"


def test_run_id_is_filesystem_safe():
    rid = audit.make_run_id("Check my order status!")
    assert rid.endswith("-check-my-order-status") and "/" not in rid
