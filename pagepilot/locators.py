"""Selector resolution with ordered fallback strategies ("self-healing").

Named locators.py (not selectors.py) so it can never shadow the stdlib
`selectors` module that asyncio, and so Playwright, depends on.

Pure module: it only calls methods on the page object it is given, so tests
can pass a fake page. Playwright is never imported here.

Strategy order for each target:
  1. role      exact accessible role + name (button, link, textbox, ...)
  2. css       an explicit CSS selector (step.selector, or a CSS-looking target)
  3. text      visible text content
  4. label     form label text (fallback)
  5. attribute aria-label / placeholder / name / title contains (fallback)
"""

import re
import time

STRATEGIES = ("role", "css", "text", "label", "attribute")

ROLES = {
    "click": ("button", "link", "menuitem", "tab", "checkbox", "radio"),
    "fill": ("textbox", "searchbox", "combobox"),
    "select": ("combobox", "listbox"),
    "wait_for": ("heading", "button", "link", "status", "alert"),
    "extract_text": ("heading", "status", "region", "alert"),
}


class SelectorError(Exception):
    def __init__(self, target, tried):
        self.target = target
        self.tried = tried
        super().__init__(
            f"Could not find '{target}' after trying every strategy: " + "; ".join(tried)
        )


class Resolution:
    def __init__(self, locator, strategy, tried):
        self.locator = locator
        self.strategy = strategy
        self.tried = tried


def looks_like_css(text):
    return bool(re.match(r"^[#.\[]|^[a-z]+[#.\[:]|^[a-z]+\s*>\s*", text or ""))


def _css_escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def candidates(page, step):
    """Yield (strategy, description, locator) in strategy order."""
    target = step.target
    for role in ROLES.get(step.action, ("button", "link")):
        yield "role", f"role={role} name={target!r}", page.get_by_role(role, name=target, exact=True)
    css = step.selector or (target if looks_like_css(target) else "")
    if css:
        yield "css", f"css={css!r}", page.locator(css)
    yield "text", f"text={target!r}", page.get_by_text(target)
    yield "label", f"label={target!r}", page.get_by_label(target)
    t = _css_escape(target)
    attr = f'[aria-label*="{t}" i], [placeholder*="{t}" i], [name*="{t}" i], [title*="{t}" i]'
    yield "attribute", f"attribute~={target!r}", page.locator(attr)


def resolve(page, step, timeout_ms=10000, poll_s=0.2, now=time.monotonic, sleep=time.sleep):
    """Find the element for a step, trying strategies in order.

    Repeats the whole ordered pass until something matches or the timeout
    runs out, so a slow page still gets every strategy. Raises SelectorError
    listing every strategy tried.
    """
    deadline = now() + timeout_ms / 1000.0
    while True:
        tried = []
        for strategy, desc, locator in candidates(page, step):
            try:
                count = locator.count()
            except Exception as e:  # a bad selector must not stop the next strategy
                tried.append(f"{desc} (error: {e})")
                continue
            if count > 0:
                first = locator.first
                remaining = max(0, int((deadline - now()) * 1000))
                try:
                    first.wait_for(state="visible", timeout=max(remaining, 1000))
                except Exception as e:
                    tried.append(f"{desc} (matched {count} but not visible: {e})")
                    continue
                tried.append(f"{desc} (matched)")
                return Resolution(first, strategy, tried)
            tried.append(f"{desc} (no match)")
        if now() >= deadline:
            raise SelectorError(step.target, tried)
        sleep(poll_s)
