"""Demo drift: demo/index.html must match the mock data that generates it."""

import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("build_demo", os.path.join(ROOT, "scripts", "build_demo.py"))
build_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_demo)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_mock_data_matches_a_fresh_mock_run():
    assert read(build_demo.MOCK_JSON) == build_demo.mock_json(build_demo.mock_run())


def test_index_html_matches_mock_data():
    log = json.loads(read(build_demo.MOCK_JSON))
    assert read(build_demo.INDEX_HTML) == build_demo.render_html(log)


def test_demo_shows_required_sections():
    page = read(build_demo.INDEX_HTML)
    for text in ("Plan (printed before anything ran)", "Per-step outcomes", "Gate stop",
                 "Final report", "stopped_at_gate", "cannot automate a browser"):
        assert text in page, text


def test_mock_run_shows_fallback_and_retry():
    log = build_demo.mock_run()
    message = [o for o in log["outcomes"] if o["target"] == "Message"][0]
    assert message["strategy"] == "attribute" and message["retries"] == 1
    assert log["final_status"] == "stopped_at_gate"


def test_check_mode_passes():
    assert build_demo.main(["--check"]) == 0
