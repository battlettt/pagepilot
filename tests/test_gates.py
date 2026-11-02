"""Gate enforcement: prove PagePilot stops before irreversible steps."""

import os

from helpers import Recorder, goto, plan_of, tempdir

from pagepilot import __main__ as cli
from pagepilot import executor, gates, planner, recipes
from pagepilot.audit import AuditLog
from pagepilot.executor import Executor
from pagepilot.fakepage import FakePage
from pagepilot.planner import Step

GATED = {
    "signin": Step("click", "Sign in", kind="signin", description="Sign in"),
    "payment": Step("click", "Pay now", kind="payment", description="Pay"),
    "submit": Step("click", "Submit", kind="submit", description="Submit the form"),
    "send": Step("click", "Send", kind="send", description="Send the message"),
    "delete": Step("click", "Delete", kind="delete", description="Delete the item"),
}


def test_each_irreversible_kind_needs_approval():
    for kind, step in GATED.items():
        assert gates.needs_approval(step), kind
        assert gates.classify(step) == gates.IRREVERSIBLE, kind
        assert gates.irreversible_kind(step) == kind


def test_kind_alone_gates_even_with_harmless_target():
    for kind in gates.IRREVERSIBLE_KINDS:
        assert gates.needs_approval(Step("click", "OK", kind=kind)), kind


def test_click_targets_detected_without_kind():
    for target, kind in [("Sign in", "signin"), ("Log in", "signin"), ("Place order", "payment"),
                         ("Pay $20", "payment"), ("Submit", "submit"), ("Send message", "send"),
                         ("Delete account", "delete"), ("Buy now", "payment")]:
        step = Step("click", target)
        assert gates.irreversible_kind(step) == kind, target


def test_explicit_irreversible_flag():
    step = Step("click", "Archive", irreversible=True)
    assert gates.needs_approval(step)


def test_recipe_marked_irreversible_is_gated():
    recipe = {"name": "r", "description": "d", "steps": [
        {"action": "goto", "target": "https://example.com"},
        {"action": "click", "target": "Archive all", "irreversible": True},
    ]}
    plan = planner.plan_recipe(recipe)
    assert gates.needs_approval(plan.steps[1])


def test_planner_gated_verbs_need_approval():
    plan = planner.plan_task("go to https://example.com then sign in then pay then submit then send then delete the post")
    assert [gates.needs_approval(s) for s in plan.steps] == [False, True, True, True, True, True]


def test_reversible_steps_do_not_need_approval():
    for step in [goto(), Step("click", "Next page"), Step("fill", "Search", "send"),
                 Step("wait_for", "Submit"), Step("extract_text", "Delete history"),
                 Step("screenshot", "page")]:
        assert not gates.needs_approval(step), step


def test_only_explicit_yes_approves():
    for answer in ["y", "yes", " YES "]:
        assert gates.is_yes(answer)
    for answer in ["", "n", "no", "sure", "yess", None]:
        assert not gates.is_yes(answer)


def run_with(steps, answers, page=None):
    page = page or FakePage({"role:button:" + s.target: 1 for s in steps if s.action == "click"})
    rec = Recorder(answers)
    with tempdir() as d:
        audit = AuditLog(plan_of(*steps), os.path.join(d, "run"), "run")
        approve = lambda prompt: cli.ask(rec.input, prompt)
        log, report = Executor(page, audit, approve, sleep=lambda s: None, out=rec.out).run(plan_of(*steps))
    return page, rec, log, report


def test_declined_gate_stops_before_each_kind():
    for kind, step in GATED.items():
        after = Step("click", "Next", description="After the gate")
        page, rec, log, _ = run_with([goto(), step, after], ["no"])
        clicked = [a[1] for a in page.actions if a[0] == "click"]
        assert clicked == [], (kind, clicked)  # neither the gated step nor anything after ran
        assert len(rec.prompts) == 1 and "IRREVERSIBLE" in rec.prompts[0], kind
        assert log["final_status"] == "stopped_at_gate", kind
        assert [o["status"] for o in log["outcomes"]] == ["success", "stopped_at_gate", "skipped"], kind


def test_gate_is_asked_before_action_happens():
    page = FakePage({"role:button:Submit": 1})
    seen = []

    def approve(prompt):
        seen.append(list(page.actions))
        return True

    with tempdir() as d:
        plan = plan_of(goto(), GATED["submit"])
        Executor(page, AuditLog(plan, d), approve, sleep=lambda s: None, out=lambda *a: None).run(plan)
    assert seen == [[("goto", "https://example.com")]]
    assert ("click", "role:button:Submit") in page.actions


def test_no_answer_means_no():
    page, rec, log, _ = run_with([goto(), GATED["payment"]], [])  # EOF on stdin
    assert log["final_status"] == "stopped_at_gate"
    assert not [a for a in page.actions if a[0] == "click"]


def test_approved_gate_runs_and_is_reported_as_change():
    page, rec, log, report = run_with([goto(), GATED["send"]], ["yes"])
    assert ("click", "role:button:Send") in page.actions
    assert log["final_status"] == "completed"
    assert any("IRREVERSIBLE (send)" in c for c in log["changes"])


def test_each_gate_asked_separately():
    steps = [goto(), GATED["submit"], GATED["send"]]
    page, rec, log, _ = run_with(steps, ["yes", "no"])
    assert len(rec.prompts) == 2
    assert ("click", "role:button:Submit") in page.actions
    assert ("click", "role:button:Send") not in page.actions
    assert log["outcomes"][2]["status"] == "stopped_at_gate"


def test_yes_flag_does_not_skip_gates():
    calls = []

    def fake_run(plan, args, approve, captcha_prompt, out):
        calls.append(approve("gate?"))
        return 1

    rec = Recorder([])  # no answers: the gate must still ask, and EOF means no
    code = cli.main(["--yes", "go to https://example.com then submit"], rec.input, rec.out, fake_run)
    assert calls == [False] and rec.prompts == ["gate?"] and code == 1


def test_dry_run_never_invokes_executor_or_browser():
    called = []
    saved = (executor.open_browser, executor.Executor)
    executor.open_browser = lambda *a, **k: called.append("open_browser")
    executor.Executor = lambda *a, **k: called.append("Executor")
    try:
        for argv in (["--dry-run", "go to https://example.com then submit then pay"],
                     ["--dry-run", "check my order status"],
                     ["--dry-run", "--recipe", "contact-form"],
                     ["--dry-run", "--yes", "--recipe", "contact-form"]):
            rec = Recorder()
            code = cli.main(argv, rec.input, rec.out, lambda *a: called.append("run_fn"))
            assert code == 0, argv
            assert rec.prompts == [], argv  # did not even ask
    finally:
        executor.open_browser, executor.Executor = saved
    assert called == []


def test_declined_plan_never_invokes_executor():
    called = []
    rec = Recorder(["n"])
    code = cli.main(["--recipe", "order-status"], rec.input, rec.out, lambda *a: called.append(1))
    assert code == 1 and called == [] and "Nothing happened" in rec.text


def test_example_recipes_gate_their_submit():
    plan = planner.plan_recipe(recipes.load_recipes()["contact-form"])
    gated = [s.target for s in plan.steps if gates.needs_approval(s)]
    assert gated == ["Submit"]
