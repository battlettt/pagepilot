"""A fake Playwright-like page for tests and the demo mock run. No browser."""

from .executor import CAPTCHA_SELECTOR


class FakeLocator:
    def __init__(self, page, key, count):
        self.page = page
        self.key = key
        self._count = count

    def count(self):
        if isinstance(self._count, Exception):
            raise self._count
        return self._count

    @property
    def first(self):
        return self

    def wait_for(self, state="visible", timeout=None):
        if self.key in self.page.hidden:
            raise TimeoutError(f"{self.key} not visible")

    def _act(self, name, *args):
        self.page.actions.append((name, self.key) + args)
        if self.page.fail.get(self.key, 0) > 0:
            self.page.fail[self.key] -= 1
            raise TimeoutError(f"{name} on {self.key} timed out")

    def click(self, timeout=None):
        self._act("click")

    def fill(self, value, timeout=None):
        self._act("fill", value)

    def select_option(self, label=None, timeout=None):
        self._act("select", label)

    def inner_text(self, timeout=None):
        self._act("inner_text")
        return self.page.texts.get(self.key, "")


class FakePage:
    """matches maps a lookup key to a match count. Keys look like
    'role:button:Submit', 'css:#go', 'text:Results', 'label:Name'."""

    def __init__(self, matches=None, texts=None, captcha=False, fail=None, hidden=()):
        self.matches = dict(matches or {})
        self.texts = dict(texts or {})
        self.captcha = captcha
        self.fail = dict(fail or {})
        self.hidden = set(hidden)
        self.lookups = []
        self.actions = []
        self.screenshots = []

    def _loc(self, key):
        self.lookups.append(key)
        return FakeLocator(self, key, self.matches.get(key, 0))

    def get_by_role(self, role, name=None, exact=False):
        return self._loc(f"role:{role}:{name}")

    def get_by_text(self, text):
        return self._loc(f"text:{text}")

    def get_by_label(self, text):
        return self._loc(f"label:{text}")

    def locator(self, selector):
        if selector == CAPTCHA_SELECTOR:
            return FakeLocator(self, "captcha", 1 if self.captcha else 0)
        return self._loc(f"css:{selector}")

    def goto(self, url, timeout=None):
        self.actions.append(("goto", url))

    def screenshot(self, path=None, full_page=False):
        self.screenshots.append(path)
        with open(path, "wb") as f:
            f.write(b"fake screenshot\n")
