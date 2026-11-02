"""CLI shape and help text."""

import os
import subprocess
import sys

from helpers import Recorder

from pagepilot import __main__ as cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_help_documents_every_form():
    result = subprocess.run([sys.executable, "-m", "pagepilot", "--help"], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    for text in ("--dry-run", "--list-recipes", "--recipe", "--param", "--yes",
                 '"check my order status"', "irreversible", "--profile", "exit codes"):
        assert text in result.stdout, text


def test_no_task_is_usage_error():
    rec = Recorder()
    assert cli.main([], rec.input, rec.out) == 2


def test_confirmed_plan_calls_runner_with_plan():
    got = []

    def fake_run(plan, args, approve, captcha_prompt, out):
        got.append(plan)
        return 0

    rec = Recorder(["yes"])
    assert cli.main(["check my order status"], rec.input, rec.out, fake_run) == 0
    assert got and got[0].source == "recipe:order-status"
    assert "Run this plan?" in rec.prompts[0]
    # The plan was printed before the question was asked.
    assert "Plan (5 steps)" in rec.text


def test_headless_disables_captcha_continue():
    got = []
    rec = Recorder(["y"])
    cli.main(["--headless", "check my order status"], rec.input, rec.out,
             lambda plan, args, approve, cp, out: got.append(cp) or 0)
    assert got == [None]


def test_missing_playwright_is_reported():
    import importlib.util
    if importlib.util.find_spec("playwright") is not None:
        return  # covered only where Playwright is absent
    rec = Recorder(["y"])
    assert cli.main(["--runs-dir", "/nonexistent/runs", "check my order status"], rec.input, rec.out) == 3
    assert "pip install playwright" in rec.text


def test_no_em_dashes_in_output_or_docs():
    for folder, _, files in os.walk(ROOT):
        if any(part in folder for part in ("__pycache__", "runs", ".git")):
            continue
        for name in files:
            if name.endswith((".py", ".md", ".json", ".html", ".toml")) and name != "BRIEF.md":
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    assert "\u2014" not in f.read(), name
