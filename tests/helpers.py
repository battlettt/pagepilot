"""Shared test helpers."""

import contextlib
import shutil
import tempfile

from pagepilot.planner import Plan, Step


@contextlib.contextmanager
def tempdir():
    d = tempfile.mkdtemp(prefix="pagepilot-test-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def plan_of(*steps, task="test task"):
    return Plan(task, list(steps))


def goto(url="https://example.com"):
    return Step("goto", url, description=f"Open {url}")


def raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        return e
    raise AssertionError(f"expected {exc_type.__name__}")


class Recorder:
    """Collects printed lines and scripted answers to prompts."""

    def __init__(self, answers=()):
        self.lines = []
        self.prompts = []
        self.answers = list(answers)

    def out(self, *parts):
        self.lines.append(" ".join(str(p) for p in parts))

    def input(self, prompt):
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    @property
    def text(self):
        return "\n".join(self.lines)
