"""Planner: task strings to plans, no browser."""

import os
import subprocess
import sys

from pagepilot import planner, recipes
from pagepilot.planner import plan_task

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def actions(plan):
    return [(s.action, s.target, s.value) for s in plan.steps]


def test_pure_modules_never_import_playwright():
    code = ("import sys, pagepilot.planner, pagepilot.gates, pagepilot.locators, "
            "pagepilot.recipes, pagepilot.audit, pagepilot.executor, pagepilot.__main__; "
            "assert 'playwright' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_goto_click_screenshot():
    plan = plan_task('go to https://example.com then click "More information" then take a screenshot')
    assert plan.ok
    assert actions(plan) == [
        ("goto", "https://example.com", ""),
        ("click", "More information", ""),
        ("screenshot", "page", ""),
    ]
    assert all(s.description for s in plan.steps)


def test_all_action_types():
    plan = plan_task(
        "open example.com/shop then fill lamps into the Search field then select Blue from Color "
        "then wait for Results then extract text of Results then take a screenshot then click Next"
    )
    assert [s.action for s in plan.steps] == [
        "goto", "fill", "select", "wait_for", "extract_text", "screenshot", "click"
    ]
    assert plan.steps[0].target == "https://example.com/shop"
    assert (plan.steps[1].target, plan.steps[1].value) == ("Search", "lamps")
    assert (plan.steps[2].target, plan.steps[2].value) == ("Color", "Blue")


def test_fill_with_form_and_quotes():
    plan = plan_task("go to https://example.com; fill the Name field with 'Sample User'")
    assert actions(plan)[1] == ("fill", "Name", "Sample User")


def test_gated_verbs_get_kinds():
    plan = plan_task("go to https://example.com then sign in then submit then pay then send then delete the draft")
    assert [s.kind for s in plan.steps] == ["", "signin", "submit", "payment", "send", "delete"]
    assert all(s.action == "click" for s in plan.steps[1:])


def test_unknown_task_is_clarify_not_guess():
    for task in ["book me a flight to Paris", "make me rich", "", "   ", "check my order status"]:
        plan = plan_task(task)  # no recipes given
        assert not plan.ok, task
        assert plan.steps == [], task
        assert plan.clarify, task


def test_one_unknown_clause_rejects_whole_plan():
    plan = plan_task("go to https://example.com then do something clever then click OK")
    assert plan.steps == [] and "do something clever" in plan.clarify


def test_plan_must_start_with_goto():
    plan = plan_task("click Login")
    assert plan.steps == [] and "opening a page" in plan.clarify


def test_bad_url_is_clarify():
    plan = plan_task("go to nowhere then click OK")
    assert plan.steps == [] and "not a URL" in plan.clarify


def test_refuses_to_fill_passwords_and_cards():
    for field in ["Password", "card number", "CVV", "PIN"]:
        plan = plan_task(f"go to https://example.com then fill hunter2 into {field}")
        assert plan.steps == [], field
        assert "never enters credentials" in plan.clarify


def test_trigger_matches_recipe():
    plan = plan_task("check my order status", recipes.load_recipes())
    assert plan.ok and plan.source == "recipe:order-status"
    assert plan.steps[0].action == "goto"


def test_trigger_takes_url_from_task():
    plan = plan_task("check my order status https://shop.example.org/orders", recipes.load_recipes())
    assert plan.steps[0].target == "https://shop.example.org/orders"


def test_format_plan_marks_gates():
    text = planner.format_plan(plan_task("go to https://example.com then submit"))
    assert "Plan (2 steps)" in text
    assert "IRREVERSIBLE, needs your approval" in text
    assert "1 step(s) will stop and ask" in text


def test_format_clarify_plan():
    text = planner.format_plan(plan_task("dance"))
    assert "No plan." in text
