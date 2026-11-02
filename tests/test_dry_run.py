"""Dry-run: plan printed, exit 0, no side effects."""

import os
import subprocess
import sys

from helpers import Recorder, tempdir

from pagepilot import __main__ as cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROBE = """
import runpy, sys
sys.argv = ["pagepilot"] + sys.argv[1:]
try:
    runpy.run_module("pagepilot", run_name="__main__")
except SystemExit as e:
    code = e.code
assert "playwright" not in sys.modules, "dry run imported playwright"
assert "pagepilot.executor" not in sys.modules, "dry run imported the executor"
sys.exit(code)
"""


def run_cli(args, cwd):
    env = dict(os.environ, PYTHONPATH=ROOT)
    return subprocess.run([sys.executable, "-c", PROBE] + args, cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=60)


def test_dry_run_prints_plan_and_exits_zero():
    rec = Recorder()
    code = cli.main(["--dry-run", "check my order status"], rec.input, rec.out)
    assert code == 0
    assert "Plan (5 steps)" in rec.text
    assert "Dry run: no browser launched" in rec.text
    assert rec.prompts == []


def test_dry_run_subprocess_has_no_side_effects():
    with tempdir() as d:
        runs = os.path.join(d, "runs")
        for args in (["--dry-run", "check my order status"],
                     ["--dry-run", "go to https://example.com then fill lamps into Search then submit"],
                     ["--dry-run", "--recipe", "site-search", "--param", "query=lamps"]):
            result = run_cli(args + ["--runs-dir", runs], cwd=d)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "Plan (" in result.stdout
            assert "Dry run: no browser launched, nothing executed, nothing written." in result.stdout
        assert os.listdir(d) == [], os.listdir(d)  # no runs/, no logs, no screenshots


def test_dry_run_of_unknown_task_exits_2_and_writes_nothing():
    with tempdir() as d:
        result = run_cli(["--dry-run", "order a pizza for me"], cwd=d)
        assert result.returncode == 2
        assert "No plan." in result.stdout
        assert os.listdir(d) == []


def test_dry_run_does_not_touch_repo_runs_dir():
    before = os.path.exists(os.path.join(ROOT, "runs"))
    rec = Recorder()
    cli.main(["--dry-run", "--recipe", "contact-form"], rec.input, rec.out)
    assert os.path.exists(os.path.join(ROOT, "runs")) == before
